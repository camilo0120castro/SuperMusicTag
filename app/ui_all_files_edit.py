# app/ui_all_files_edit.py
"""
AllFilesEditMixin — inline filename editing and right-click
revert menu on the All Files treeview.

Split out of ui_all_files.py.
"""
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from app.constants import (
    ACCENT_BLUE, SUCCESS_GREEN, WARNING_YELLOW,
    DANGER_RED, TEXT_PRIMARY,
)
from app.helpers import (
    _validate_new_filename,
    _sanitize_filename_part,
)


class AllFilesEditMixin:
    # ------------------------------------------------------------------
    # Inline filename editing
    # ------------------------------------------------------------------
    def _on_all_files_double_click(self, event,
                                    tree: ttk.Treeview):
        region = tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        iid = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if not iid or not col:
            return
        try:
            col_id = tree.column(col, "id")
        except tk.TclError:
            return
        if col_id == "filename":
            self._open_all_files_filename_editor(
                tree, iid)
        elif col_id in ("title", "artist", "album"):
            self._open_all_files_tag_editor(
                tree, iid, col_id)


    def _on_all_files_f2(self, event, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
        iid = selected[-1]
        tree.focus(iid)
        tree.see(iid)
        # F2 on filename column or no specific column
        # defaults to filename editor.
        # If a cell is focused on a tag column, open
        # the tag editor for that column instead.
        try:
            col = tree.identify_column(
                tree.winfo_pointerx()
                - tree.winfo_rootx())
            col_id = tree.column(col, "id")
        except Exception:
            col_id = "filename"
        if col_id in ("title", "artist", "album"):
            self._open_all_files_tag_editor(
                tree, iid, col_id)
        else:
            self._open_all_files_filename_editor(
                tree, iid)


    def _open_all_files_filename_editor(self, tree: ttk.Treeview,
                                         iid: str):
        if iid not in self.all_files_data:
            return
        rec     = self.all_files_data[iid]
        current = rec["filename"]


        try:
            bbox = tree.bbox(iid, "filename")
        except Exception:
            return
        if not bbox:
            return


        x, y, w, h = bbox
        edit_var    = tk.StringVar(value=current)
        _committed  = [False]


        entry = tk.Entry(
            tree,
            textvariable=edit_var,
            bg="#1c3a5a", fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat", font=("", 11),
            highlightthickness=1,
            highlightbackground=ACCENT_BLUE)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, tk.END)


        def _commit(_event=None):
            if _committed[0]:
                return
            _committed[0] = True
            new_val = edit_var.get().strip()
            try:
                entry.destroy()
            except Exception:
                pass
            if not new_val or new_val == current:
                return
            valid, ext_warning = _validate_new_filename(
                new_val, current)
            if not valid:
                self._set_sidebar_status(
                    f"⚠ {ext_warning}", DANGER_RED)
                return


            self._snapshot_original(iid)
            self._push_undo_snapshot()
            rec["filename"] = new_val
            self._dirty_paths.add(iid)
            self._fuzzy_stale = True
            self._invalidate_unorg_cache()
            self._update_tree_row(iid, rec)
            self._update_status_bar()
            self._update_unsaved_banner()


            try:
                is_active = (tree.selection() == (iid,))
            except Exception:
                is_active = (iid == self._sidebar_active_path)


            if is_active:
                self.meta_filename_var.set(new_val)
                if ext_warning:
                    self._set_sidebar_status(
                        f"✔ Filename updated. "
                        f"{ext_warning}", WARNING_YELLOW)
                else:
                    self._set_sidebar_status(
                        "✔ Filename updated.",
                        SUCCESS_GREEN)
            elif ext_warning:
                self._set_sidebar_status(
                    ext_warning, WARNING_YELLOW)


        def _cancel(_event=None):
            if _committed[0]:
                return
            _committed[0] = True
            try:
                entry.destroy()
            except Exception:
                pass


        def _on_entry_ctrl_z(_event):
            _cancel()
            return "break"


        entry.bind("<Return>",    _commit)
        entry.bind("<KP_Enter>",  _commit)
        entry.bind("<Escape>",    _cancel)
        entry.bind("<FocusOut>",  _commit)
        entry.bind("<Control-z>", _on_entry_ctrl_z)

    def _open_all_files_tag_editor(
            self,
            tree: ttk.Treeview,
            iid: str,
            col_id: str):
        """
        Inline editor for Title, Artist, and Album
        columns in the All Files treeview.
        Behaviour mirrors the filename editor:
        - Enter / FocusOut commits
        - Escape cancels
        - Ctrl+Z cancels (preserves global undo)
        On commit, pushes an undo snapshot and adds
        the path to _dirty_paths.
        If the edited field is Title or Artist, a
        non-blocking notification asks the user whether
        to rebuild the filename.
        """
        if iid not in self.all_files_data:
            return
        rec     = self.all_files_data[iid]
        current = rec.get(col_id, "")

        try:
            bbox = tree.bbox(iid, col_id)
        except Exception:
            return
        if not bbox:
            return

        x, y, w, h = bbox
        edit_var   = tk.StringVar(value=current)
        _committed = [False]

        entry = tk.Entry(
            tree,
            textvariable=edit_var,
            bg="#1c3a5a", fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat", font=("", 11),
            highlightthickness=1,
            highlightbackground=ACCENT_BLUE)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def _commit(_event=None):
            if _committed[0]:
                return
            _committed[0] = True
            new_val = edit_var.get().strip()
            try:
                entry.destroy()
            except Exception:
                pass
            if not new_val or new_val == current:
                return

            self._snapshot_original(iid)
            self._push_undo_snapshot()
            rec[col_id] = new_val

            if col_id == "artist":
                self.distinct_artists = {
                    r["artist"]
                    for r in self.all_files_data.values()
                    if r["artist"] not in (
                        "Unknown", "")
                }

            self._dirty_paths.add(iid)
            self._fuzzy_stale = True
            self._invalidate_unorg_cache()

            if self._scanned_unorganized:
                self._sync_unorganized_after_record_changes(
                    [iid])

            self._update_tree_row(iid, rec)

            # Sync sidebar if this file is active
            if self._sidebar_active_path == iid:
                if col_id == "title":
                    self.meta_title_var.set(new_val)
                elif col_id == "artist":
                    self.meta_artist_var.set(new_val)
                elif col_id == "album":
                    self.meta_album_var.set(new_val)

            self._update_status_bar()
            self._update_unsaved_banner()

            # Ask about filename rebuild for
            # title and artist changes only
            if col_id in ("title", "artist"):
                self._show_filename_rebuild_notification(
                    iid)

        def _cancel(_event=None):
            if _committed[0]:
                return
            _committed[0] = True
            try:
                entry.destroy()
            except Exception:
                pass

        def _on_ctrl_z(_event):
            _cancel()
            return "break"

        entry.bind("<Return>",    _commit)
        entry.bind("<KP_Enter>",  _commit)
        entry.bind("<Escape>",    _cancel)
        entry.bind("<FocusOut>",  _commit)
        entry.bind("<Control-z>", _on_ctrl_z)

    def _get_filename_rebuild_target(
            self,
            path: str) -> str | None:
        rec = self.all_files_data.get(path)
        if not rec:
            return None

        artist = rec.get("artist", "Unknown")
        title  = rec.get("title",  "Unknown")
        naming = self.naming_convention_var.get()
        ext    = os.path.splitext(
            rec["filename"])[1]

        _repl       = self._get_filename_replacements()
        safe_artist = _sanitize_filename_part(
            artist, _repl)
        safe_title  = _sanitize_filename_part(
            title, _repl)

        if naming == "Artist - Title":
            new_filename = (
                f"{safe_artist} - {safe_title}{ext}")
        else:
            new_filename = (
                f"{safe_title} - {safe_artist}{ext}")

        if new_filename == rec["filename"]:
            return None
        return new_filename

    def _apply_filename_rebuilds(
            self,
            paths: list[str]) -> list[tuple[str, str]]:
        candidates = []
        for path in dict.fromkeys(paths):
            new_filename = self._get_filename_rebuild_target(
                path)
            if new_filename:
                candidates.append((path, new_filename))

        if not candidates:
            return []

        self._push_undo_snapshot()
        for path, new_filename in candidates:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            self._snapshot_original(path)
            rec["filename"] = new_filename
            self._dirty_paths.add(path)
            self._fuzzy_stale = True
            self._update_tree_row(path, rec)
            if self._sidebar_active_path == path:
                self.meta_filename_var.set(new_filename)

        changed_paths = [path for path, _ in candidates]
        if self._scanned_unorganized:
            self._sync_unorganized_after_record_changes(
                changed_paths)
        self._update_status_bar()
        self._update_unsaved_banner()
        return candidates

    def _show_filename_rebuild_notification(
            self, path: str):
        """
        Shows a small non-blocking notification in the
        bottom-right corner of the main window asking
        the user whether to rebuild the filename from
        the current Title and Artist tag values.

        Multiple notifications stack vertically upward.
        Each notification stays until answered.
        Clicking Yes rebuilds and commits the filename.
        Clicking No dismisses without changes.
        """
        new_filename = self._get_filename_rebuild_target(
            path)
        if not new_filename:
            return

        # Initialise notification stack tracker
        if not hasattr(self, "_notif_stack"):
            self._notif_stack: list = []

        # Notification card dimensions
        _NOTIF_W = 320
        _NOTIF_H = 90
        _NOTIF_PAD = 8
        _NOTIF_RIGHT_MARGIN = 12
        _NOTIF_BOTTOM_MARGIN = 12

        def _get_next_y():
            base_y = (
                self.winfo_height()
                - _NOTIF_BOTTOM_MARGIN
                - _NOTIF_H)
            for _ in self._notif_stack:
                base_y -= (_NOTIF_H + _NOTIF_PAD)
            return base_y

        notif = tk.Frame(
            self,
            bg="#1e1e1e",
            highlightbackground="#444444",
            highlightthickness=1,
            width=_NOTIF_W,
            height=_NOTIF_H)

        x_pos = (
            self.winfo_width()
            - _NOTIF_W
            - _NOTIF_RIGHT_MARGIN)
        y_pos = _get_next_y()

        notif.place(x=x_pos, y=y_pos,
                    width=_NOTIF_W,
                    height=_NOTIF_H)
        notif.lift()
        self._notif_stack.append(notif)

        # Notification text
        short_fn = (
            new_filename
            if len(new_filename) <= 34
            else new_filename[:31] + "…")

        tk.Label(
            notif,
            text="Rename file to match tags?",
            bg="#1e1e1e", fg="white",
            font=("", 10, "bold"),
            anchor="w",
        ).place(x=10, y=8, width=300)

        tk.Label(
            notif,
            text=short_fn,
            bg="#1e1e1e", fg="#aaaaaa",
            font=("Courier", 9),
            anchor="w",
        ).place(x=10, y=28, width=300)

        def _remove_notif():
            if notif in self._notif_stack:
                idx = self._notif_stack.index(notif)
                self._notif_stack.remove(notif)
                try:
                    notif.place_forget()
                    notif.destroy()
                except Exception:
                    pass
                # Shift all notifications above this
                # one downward to fill the gap
                for i, n in enumerate(
                        self._notif_stack[idx:],
                        start=idx):
                    new_y = (
                        self.winfo_height()
                        - _NOTIF_BOTTOM_MARGIN
                        - _NOTIF_H
                        - i * (_NOTIF_H + _NOTIF_PAD))
                    try:
                        n.place(
                            x=x_pos, y=new_y,
                            width=_NOTIF_W,
                            height=_NOTIF_H)
                    except Exception:
                        pass

        def _on_yes():
            _remove_notif()
            self._apply_filename_rebuilds([path])

        def _on_no():
            _remove_notif()

        btn_frame = tk.Frame(
            notif, bg="#1e1e1e")
        btn_frame.place(
            x=10, y=54,
            width=_NOTIF_W - 20,
            height=28)

        tk.Button(
            btn_frame,
            text="Yes — rename",
            bg="#1565C0", fg="white",
            font=("", 9),
            relief="flat",
            cursor="hand2",
            command=_on_yes,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_frame,
            text="No",
            bg="#333333", fg="white",
            font=("", 9),
            relief="flat",
            cursor="hand2",
            command=_on_no,
        ).pack(side="left")

    def _show_filename_rebuild_notifications(
            self,
            paths: list[str]):
        unique_paths = list(dict.fromkeys(paths))
        candidates = [
            path for path in unique_paths
            if self._get_filename_rebuild_target(path)]
        if not candidates:
            return
        if len(candidates) == 1:
            self._show_filename_rebuild_notification(
                candidates[0])
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Rebuild Filenames")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 520, 290)

        ctk.CTkLabel(
            dialog,
            text=(
                f"Rebuild filenames for "
                f"{len(candidates)} edited file(s)?"),
            font=("", 14, "bold"),
        ).pack(pady=(20, 8), padx=20, anchor="w")

        ctk.CTkLabel(
            dialog,
            text=(
                "Artist/title changes created filename "
                "mismatches. Rebuild all filenames now, "
                "or keep the current names and review later."),
            font=("", 11),
            wraplength=470,
            justify="left",
        ).pack(pady=(0, 10), padx=20, anchor="w")

        preview_lines = []
        for path in candidates[:5]:
            rec = self.all_files_data.get(path, {})
            preview_lines.append(
                rec.get("rel_path", os.path.basename(path)))
        if len(candidates) > 5:
            preview_lines.append(
                f"... and {len(candidates) - 5} more")

        ctk.CTkLabel(
            dialog,
            text="\n".join(preview_lines),
            font=("Courier", 11),
            justify="left",
            anchor="w",
            wraplength=470,
        ).pack(padx=20, pady=(0, 16), anchor="w")

        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack(pady=(0, 16))

        def _confirm():
            dialog.destroy()
            applied = self._apply_filename_rebuilds(
                candidates)
            if applied:
                self._set_sidebar_status(
                    f"✔ Rebuilt filenames for "
                    f"{len(applied)} file(s).",
                    SUCCESS_GREEN)

        ctk.CTkButton(
            btn_row,
            text="Rebuild All",
            width=120,
            command=_confirm,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row,
            text="Later",
            width=100,
            command=dialog.destroy,
        ).pack(side="left", padx=6)

    def _dismiss_all_notifications(self):
        """
        Dismisses all pending filename rebuild
        notifications. Called when the user discards
        all changes so stale notifications are not
        left visible.
        """
        if not hasattr(self, "_notif_stack"):
            return
        for notif in list(self._notif_stack):
            try:
                notif.place_forget()
                notif.destroy()
            except Exception:
                pass
        self._notif_stack.clear()

    def _play_files(self, paths: list):
        """
        Open files with the system default media player.
        Uses os.startfile on Windows, 'open' on macOS,
        and 'xdg-open' on Linux. Each file is passed
        separately — the OS/player decides how to handle
        multiple files (queue, playlist, etc.).
        No error handling — if the OS cannot open a file
        we simply let it fail silently.
        """
        for path in paths:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(
                        ["cmd", "/c", "start",
                         "", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
                elif sys.platform == "darwin":
                    subprocess.Popen(
                        ["open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(
                        ["xdg-open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
            except Exception as exc:
                print(
                    f"[play] could not open "
                    f"{os.path.basename(path)}"
                    f": {exc}")

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------
    def _on_all_files_right_click(self, event,
                                   tree: ttk.Treeview):
        """
        Right-click context menu on All Files treeview.
        Shows Play for selected files, then Revert for
        dirty rows.
        """
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.focus(iid)

        # Collect paths to play — all selected if
        # multiple, otherwise just the clicked row.
        selected = list(tree.selection())
        if iid not in selected:
            selected = [iid]
        play_paths = [
            p for p in selected
            if p in self.all_files_data]

        is_dirty = iid in self._dirty_paths
        has_orig = iid in self._original_values

        menu = tk.Menu(
            self, tearoff=0,
            bg="#2b2b2b", fg=TEXT_PRIMARY,
            activebackground=ACCENT_BLUE,
            activeforeground=TEXT_PRIMARY,
            font=("", 11))

        # ── Play ──────────────────────────────────────
        play_label = (
            f"▶  Play ({len(play_paths)} file(s))"
            if len(play_paths) > 1
            else "▶  Play")
        menu.add_command(
            label=play_label,
            command=lambda p=play_paths:
            self._play_files(p))

        cover_label = (
            f"🎨  Edit Cover Art "
            f"({len(play_paths)} file(s))"
            if len(play_paths) > 1
            else "🎨  Edit Cover Art")
        menu.add_command(
            label=cover_label,
            command=lambda p=play_paths:
            self._open_bulk_cover_art(p))

        menu.add_separator()

        # ── Revert ────────────────────────────────────
        if is_dirty and has_orig:
            menu.add_command(
                label="↩  Revert this file",
                command=lambda: (
                    self._revert_single_file(iid),
                    self._set_sidebar_status(
                        f"↩ Reverted: "
                        f"{os.path.basename(iid)}",
                        SUCCESS_GREEN)))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_bulk_cover_art(self, paths: list):
        if not paths:
            return
        from app.ui_cover_art_bulk import BulkCoverArtDialog

        def _after_save(saved_path: str,
                        image_bytes: bytes):
            rec = self.all_files_data.get(saved_path)
            if rec:
                rec["has_cover_art"] = True
            if saved_path == self._sidebar_active_path:
                self._display_cover_art(saved_path)
                self._set_sidebar_status(
                    "✔ Cover art saved.",
                    SUCCESS_GREEN)

        BulkCoverArtDialog(
            parent=self,
            paths=paths,
            records=self.all_files_data,
            on_save=_after_save)

