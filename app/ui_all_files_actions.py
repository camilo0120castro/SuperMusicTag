# app/ui_all_files_actions.py
"""
AllFilesActionsMixin — file deletion and duplicate detection
on the All Files tab.

Split out of ui_all_files.py.
"""
import os
import threading
import customtkinter as ctk
from collections import defaultdict
import send2trash

from app.constants import (
    SUCCESS_GREEN, WARNING_YELLOW, WARNING_ON_LIGHT,
    DANGER_RED, DANGER_RED_HOVER,
    TEXT_MUTED, TEXT_ADAPTIVE, TEXT_WARNING,
    TEXT_PRIMARY,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER,
    ACCENT_BLUE, ORANGE_PRIMARY, ORANGE_HOVER,
)


class AllFilesActionsMixin:
    # ------------------------------------------------------------------
    # File deletion
    # ------------------------------------------------------------------
    def _on_delete_key(self, event, tree):
        if self.is_loading:
            return
        selected = tree.selection()
        if not selected:
            return
        self._delete_selected_files(list(selected))


    def _delete_from_toolbar(self):
        if self.is_loading:
            return
        if not hasattr(self, "_all_files_tree"):
            return
        selected = self._all_files_tree.selection()
        if not selected:
            self._show_info_dialog(
                "No Selection",
                "Select one or more files in the list "
                "before deleting.")
            return
        self._delete_selected_files(list(selected))


    def _delete_selected_files(self, paths: list):
        if not paths:
            return
        count         = len(paths)
        preview_paths = [
            self.all_files_data.get(p, {}).get(
                "rel_path", p)
            for p in paths]
        preview_lines = preview_paths[:5]
        if count > 5:
            preview_lines.append(f"… and {count - 5} more")
        preview_text = "\n".join(
            f"  • {f}" for f in preview_lines)


        dialog = ctk.CTkToplevel(self)
        dialog.title("Delete Files")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 440, 260)


        ctk.CTkLabel(
            dialog,
            text=f"Send {count} file(s) to the Recycle Bin?",
            font=("", 14, "bold")
        ).pack(pady=(20, 6), padx=20)
        ctk.CTkLabel(
            dialog, text=preview_text,
            font=("Courier", 11), justify="left",
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 6), padx=20)
        ctk.CTkLabel(
            dialog,
            text=(
                "⚠  Undo restores the library record in memory only.\n"
                "The file will remain in the Recycle Bin until emptied."
            ),
            text_color=WARNING_ON_LIGHT, font=("", 11),
            justify="left",
        ).pack(pady=(0, 16), padx=20)


        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack()


        def _confirmed():
            dialog.destroy()
            self._execute_delete(paths)


        ctk.CTkButton(
            btn_row, text="Send to Recycle Bin", width=160,
            fg_color=DANGER_RED, hover_color=DANGER_RED_HOVER,
            command=_confirmed
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color=CANCEL_BG, hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy
        ).pack(side="left", padx=8)


    def _execute_delete(self, paths: list):
        self._push_undo_snapshot()
        deleted = 0
        failed  = 0


        for path in paths:
            try:
                self.security_check(path)


                send2trash.send2trash(path)


                self.all_files_data.pop(path, None)
                self._dirty_paths.discard(path)
                self._original_values.pop(path, None)
                self._proposed_changes.pop(path, None)
                self._scanned_unorganized.pop(path, None)
                self._unorg_check_vars.pop(path, None)
                self._search_detached.discard(path)


                for tree in self.active_trees:
                    try:
                        if tree.exists(path):
                            tree.delete(path)
                    except Exception:
                        pass

                # Remove from Unorganized tab treeview explicitly.
                # unorg_tree is not in active_trees.
                if (hasattr(self, "unorg_tree") and
                        self.unorg_tree.exists(path)):
                    try:
                        self.unorg_tree.delete(path)
                    except Exception:
                        pass

                if self._sidebar_active_path == path:
                    self._clear_sidebar()


                deleted += 1


            except PermissionError as exc:
                print(f"[delete] security: {exc}")
                failed += 1
            except Exception as exc:
                print(f"[delete] {os.path.basename(path)}: {exc}")
                failed += 1


        self._invalidate_unorg_cache()
        self.distinct_artists = {
            rec["artist"]
            for rec in self.all_files_data.values()
            if rec["artist"] not in ("Unknown", "")
        }
        self._update_status_bar()
        self._update_unsaved_banner()
        self._invalidate_duplicate_results()


        msg = f"🗑  {deleted} file(s) sent to Recycle Bin."
        if failed:
            msg += f"  ⚠  {failed} failed."
        self._set_sidebar_status(
            msg, SUCCESS_GREEN if not failed else WARNING_YELLOW)
        self._restore_dir_label()


    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------
    def _find_duplicates(self):
        if not self.all_files_data:
            self._show_info_dialog(
                "No Files Loaded",
                "Load a directory before scanning "
                "for duplicates.")
            return
        if self.is_loading:
            return

        # If the window is already open, bring it to front
        if (self._duplicate_window is not None and
                self._duplicate_window.winfo_exists()):
            self._duplicate_window.lift()
            self._duplicate_window.focus_set()
            return

        # If cached results exist, reopen without rescanning
        if self._duplicate_results is not None:
            self._open_duplicates_window(
                self._duplicate_results)
            return

        # No results — run the scan
        self._run_duplicate_scan()

    def _run_duplicate_scan(self):
        self.dir_label.configure(
            text="Scanning for duplicates…",
            text_color=TEXT_WARNING)
        records_snapshot = dict(self.all_files_data)

        def _worker():
            # Method 1 — filename stem match
            stem_groups: dict = defaultdict(list)
            for path, rec in records_snapshot.items():
                stem = os.path.splitext(
                    rec["filename"])[0].lower().strip()
                stem_groups[stem].append(path)
            filename_dupes = [
                {"kind":  "filename",
                 "label": stem,
                 "paths": paths}
                for stem, paths in stem_groups.items()
                if len(paths) > 1
            ]

            # Method 2 — same artist + title tags
            meta_groups: dict = defaultdict(list)
            for path, rec in records_snapshot.items():
                artist = rec.get(
                    "artist", "Unknown").strip().lower()
                title  = rec.get(
                    "title",  "Unknown").strip().lower()
                if (artist == "unknown" or
                        title == "unknown"):
                    continue
                key = f"{artist}|||{title}"
                meta_groups[key].append(path)
            filename_dupe_sets = [
                frozenset(g["paths"])
                for g in filename_dupes]
            meta_dupes = []
            for key, paths in meta_groups.items():
                if len(paths) < 2:
                    continue
                if frozenset(paths) in filename_dupe_sets:
                    continue
                artist_disp, title_disp = key.split(
                    "|||", 1)
                meta_dupes.append({
                    "kind":  "metadata",
                    "label": (
                        f'"{artist_disp}" — '
                        f'"{title_disp}"'),
                    "paths": paths,
                })
            results = {
                "filename": filename_dupes,
                "metadata": meta_dupes,
            }
            self.after(
                0, lambda: self._on_duplicate_scan_done(
                    results))

        threading.Thread(
            target=_worker, daemon=True).start()

    def _on_duplicate_scan_done(self, results: dict):
        self._restore_dir_label()
        self._duplicate_results = results
        self._open_duplicates_window(results)

    def _open_duplicates_window(self, results: dict):
        # Destroy any existing window before creating a new one
        if (self._duplicate_window is not None and
                self._duplicate_window.winfo_exists()):
            try:
                self._duplicate_window.destroy()
            except Exception:
                pass
        self._duplicate_window = None

        filename_dupes = results.get("filename", [])
        metadata_dupes = results.get("metadata", [])
        total_groups   = (
            len(filename_dupes) + len(metadata_dupes))
        total_files    = len({
            p
            for group in filename_dupes + metadata_dupes
            for p in group["paths"]
        })

        win = ctk.CTkToplevel(self)
        win.title("Duplicate Files")
        win.geometry("720x580")
        win.resizable(True, True)
        self._duplicate_window = win

        # Keep window on top of main but not system-modal
        win.transient(self)

        # ----------------------------------------------------------
        # Top bar
        # ----------------------------------------------------------
        top_bar = ctk.CTkFrame(
            win, fg_color="transparent")
        top_bar.pack(
            fill="x", padx=16, pady=(12, 0))
        self._dup_top_bar = top_bar

        ctk.CTkLabel(
            top_bar,
            text="Duplicate Files",
            font=("", 16, "bold"),
        ).pack(side="left")

        ctk.CTkButton(
            top_bar, text="↻ Refresh",
            width=90,
            command=self._refresh_duplicate_window,
        ).pack(side="right", padx=(8, 0))

        all_paths = [
            p
            for group in filename_dupes + metadata_dupes
            for p in group["paths"]
        ]
        ctk.CTkButton(
            top_bar,
            text="📌 View all duplicates",
            width=160,
            command=lambda ap=all_paths: (
                self._fix_filename_cluster(
                    set(ap), origin="Duplicates"),
                win.lift()),
        ).pack(side="right", padx=(0, 4))

        # ----------------------------------------------------------
        # Stale warning banner (hidden by default)
        # ----------------------------------------------------------
        self._dup_stale_banner = ctk.CTkFrame(
            win, fg_color="#3d2600",
            corner_radius=0, height=28)
        self._dup_stale_banner.pack_propagate(False)
        ctk.CTkLabel(
            self._dup_stale_banner,
            text=(
                "⚠  Library has changed. "
                "Click Refresh to update results."),
            text_color=WARNING_YELLOW,
            font=("", 11),
        ).pack(side="left", padx=12, pady=4)
        self._dup_stale_banner.pack_forget()

        # ----------------------------------------------------------
        # Summary line
        # ----------------------------------------------------------
        summary_parts = []
        if filename_dupes:
            summary_parts.append(
                f"{len(filename_dupes)} filename "
                f"group(s)")
        if metadata_dupes:
            summary_parts.append(
                f"{len(metadata_dupes)} metadata "
                f"group(s)")
        summary = (
            "  •  ".join(summary_parts)
            if summary_parts else "")

        ctk.CTkLabel(
            win,
            text=(
                f"Found {total_groups} group(s) "
                f"across {total_files} file(s)"
                + (f"  —  {summary}" if summary else "")),
            font=("", 11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(6, 0))

        # ----------------------------------------------------------
        # Scrollable card area
        # ----------------------------------------------------------
        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(
            fill="both", expand=True,
            padx=12, pady=(8, 12))

        if total_groups == 0:
            ctk.CTkLabel(
                scroll,
                text="No duplicate files found.",
                text_color=TEXT_MUTED,
            ).pack(pady=20)
            return

        if filename_dupes:
            self._add_dup_section_header(
                scroll,
                "Filename Duplicates",
                f"{len(filename_dupes)} group(s)")
            for group in filename_dupes:
                self._build_duplicate_card(
                    scroll, group)

        if metadata_dupes:
            self._add_dup_section_header(
                scroll,
                "Metadata Duplicates",
                f"{len(metadata_dupes)} group(s)")
            for group in metadata_dupes:
                self._build_duplicate_card(
                    scroll, group)

    def _add_dup_section_header(
            self, parent, title: str, subtitle: str):
        ctk.CTkFrame(
            parent, height=1,
            fg_color="gray40",
        ).pack(fill="x", padx=10, pady=(16, 0))
        row = ctk.CTkFrame(
            parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(
            row, text=title,
            font=("", 15, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            row, text=subtitle,
            font=("", 11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(10, 0))

    def _build_duplicate_card(
            self, parent, group: dict):
        kind  = group["kind"]
        label = group["label"]
        paths = group["paths"]

        icon = "📄" if kind == "filename" else "🏷"
        card = ctk.CTkFrame(
            parent,
            corner_radius=8, border_width=1)
        card.pack(fill="x", pady=6, padx=4)

        # Header row
        header_row = ctk.CTkFrame(
            card, fg_color="transparent")
        header_row.pack(
            fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            header_row,
            text=f"{icon}  {label}",
            font=("", 12, "bold"),
            text_color=ACCENT_BLUE, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            header_row,
            text=f"{len(paths)} file(s)",
            font=("", 11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(8, 0))

        # File list — plain labels, no checkboxes
        file_frame = ctk.CTkFrame(
            card, fg_color="transparent")
        file_frame.pack(
            fill="x", padx=12, pady=(0, 6))
        for path in sorted(
                paths,
                key=lambda p:
                os.path.basename(p).lower()):
            ctk.CTkLabel(
                file_frame,
                text=path,
                font=("Courier", 10),
                text_color=TEXT_MUTED,
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=1, padx=4)

        # Divider
        ctk.CTkFrame(
            card, height=1, fg_color="gray30",
        ).pack(fill="x", padx=12, pady=(4, 0))

        # Action row
        action_row = ctk.CTkFrame(
            card, fg_color="transparent")
        action_row.pack(
            fill="x", padx=12, pady=(6, 10))
        ctk.CTkButton(
            action_row,
            text="🔍 View files",
            width=110,
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            font=("", 11, "bold"),
            command=lambda p=paths: (
                self._fix_filename_cluster(
                    set(p), origin="Duplicates"),
                self._duplicate_window.lift()
                if (self._duplicate_window is not None
                    and self._duplicate_window
                    .winfo_exists())
                else None),
        ).pack(side="left")
        ctk.CTkButton(
            action_row,
            text="Dismiss",
            width=80,
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=lambda c=card: (
                c.destroy()),
        ).pack(side="right")

    def _refresh_duplicate_window(self):
        if (self._duplicate_window is None or
                not self._duplicate_window.winfo_exists()):
            return
        # Clear cached results so the scan runs fresh
        self._duplicate_results = None
        # Hide the stale banner if visible
        if hasattr(self, "_dup_stale_banner"):
            try:
                self._dup_stale_banner.pack_forget()
            except Exception:
                pass
        # Close the current window and run a fresh scan
        try:
            self._duplicate_window.destroy()
        except Exception:
            pass
        self._duplicate_window = None
        self._run_duplicate_scan()

    def _invalidate_duplicate_results(self):
        self._duplicate_results = None
        # If the window is open, show the stale banner
        if (self._duplicate_window is not None and
                self._duplicate_window.winfo_exists()):
            if hasattr(self, "_dup_stale_banner"):
                try:
                    self._dup_stale_banner.pack(
                        fill="x", padx=0, pady=(8, 0),
                        after=self._dup_top_bar)
                except Exception:
                    pass

