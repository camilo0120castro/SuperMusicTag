# app/ui_unorganized_edit.py
"""
UnorganizedEditMixin — Unorganized tab inline editing helpers:
per-field clear, double-click cell editor, suggested-filename
rebuild, right-click context menu, and the edit-all-fields dialog.

Lives alongside UnorganizedMixin (ui_unorganized.py).
"""
import os
import tkinter as tk
import customtkinter as ctk


from app.constants import (
    UNORG_EDITABLE_COLS,
    ACCENT_BLUE, SUCCESS_GREEN,
    DANGER_RED, DANGER_RED_HOVER,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    TEXT_PRIMARY, TEXT_ADAPTIVE, TEXT_WARNING, TEXT_MUTED,
)
from app.helpers import _sanitize_filename_part




class UnorganizedEditMixin:


    # ------------------------------------------------------------------
    # Per-field suggestion clear
    # ------------------------------------------------------------------
    def _clear_suggestion_field(self, iid: str,
                                 col_id: str):
        if iid not in self._proposed_changes:
            return
        field_map = {
            "suggest_artist": "artist",
            "suggest_title":  "title",
            "suggest_album":  "album",
        }
        field = field_map.get(col_id)
        if not field:
            return
        self._proposed_changes[iid][field] = ""
        p = self._proposed_changes[iid]
        if all(p.get(f, "") in ("", "Unknown")
               for f in ("artist", "title", "album")):
            del self._proposed_changes[iid]
        self._update_unorg_row(iid)
        if iid == self._sidebar_active_path:
            self._sync_sidebar_from_unorg(iid)


    # ------------------------------------------------------------------
    # Inline cell editor (double-click)
    # ------------------------------------------------------------------
    def _on_unorg_double_click(self, event):
        region = self.unorg_tree.identify_region(
            event.x, event.y)
        if region != "cell":
            return
        iid = self.unorg_tree.focus()
        if not iid:
            iid = self.unorg_tree.identify_row(event.y)
        if not iid:
            return

        col = self.unorg_tree.identify_column(event.x)
        if not col:
            return
        try:
            col_id = self.unorg_tree.column(col, "id")
        except Exception:
            return
        # Non-suggestion columns: double-click toggles the checkbox
        if col_id not in UNORG_EDITABLE_COLS:
            self._toggle_unorg_check(iid)
            return
        if iid not in self._proposed_changes:
            rec = self._scanned_unorganized.get(iid)
            if not rec:
                return
            self._proposed_changes[iid] = {
                "filename": rec["filename"],
                "title": rec["title"],
                "artist": rec["artist"],
                "album": rec["album"],
                "confidence": "manual",
            }
        rec_key = UNORG_EDITABLE_COLS[col_id]
        current = self._proposed_changes[iid].get(
            rec_key, "")
        try:
            bbox = self.unorg_tree.bbox(iid, col_id)
        except Exception:
            return
        if not bbox:
            return
        self._suggestion_overlay.hide()
        x, y, w, h = bbox
        edit_var   = tk.StringVar(value=current)
        _committed = [False]
        entry = tk.Entry(
            self.unorg_tree,
            textvariable=edit_var,
            bg="#1c3a5a", fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat", font=("", 11),
            highlightthickness=1,
            highlightbackground=ACCENT_BLUE)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, tk.END)
        
        undo_stack = [current]
        
        def _on_edit_write(*_):
            val = edit_var.get()
            if not undo_stack or undo_stack[-1] != val:
                undo_stack.append(val)
                if len(undo_stack) > 50:
                    undo_stack.pop(0)
                    
        edit_var.trace_add("write", _on_edit_write)


        def _commit(_event=None):
            if _committed[0]:
                return
            _committed[0] = True
            new_val = edit_var.get().strip()
            try:
                entry.destroy()
            except Exception:
                pass
            if new_val == current:
                return
            self._proposed_changes[iid][rec_key] = \
                new_val
            self._proposed_changes[iid][
                "confidence"] = "manual"
            if rec_key in ("artist", "title"):
                self._rebuild_suggested_filename(iid)
            self._update_unorg_row(iid)
            if iid == self._sidebar_active_path:
                self._sync_sidebar_from_unorg(iid)
            rec_name = self._scanned_unorganized.get(
                iid, {}).get("filename", iid)
            self.unorganized_status_lbl.configure(
                text=(f"✏  Suggestion updated for "
                      f"{rec_name}"),
                text_color=SUCCESS_GREEN)


        def _cancel(_event=None):
            if _committed[0]:
                return
            _committed[0] = True
            try:
                entry.destroy()
            except Exception:
                pass


        def _on_entry_ctrl_z(_event):
            if len(undo_stack) > 1:
                undo_stack.pop() # remove current state
                prev = undo_stack[-1]
                edit_var.set(prev)
                entry.icursor("end")
            return "break"


        entry.bind("<Return>",    _commit)
        entry.bind("<KP_Enter>",  _commit)
        entry.bind("<Escape>",    _cancel)
        entry.bind("<FocusOut>",  _commit)
        entry.bind("<Control-z>", _on_entry_ctrl_z)


    def _rebuild_suggested_filename(self, iid: str):
        proposed = self._proposed_changes.get(iid)
        if not proposed:
            return
        artist = proposed.get("artist", "")
        title  = proposed.get("title",  "")
        if not artist or not title:
            return
        orig_rec = self._scanned_unorganized.get(iid)
        ext = os.path.splitext(
            orig_rec["filename"])[1] \
            if orig_rec else ""
        _repl  = self._get_filename_replacements()
        safe_a = _sanitize_filename_part(
            artist, _repl)
        safe_t = _sanitize_filename_part(
            title, _repl)
        naming = self.naming_convention_var.get()
        proposed["filename"] = (
            f"{safe_a} - {safe_t}{ext}"
            if naming == "Artist - Title"
            else f"{safe_t} - {safe_a}{ext}")


    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------
    def _on_unorg_right_click(self, event):
        iid = self.unorg_tree.identify_row(event.y)
        if not iid:
            return
        self.unorg_tree.focus(iid)
        has_proposal = iid in self._proposed_changes
        proposed     = self._proposed_changes.get(
            iid, {})
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2b2b2b", fg=TEXT_PRIMARY,
            activebackground=ACCENT_BLUE,
            activeforeground=TEXT_PRIMARY,
            font=("", 11))
        menu.add_command(
            label="Edit suggestions…",
            state="normal",
            command=lambda: (
                self._open_suggestion_edit_dialog(
                    iid)))
        menu.add_separator()
        menu.add_command(
            label="🗑 Clear suggestion for this file",
            state="normal" if has_proposal
            else "disabled",
            command=lambda: (
                self._clear_single_suggestion(iid)))
        highlighted = list(
            self.unorg_tree.selection())
        multi_with_proposals = [
            h for h in highlighted
            if h in self._proposed_changes]
        menu.add_command(
            label=(
                f"🗑 Clear suggestions for "
                f"selected files "
                f"({len(multi_with_proposals)})"),
            state="normal"
            if len(multi_with_proposals) > 1
            else "disabled",
            command=lambda iids=multi_with_proposals: (
                self._clear_suggestions_for_paths(
                    iids)))
        menu.add_command(
            label="🗑 Clear all suggestions",
            state="normal"
            if self._proposed_changes
            else "disabled",
            command=self._confirm_clear_all_suggestions)
        menu.add_separator()
        for col_label, col_id, field in [
                ("Clear suggested Artist",
                 "suggest_artist", "artist"),
                ("Clear suggested Title",
                 "suggest_title",  "title"),
                ("Clear suggested Album",
                 "suggest_album",  "album"),
        ]:
            field_val   = proposed.get(field, "")
            field_state = (
                "normal"
                if has_proposal and
                field_val not in ("", "Unknown")
                else "disabled")
            menu.add_command(
                label=col_label,
                state=field_state,
                command=lambda c=col_id: (
                    self._clear_suggestion_field(
                        iid, c)))
        menu.add_separator()
        # "Select highlighted" — shown when multiple rows are highlighted
        # and at least one of them is not yet checked.
        highlighted = list(self.unorg_tree.selection())
        multi_highlighted_unchecked = (
            len(highlighted) > 1 and
            any(not self._is_path_checked(h)
                for h in highlighted))
        if multi_highlighted_unchecked:
            def _select_highlighted(iids=highlighted):
                for h in iids:
                    self._set_check(h, True)
            menu.add_command(
                label="☑  Select highlighted",
                command=_select_highlighted)
        menu.add_command(
            label="☑  Select All",
            command=self._on_select_all_unorg)
        menu.add_command(
            label="☐  Deselect All",
            command=self._on_unselect_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


    # ------------------------------------------------------------------
    # Edit-all-fields dialog
    # ------------------------------------------------------------------
    def _open_suggestion_edit_dialog(self, iid: str):
        proposed = self._proposed_changes.get(iid)
        if not proposed:
            rec = self._scanned_unorganized.get(iid)
            if not rec:
                return
            proposed = {
                "filename": rec["filename"],
                "title": rec["title"],
                "artist": rec["artist"],
                "album": rec["album"],
                "confidence": "manual",
            }
            self._proposed_changes[iid] = proposed
        rec = self._scanned_unorganized.get(iid, {})
        dialog = ctk.CTkToplevel(self)
        dialog.title(
            f"Edit Suggestions — "
            f"{rec.get('filename', iid)}")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 460, 290)
        ctk.CTkLabel(
            dialog, text="Edit Suggested Values",
            font=("", 14, "bold"),
        ).pack(pady=(16, 8), padx=20)
        vars_map: dict = {}
        for field_label, field_key in [
                ("Artist", "artist"),
                ("Title",  "title"),
                ("Album",  "album")]:
            row = ctk.CTkFrame(
                dialog, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(
                row, text=f"{field_label}:",
                width=55, anchor="w",
            ).pack(side="left")
            v = ctk.StringVar(
                value=proposed.get(field_key, ""))
            vars_map[field_key] = v
            ctk.CTkEntry(
                row, textvariable=v,
            ).pack(side="left", fill="x",
                   expand=True, padx=(0, 4))
            ctk.CTkButton(
                row, text="✕",
                width=28, height=28,
                fg_color=DANGER_RED,
                hover_color=DANGER_RED_HOVER,
                font=("", 11, "bold"),
                command=lambda var=v: var.set(""),
            ).pack(side="left")
        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack(pady=(16, 0))


        def _apply():
            changed = False
            for field_key, var in vars_map.items():
                new_val = var.get().strip()
                if new_val != proposed.get(
                        field_key, ""):
                    proposed[field_key] = new_val
                    changed = True
            if changed:
                self._proposed_changes[iid][
                    "confidence"] = "manual"
                self._rebuild_suggested_filename(iid)
                self._update_unorg_row(iid)
                if iid == self._sidebar_active_path:
                    self._sync_sidebar_from_unorg(iid)
                p = self._proposed_changes.get(iid, {})
                if all(
                    p.get(f, "") in ("", "Unknown")
                    for f in (
                        "artist", "title", "album")
                ):
                    self._proposed_changes.pop(
                        iid, None)
                    self._update_unorg_row(iid)
            dialog.destroy()


        def _clear_all():
            for var in vars_map.values():
                var.set("")


        ctk.CTkButton(
            btn_row, text="Apply", width=100,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=_apply,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="Clear All", width=100,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=_clear_all,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy,
        ).pack(side="left", padx=6)

    def _clear_single_suggestion(self, iid: str):
        """Remove the entire suggestion for one file."""
        if iid in self._proposed_changes:
            del self._proposed_changes[iid]
            self._update_unorg_row(iid)
            if iid == self._sidebar_active_path:
                self._sync_sidebar_from_unorg(iid)

    def _clear_suggestions_for_paths(
            self, iids: list):
        """Remove suggestions for a list of files."""
        for iid in iids:
            if iid in self._proposed_changes:
                del self._proposed_changes[iid]
                self._update_unorg_row(iid)
        if self._sidebar_active_path in iids:
            self._sync_sidebar_from_unorg(
                self._sidebar_active_path)

    def _confirm_clear_all_suggestions(self):
        """Show confirmation before clearing all
        suggestions."""
        if not self._proposed_changes:
            return
        count = len(self._proposed_changes)
        dialog = ctk.CTkToplevel(self)
        dialog.title("Clear All Suggestions")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 380, 150)
        ctk.CTkLabel(
            dialog,
            text=f"Clear all {count} suggestion(s)?",
            font=("", 14, "bold"),
        ).pack(pady=(20, 6), padx=20)
        ctk.CTkLabel(
            dialog,
            text=(
                "This will remove all pending "
                "suggestions. This cannot be undone."),
            font=("", 11),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 16), padx=20)
        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack()

        def _confirmed():
            dialog.destroy()
            self._proposed_changes.clear()
            self._rebuild_unorg_table()
            self._clear_sidebar()

        ctk.CTkButton(
            btn_row, text="Clear All", width=100,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=_confirmed,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=dialog.destroy,
        ).pack(side="left", padx=8)

