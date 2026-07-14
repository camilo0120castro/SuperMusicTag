# app/ui_dialogs.py
"""
DialogsMixin — groups all modal popup dialogs:
  - _center_dialog           (positioning helper)
  - _show_info_dialog        (generic info box)
  - _open_column_reorder_dialog
  - _check_api_key / _show_api_key_popup
  - _review_changes / _open_review_changes_dialog
  - _discard_all_changes
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from app.config import _save_config
from app.constants import (
    WARNING_YELLOW,
    DANGER_RED, DANGER_RED_HOVER,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_ADAPTIVE,
    BG_DARK, ACCENT_BLUE, COL_IDS, COL_LABELS,
)
from app.helpers import _truncate_path


class DialogsMixin:
    # ------------------------------------------------------------------
    # Center dialog helper
    # ------------------------------------------------------------------
    def _center_dialog(self, dialog: ctk.CTkToplevel,
                        w: int, h: int):
        dialog.update_idletasks()
        sx = (self.winfo_x()
              + (self.winfo_width()  // 2)
              - (w // 2))
        sy = (self.winfo_y()
              + (self.winfo_height() // 2)
              - (h // 2))
        dialog.geometry(f"{w}x{h}+{sx}+{sy}")

    # ------------------------------------------------------------------
    # Generic info dialog
    # ------------------------------------------------------------------
    def _show_info_dialog(self, title: str,
                           message: str):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 360, 130)
        ctk.CTkLabel(
            dialog, text=message,
            font=("", 12), wraplength=320,
        ).pack(pady=(24, 12), padx=20)
        ctk.CTkButton(
            dialog, text="OK", width=80,
            command=dialog.destroy,
        ).pack(pady=(0, 16))

    # ------------------------------------------------------------------
    # Column reorder dialog
    # ------------------------------------------------------------------
    def _open_column_reorder_dialog(self):
        if not self.active_trees:
            return
        original_order = list(self._saved_column_order)  # snapshot for cancel
        current_cols   = list(original_order)             # working copy
        dialog = ctk.CTkToplevel(self)
        dialog.title("Reorder Columns — All Files")
        dialog.grab_set()
        self._center_dialog(dialog, 300, 420)

        ctk.CTkLabel(
            dialog,
            text=(
                "Drag to reorder, use Up/Down, or press "
                "Alt+Up / Alt+Down. Reset restores the default layout."),
            wraplength=260,
        ).pack(pady=(15, 5), padx=10)

        lb_frame = ctk.CTkFrame(dialog)
        lb_frame.pack(
            fill="both", expand=True,
            padx=15, pady=5)
        listbox = tk.Listbox(
            lb_frame, bg=BG_DARK, fg=TEXT_PRIMARY,
            selectbackground=ACCENT_BLUE,
            font=("", 12),
            borderwidth=0, highlightthickness=0)
        listbox.pack(fill="both", expand=True)
        for col in current_cols:
            listbox.insert(
                tk.END, COL_LABELS.get(col, col))

        def apply_preview():
            self._saved_column_order = list(current_cols)
            self._apply_column_order()

        def move(delta: int):
            sel = listbox.curselection()
            if not sel:
                return
            idx     = sel[0]
            new_idx = idx + delta
            if new_idx < 0 or \
                    new_idx >= listbox.size():
                return
            text = listbox.get(idx)
            listbox.delete(idx)
            listbox.insert(new_idx, text)
            listbox.select_set(new_idx)
            current_cols.insert(
                new_idx, current_cols.pop(idx))
            apply_preview()

        def reset_to_default():
            current_cols[:] = list(COL_IDS)
            listbox.delete(0, tk.END)
            for col in current_cols:
                listbox.insert(
                    tk.END, COL_LABELS.get(col, col))
            if current_cols:
                listbox.select_set(0)
            apply_preview()

        _drag_src = [None]

        def _on_drag_start(event):
            _drag_src[0] = listbox.nearest(event.y)
            listbox.select_clear(0, tk.END)
            listbox.select_set(_drag_src[0])

        def _on_drag_motion(event):
            src = _drag_src[0]
            if src is None:
                return
            dst = listbox.nearest(event.y)
            if dst == src:
                return
            text = listbox.get(src)
            listbox.delete(src)
            listbox.insert(dst, text)
            listbox.select_clear(0, tk.END)
            listbox.select_set(dst)
            current_cols.insert(
                dst, current_cols.pop(src))
            _drag_src[0] = dst
            apply_preview()

        def _on_drag_release(_event):
            _drag_src[0] = None

        listbox.bind(
            "<ButtonPress-1>",  _on_drag_start)
        listbox.bind(
            "<B1-Motion>",       _on_drag_motion)
        listbox.bind(
            "<ButtonRelease-1>", _on_drag_release)
        listbox.bind(
            "<Alt-Up>",
            lambda e: (move(-1), "break")[1])
        listbox.bind(
            "<Alt-Down>",
            lambda e: (move(1), "break")[1])

        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=5)
        ctk.CTkButton(
            btn_row, text="▲ Up", width=80,
            command=lambda: move(-1),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="▼ Down", width=80,
            command=lambda: move(1),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Reset", width=80,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=reset_to_default,
        ).pack(side="right", padx=5)

        def apply():
            self._saved_column_order = list(current_cols)
            _save_config(self._current_config_dict())
            dialog.destroy()

        def cancel():
            current_cols[:] = original_order
            self._saved_column_order = list(original_order)
            self._apply_column_order()
            dialog.destroy()

        apply_cancel_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        apply_cancel_row.pack(pady=(5, 15))
        ctk.CTkButton(
            apply_cancel_row, text="Apply", width=80,
            command=apply,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            apply_cancel_row, text="Cancel", width=80,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=cancel,
        ).pack(side="left", padx=5)

    # ------------------------------------------------------------------
    # API key helpers
    # ------------------------------------------------------------------
    def _check_api_key(self) -> bool:
        if os.environ.get("GEMINI_API_KEY"):
            return True
        self._show_api_key_popup()
        return False

    def _show_api_key_popup(self):
        popup = ctk.CTkToplevel(self)
        popup.title("Gemini API Key Required")
        popup.resizable(False, False)
        popup.grab_set()
        self._center_dialog(popup, 480, 210)

        ctk.CTkLabel(
            popup,
            text="Gemini API Key Not Found",
            font=("", 16, "bold"),
        ).pack(pady=(24, 6), padx=24)

        # Platform-specific command and note.
        # Only the relevant OS command is shown —
        # no need to show both and confuse the user.
        if sys.platform == "win32":
            cmd  = 'setx GEMINI_API_KEY "your-key-here"'
            note = (
                "Run in Command Prompt, then "
                "restart SuperMusicTag.")
        else:
            cmd  = 'export GEMINI_API_KEY="your-key-here"'
            note = (
                "Add to ~/.bashrc or ~/.zshrc, "
                "then restart SuperMusicTag.")

        ctk.CTkLabel(
            popup,
            text=note,
            font=("", 11),
            text_color="gray70",
            justify="left",
        ).pack(pady=(0, 6), padx=24, anchor="w")

        # Selectable, copyable entry in readonly state.
        # The user can Ctrl+A / Ctrl+C to copy the
        # command without retyping it.
        cmd_entry = ctk.CTkEntry(
            popup,
            font=("Courier", 12),
            width=420,
            state="normal")
        cmd_entry.insert(0, cmd)
        cmd_entry.configure(state="readonly")
        cmd_entry.pack(padx=24, pady=(0, 16))

        ctk.CTkButton(
            popup, text="OK", width=100,
            command=popup.destroy,
        ).pack(pady=(0, 16))

    # ------------------------------------------------------------------
    # Review Changes — switches to All Files tab so amber
    # rows are visible, then opens the unified dialog.
    # ------------------------------------------------------------------
    def _review_changes(self):
        if getattr(self, "_active_tab", "") != "All Files":
            self._switch_tab(
                "All Files",
                clear_sidebar=False)
        self._open_review_changes_dialog()

    # ------------------------------------------------------------------
    # Review Changes dialog — the single place to both
    # review AND commit. "Save to disk" calls
    # _execute_commit() directly (no second dialog).
    # ------------------------------------------------------------------
    def _open_review_changes_dialog(self):
        if not self._dirty_paths:
            return

        # Build summary counts for the title bar
        tag_changes    = 0
        rename_changes = 0
        for path in self._dirty_paths:
            rec  = self.all_files_data.get(path)
            orig = self._original_values.get(path)
            if not rec:
                continue
            if orig:
                for field in (
                        "title", "artist", "album"):
                    if rec.get(field) != orig.get(
                            field):
                        tag_changes += 1
                        break
                if rec.get("filename") != orig.get(
                        "filename"):
                    rename_changes += 1
            else:
                tag_changes += 1

        summary_parts = []
        if tag_changes:
            summary_parts.append(
                f"{tag_changes} tag change(s)")
        if rename_changes:
            summary_parts.append(
                f"{rename_changes} rename(s)")
        summary = (
            "  •  ".join(summary_parts)
            if summary_parts else "")

        dialog = ctk.CTkToplevel(self)
        dialog.title("Review & Save Changes")
        dialog.resizable(True, True)
        dialog.grab_set()
        self._center_dialog(dialog, 760, 560)

        # ── Title ──────────────────────────────────────
        ctk.CTkLabel(
            dialog,
            text=(
                f"Pending Changes — "
                f"{len(self._dirty_paths)} file(s)"
                + (f"  ({summary})"
                   if summary else "")),
            font=("", 15, "bold"),
        ).pack(pady=(16, 4), padx=20, anchor="w")

        ctk.CTkLabel(
            dialog,
            text=(
                "Review all changes below. "
                "Click 'Save to disk' to commit, or "
                "click '↩ Revert' on any row to undo "
                "that file's changes."),
            font=("", 11), text_color=TEXT_MUTED,
            wraplength=720,
        ).pack(pady=(0, 8), padx=20, anchor="w")

        # ── Treeview ───────────────────────────────────
        tree_frame = ctk.CTkFrame(
            dialog, corner_radius=0)
        tree_frame.pack(
            fill="both", expand=True,
            padx=16, pady=(0, 8))

        y_bar = ctk.CTkScrollbar(
            tree_frame, orientation="vertical")
        y_bar.pack(side="right", fill="y")
        x_bar = ctk.CTkScrollbar(
            tree_frame, orientation="horizontal")
        x_bar.pack(side="bottom", fill="x")

        cols = ("file", "field", "before",
                "after", "action")
        tree = ttk.Treeview(
            tree_frame, columns=cols,
            show="headings", selectmode="none",
            yscrollcommand=y_bar.set,
            xscrollcommand=x_bar.set)
        y_bar.configure(command=tree.yview)
        x_bar.configure(command=tree.xview)

        tree.heading(
            "file",   text="File",   anchor="w")
        tree.heading(
            "field",  text="Field",  anchor="w")
        tree.heading(
            "before", text="Before", anchor="w")
        tree.heading(
            "after",  text="After",  anchor="w")
        tree.heading(
            "action", text="",       anchor="w")

        tree.column("file",   width=200, minwidth=120)
        tree.column("field",  width=85,  minwidth=60)
        tree.column("before", width=190, minwidth=100)
        tree.column("after",  width=190, minwidth=100)
        tree.column("action", width=75,  minwidth=60)

        _tv = self._get_tv_theme_colours()
        tree.tag_configure(
            "changed",
            background=_tv["row_even"],
            foreground=_tv["text"])
        tree.tag_configure(
            "edge",
            background=_tv["row_odd"],
            foreground=_tv["text"])

        tree.pack(fill="both", expand=True)

        # Map treeview iid → file path for revert clicks
        iid_to_path: dict = {}

        fields = [
            ("filename", "Filename"),
            ("title",    "Title"),
            ("artist",   "Artist"),
            ("album",    "Album"),
        ]

        for path in sorted(
                self._dirty_paths,
                key=lambda p:
                os.path.basename(p).lower()):
            rec  = self.all_files_data.get(path)
            orig = self._original_values.get(path)
            if not rec:
                continue
            display_path = rec.get(
                "rel_path",
                _truncate_path(path))
            first    = True

            for field_key, field_label in fields:
                current  = rec.get(field_key, "")
                original = (
                    orig.get(field_key, current)
                    if orig else current)
                if current == original:
                    continue

                # Show filename only on first changed
                # field per file to avoid repetition
                display_name = display_path if first else ""
                first        = False

                iid = tree.insert(
                    "", "end",
                    values=(
                        display_name,
                        field_label,
                        original,
                        current,
                        "↩ Revert"),
                    tags=("changed",))
                iid_to_path[iid] = path

            if first:
                # No fields actually changed — skip.
                continue

        # ── Revert click handler ───────────────────────
        def _on_tree_click(event):
            region = tree.identify_region(
                event.x, event.y)
            if region != "cell":
                return
            col = tree.identify_column(event.x)
            iid = tree.identify_row(event.y)
            if not iid or not col:
                return
            try:
                col_id = tree.column(col, "id")
            except Exception:
                return
            if col_id != "action":
                return
            path = iid_to_path.get(iid)
            if not path:
                return
            self._revert_single_file(path)
            dialog.destroy()
            if self._dirty_paths:
                self._open_review_changes_dialog()

        tree.bind(
            "<ButtonRelease-1>", _on_tree_click)

        # ── Bottom row ─────────────────────────────────
        bottom_frame = ctk.CTkFrame(
            dialog, fg_color="transparent")
        bottom_frame.pack(
            fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(
            bottom_frame,
            text=(
                "⚠  Changes will be written to disk. "
                "This cannot be undone from disk."),
            text_color=WARNING_YELLOW,
            font=("", 11),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            bottom_frame,
            text="Close", width=80,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            bottom_frame,
            text="💾 Save to disk",
            width=130,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            font=("", 12, "bold"),
            command=lambda: (
                dialog.destroy(),
                self._execute_commit()),
        ).pack(side="right", padx=(0, 6))

    # ------------------------------------------------------------------
    # Discard all changes
    # ------------------------------------------------------------------
    def _discard_all_changes(self):
        if not self._dirty_paths and not self._undo_stack:
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Discard All Changes")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 360, 150)

        ctk.CTkLabel(
            dialog,
            text="Discard ALL in-memory changes?",
            font=("", 14, "bold"),
        ).pack(pady=(24, 6), padx=20)
        ctk.CTkLabel(
            dialog,
            text=(
                "This will undo every change since "
                "the last load."),
            text_color=TEXT_MUTED, font=("", 11),
        ).pack(pady=(0, 16), padx=20)

        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack()

        def _confirmed():
            dialog.destroy()

            was_pinned = (
                hasattr(self, "_search_pinned_paths")
                and self._search_pinned_paths is not None)

            # Restore from the load snapshot if available —
            # this works correctly even past the bounded
            # undo stack. Falls back to walking the undo
            # stack if no snapshot exists.
            if self._load_snapshot is not None:
                self._undo_stack.clear()
                self._redo_stack.clear()
                # _load_snapshot contains only the four
                # user-editable fields. Merge them back
                # into the live records — read-only fields
                # (bitrate, length, path, etc.) are left
                # untouched since they reflect current
                # disk state and were never mutated.
                for path, fields in \
                        self._load_snapshot.items():
                    rec = self.all_files_data.get(path)
                    if rec:
                        rec["filename"] = \
                            fields["filename"]
                        rec["title"]    = \
                            fields["title"]
                        rec["artist"]   = \
                            fields["artist"]
                        rec["album"]    = \
                            fields["album"]
                self.distinct_artists = {
                    rec["artist"]
                    for rec in
                    self.all_files_data.values()
                    if rec["artist"] not in (
                        "Unknown", "")
                }
                self._dirty_paths.clear()
                self._clear_original_values()
                self._invalidate_unorg_cache()
                self._update_undo_redo_buttons()
                self._refresh_all_views()
            else:
                while len(self._undo_stack) > 1:
                    self._redo_stack.append(
                        self._undo_stack.pop())
                if self._undo_stack:
                    self._do_undo()

            # Dismiss any pending filename rebuild
            # notifications
            self._dismiss_all_notifications()

            # If the user discards all changes while
            # pinned, clear the filter and return
            if was_pinned:
                self._clear_pinned_filter()
                self._switch_tab(
                    "Fuzzy Matches",
                    clear_sidebar=False)

        ctk.CTkButton(
            btn_row, text="Discard", width=100,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=_confirmed,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy,
        ).pack(side="left", padx=8)

