# app/ui_unorganized.py
"""
UnorganizedMixin — Unorganized tab core: layout, table rebuild/
update, row interactions (click/space/check), reason logic,
sidebar sync, scan trigger, and per-row tag management.


Inline editing, suggestion clearing, right-click menu, and the
edit-all-fields dialog live in UnorganizedEditMixin
(ui_unorganized_edit.py).
Analyze / Organize / Save / write-to-disk / Gemini API live in
UnorganizedActionsMixin (ui_unorganized_actions.py).
The hover ✕ overlay class lives in ui_unorganized_overlay.py.


Colour rules for rows:
  - Base:           even/odd alternating (BG_DARK / BG_DARK_ALT)
  - has_suggestion: SUGGESTION_BG amber tint — applied when at least
                    one suggestion field (artist/title/album) is
                    non-empty. Removed when all three are cleared.
  - Confidence colours: DISABLED — text column only.
  - TTK selection:  blue highlight on click/arrow keys.
  - Checkbox (☑/☐): symbol in col #1 only, no row colour change.
"""
import customtkinter as ctk
from tkinter import ttk


from app.constants import (
    UNORG_COL_IDS, UNORG_COL_DEFS, UNORG_COL_LABELS,
    SUCCESS_GREEN, WARNING_ON_LIGHT,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    DANGER_RED, DANGER_RED_HOVER,
    TEXT_ADAPTIVE, TEXT_WARNING, TEXT_MUTED,
    _COMBO_BTN_HIDDEN, _COMBO_BTN_VISIBLE, WARNING_YELLOW,
)
from app.helpers import _sort_key, _setup_treeview_keyboard_navigation
from app.ui_unorganized_overlay import _SuggestionClearOverlay


# Re-export so legacy `from app.ui_unorganized import _SuggestionClearOverlay`
# keeps working (the class is now defined in ui_unorganized_overlay).
__all__ = ["UnorganizedMixin", "_SuggestionClearOverlay"]




def _format_confidence(confidence: str) -> str:
    """Format confidence value for display in the treeview."""
    _map = {
        "high":         "High",
        "medium":       "Medium",
        "low":          "Low",
        "medium-local": "Local",
        "manual":       "Edited",
    }
    return _map.get(confidence.lower(), confidence.capitalize())


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------
class UnorganizedMixin:


    def _populate_unorganized_tab(self):
        self._clear_tab(self.tab_unorganized)
        self._build_unorganized_layout()
        if self._scanned_unorganized:
            self._rebuild_unorg_table()


    def _build_unorganized_layout(self):
        # Cancel any pending auto-clear timer from the
        # previous layout before rebuilding. Without this,
        # the orphaned after() callback would fire against
        # the new unorganized_status_lbl widget and clear
        # a message that should persist.
        if hasattr(self, "_unorg_status_clear_id") and \
                self._unorg_status_clear_id is not None:
            try:
                self.after_cancel(
                    self._unorg_status_clear_id)
            except Exception:
                pass
        self._unorg_status_clear_id = None
        self.tab_unorganized.grid_columnconfigure(
            0, weight=1)
        self.tab_unorganized.grid_rowconfigure(
            0, weight=0)
        self.tab_unorganized.grid_rowconfigure(
            1, weight=1)
        self.tab_unorganized.grid_rowconfigure(
            2, weight=0)
        self.tab_unorganized.grid_rowconfigure(
            3, weight=0)


        top_bar = ctk.CTkFrame(
            self.tab_unorganized,
            fg_color="transparent")
        top_bar.grid(
            row=0, column=0, sticky="ew",
            pady=(0, 5))


        ctk.CTkLabel(
            top_bar, text="Unorganized Files",
            font=("", 14, "bold"),
        ).pack(side="left", padx=(10, 4))

        self.unorg_strategy_lbl = ctk.CTkLabel(
            top_bar, text="",
            font=("", 11, "bold"))
        self.unorg_strategy_lbl.pack(side="left", padx=4)
        self._update_unorg_strategy_label()


        self.scan_files_btn = ctk.CTkButton(
            top_bar,
            text="🔍 Find Unorganized Files",
            command=self._on_scan_clicked)
        self.scan_files_btn.pack(
            side="right", padx=10)


        ctk.CTkButton(
            top_bar, text="Check All",
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._on_select_all_unorg,
        ).pack(side="right", padx=(0, 4))


        ctk.CTkButton(
            top_bar, text="Uncheck All",
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._on_unselect_all,
        ).pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            top_bar, text="Fix Filenames",
            fg_color="gray35", hover_color="gray45",
            text_color="white",
            command=self._open_fix_filenames_dialog_for_checked,
        ).pack(side="right", padx=(0, 4))


        self.unorganized_status_lbl = ctk.CTkLabel(
            top_bar, text="",
            text_color=SUCCESS_GREEN)
        self.unorganized_status_lbl.pack(
            side="left", padx=10)

        self.unorg_count_lbl = ctk.CTkLabel(
            top_bar, text="",
            text_color=TEXT_MUTED,
            font=("", 11))
        self.unorg_count_lbl.pack(
            side="left", padx=(0, 10))


        # ----------------------------------------------------------
        # Table — use ctk.CTkFrame; overlay uses root-window
        # coordinates so the frame type does not matter.
        # ----------------------------------------------------------
        table_frame = ctk.CTkFrame(
            self.tab_unorganized, corner_radius=0)
        table_frame.grid(
            row=1, column=0, sticky="nsew",
            padx=5, pady=2)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)


        y_bar = ctk.CTkScrollbar(
            table_frame, orientation="vertical")
        y_bar.grid(row=0, column=1, sticky="ns")
        x_bar = ctk.CTkScrollbar(
            table_frame, orientation="horizontal")
        x_bar.grid(row=1, column=0, sticky="ew")


        self.unorg_tree = ttk.Treeview(
            table_frame,
            columns=UNORG_COL_IDS,
            show="headings",
            selectmode="extended",
            yscrollcommand=y_bar.set,
            xscrollcommand=x_bar.set)
        self.unorg_tree.grid(
            row=0, column=0, sticky="nsew")
        y_bar.configure(
            command=self.unorg_tree.yview)
        x_bar.configure(
            command=self.unorg_tree.xview)
        self.unorg_tree.sort_states = {
            col: False for col in UNORG_COL_IDS}


        def _sort(col: str):
            reverse = self.unorg_tree.sort_states[col]
            rows    = [
                (self.unorg_tree.set(k, col), k)
                for k in
                self.unorg_tree.get_children("")]
            rows.sort(
                key=lambda t: _sort_key(t[0]),
                reverse=reverse)
            for i, (_, k) in enumerate(rows):
                self.unorg_tree.move(k, "", i)
                self._retag_unorg_row(k, i)
            for cid in UNORG_COL_IDS:
                base      = UNORG_COL_LABELS[cid]
                indicator = (
                    (" ▼" if reverse else " ▲")
                    if cid == col else "")
                self.unorg_tree.heading(
                    cid,
                    text=base + indicator,
                    command=lambda c=cid: _sort(c))
            self.unorg_tree.sort_states[col] = \
                not reverse


        for col_id, label, w, mw, stretch \
                in UNORG_COL_DEFS:
            anchor = "center" if col_id == "check" else "w"
            self.unorg_tree.heading(
                col_id, text=label, anchor=anchor,
                command=lambda c=col_id: _sort(c))
            self.unorg_tree.column(
                col_id, width=w, minwidth=mw,
                stretch=stretch, anchor=anchor)

        # Hide both current-value and suggestion columns
        # for toggled-off conditions. When a condition
        # is off the user does not need to see either
        # the current value or the suggestion for that
        # field. Cover art and filename conditions have
        # no corresponding tag columns to hide.
        visible_cols = list(UNORG_COL_IDS)
        if not self.unorg_check_artist_var.get():
            visible_cols = [
                c for c in visible_cols
                if c not in (
                    "current_artist",
                    "suggest_artist")]
        if not self.unorg_check_title_var.get():
            visible_cols = [
                c for c in visible_cols
                if c not in (
                    "current_title",
                    "suggest_title")]
        if not self.unorg_check_album_var.get():
            visible_cols = [
                c for c in visible_cols
                if c not in (
                    "current_album",
                    "suggest_album")]
        self.unorg_tree.configure(
            displaycolumns=visible_cols)

        # Distribute available width across all visible
        # columns so they expand proportionally when the
        # window is resized or maximised. Without this,
        # the space beyond the last column is drawn in
        # the light ttk theme colour.
        # The check column is excluded from stretching
        # so it stays compact at its fixed width.
        for col_id in UNORG_COL_IDS:
            self.unorg_tree.column(
                col_id, stretch=False)
        for col_id in visible_cols:
            if col_id != "check":
                self.unorg_tree.column(
                    col_id, stretch=True)

        # --- Tags ---------------------------------------------------
        # NOTE: do NOT set background on the global Treeview
        # ttk style (see _setup_treeview_style) — doing so
        # overrides tag-based backgrounds on Windows.
        _tv = self._get_tv_theme_colours()
        self.unorg_tree.tag_configure(
            "even",
            background=_tv["row_even"],
            foreground=_tv["text"])
        self.unorg_tree.tag_configure(
            "odd",
            background=_tv["row_odd"],
            foreground=_tv["text"])
        self.unorg_tree.tag_configure(
            "has_suggestion",
            background=_tv["suggestion_bg"],
            foreground=_tv["suggestion_fg"])


        # --- Bindings -----------------------------------------------
        self.unorg_tree.bind(
            "<ButtonRelease-1>",
            self._on_unorg_row_click)
        self.unorg_tree.bind(
            "<<TreeviewSelect>>",
            self._on_unorg_select_change)
        self.unorg_tree.bind(
            "<space>",
            self._on_unorg_space_toggle)
        self.unorg_tree.bind(
            "<Double-1>",
            self._on_unorg_double_click)
        self.unorg_tree.bind(
            "<Button-3>",
            self._on_unorg_right_click)
        self.unorg_tree.bind(
            "<Motion>",
            self._on_unorg_motion)
        self.unorg_tree.bind(
            "<Leave>",
            self._on_unorg_leave)

        _setup_treeview_keyboard_navigation(self.unorg_tree)


        # --- Hover ✕ overlay ----------------------------------------
        # The button is parented to the ROOT WINDOW (self)
        # so it is above all other widgets in z-order and
        # its click events are never intercepted.
        self._suggestion_overlay = \
            _SuggestionClearOverlay(
                tree=self.unorg_tree,
                root_window=self,
                col_ids=(
                    "suggest_artist",
                    "suggest_title",
                    "suggest_album"),
                on_clear=self._clear_suggestion_field,
            )


        # ----------------------------------------------------------
        # Tip bar
        # ----------------------------------------------------------
        hint_bar = ctk.CTkFrame(
            self.tab_unorganized,
            fg_color="transparent")
        hint_bar.grid(
            row=2, column=0, sticky="ew",
            padx=5, pady=(0, 2))
        ctk.CTkLabel(
            hint_bar,
            text=(
                "💡  Double-click a suggestion cell "
                "to edit that field inline. Highlighted rows "
                "drive sidebar edits; checked rows drive "
                "Organize/Apply actions."),
            text_color=WARNING_ON_LIGHT,
            font=("", 12),
        ).pack(side="left", padx=6, pady=4)


        # ----------------------------------------------------------
        # Action bar
        # ----------------------------------------------------------
        act_bar = ctk.CTkFrame(self.tab_unorganized)
        act_bar.grid(
            row=3, column=0, sticky="ew",
            padx=5, pady=(4, 6))


        btn_row = ctk.CTkFrame(
            act_bar, fg_color="transparent")
        btn_row.pack(expand=True, pady=(4, 2))


        self.organize_selected_btn = ctk.CTkButton(
            btn_row, text="Organize Checked",
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=self._on_organize_selected)
        self.organize_selected_btn.pack(
            side="left", padx=6)


        self.organize_all_btn = ctk.CTkButton(
            btn_row, text="Organize All",
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=self._on_organize_all)
        self.organize_all_btn.pack(
            side="left", padx=6)


        self.save_selected_btn = ctk.CTkButton(
            btn_row, text="Apply Changes to Checked",
            command=self._on_save_selected_proposed)
        self.save_selected_btn.pack(
            side="left", padx=6)


        self.save_all_btn = ctk.CTkButton(
            btn_row, text="Apply Changes to All",
            command=self._on_save_all_proposed)
        self.save_all_btn.pack(side="left", padx=6)
        self._update_unorg_checked_actions()


    # ------------------------------------------------------------------
    # Hover motion — drives overlay
    # ------------------------------------------------------------------
    def _on_unorg_motion(self, event):
        self._suggestion_overlay.on_motion(event)


    def _on_unorg_leave(self, event):
        self._suggestion_overlay.on_leave(event)


    def _set_check(self, iid: str, value: bool):
        if iid not in self._unorg_check_vars:
            self._unorg_check_vars[iid] = \
                ctk.BooleanVar(value=value)
        else:
            self._unorg_check_vars[iid].set(value)
        self._update_unorg_row(iid)
        self._update_unorg_checked_actions()

    def _count_checked_unorg(self) -> int:
        return sum(
            1 for path, var in self._unorg_check_vars.items()
            if var.get() and path in self._scanned_unorganized)

    def _update_unorg_checked_actions(self):
        checked = self._count_checked_unorg()
        total = len(self._scanned_unorganized)
        try:
            highlighted = len(self.unorg_tree.selection())
        except Exception:
            highlighted = 0

        if hasattr(self, "organize_selected_btn"):
            self.organize_selected_btn.configure(
                text=(
                    f"Organize Checked "
                    f"({checked})"),
                state=(
                    "normal" if checked > 0
                    else "disabled"))
        if hasattr(self, "save_selected_btn"):
            self.save_selected_btn.configure(
                text=(
                    f"Apply Changes to Checked "
                    f"({checked})"),
                state=(
                    "normal" if checked > 0
                    else "disabled"))

        if hasattr(self, "unorg_count_lbl"):
            if self._scanned_unorganized:
                text = (
                    f"Total: {total} unorganized"
                    f"  |  Checked: {checked}")
                if highlighted > 0:
                    text += f"  |  Highlighted: {highlighted}"
                self.unorg_count_lbl.configure(
                    text=text,
                    text_color=(
                        SUCCESS_GREEN
                        if checked > 0
                        else TEXT_MUTED))
            else:
                self.unorg_count_lbl.configure(text="")

    def _set_unorg_status(
            self,
            text: str,
            colour: str,
            persist: bool | None = None):
        """
        Sets the transient operation feedback label
        in the Unorganized tab top bar.

        Mirrors _set_sidebar_status:
        - WARNING_YELLOW and DANGER_RED persist until
          the next operation (user must see errors).
        - SUCCESS_GREEN auto-clears after 5 seconds.
        - persist=True forces the message to stay;
          persist=False forces auto-clear.
        """
        if not hasattr(self, "unorganized_status_lbl"):
            return
        self.unorganized_status_lbl.configure(
            text=text, text_color=colour)

        if hasattr(self, "_unorg_status_clear_id") and \
                self._unorg_status_clear_id is not None:
            try:
                self.after_cancel(
                    self._unorg_status_clear_id)
            except Exception:
                pass
            self._unorg_status_clear_id = None

        should_persist = (
            persist if persist is not None
            else colour in (DANGER_RED, WARNING_YELLOW))

        if not should_persist:
            self._unorg_status_clear_id = self.after(
                5000,
                lambda: (
                    self.unorganized_status_lbl.configure(
                        text="")
                    if hasattr(
                        self,
                        "unorganized_status_lbl")
                    else None))
        else:
            self._unorg_status_clear_id = None

    def _update_unorg_strategy_label(self):
        if not hasattr(self, "unorg_strategy_lbl"):
            return
        strategy = self.organize_strategy_var.get()
        if strategy == "tags_only":
            self.unorg_strategy_lbl.configure(
                text="[Strategy: Local Tags]",
                text_color=WARNING_YELLOW)
        else:
            self.unorg_strategy_lbl.configure(
                text="[Strategy: Gemini AI]",
                text_color=SUCCESS_GREEN)


    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------
    def _reason_for_record(self, rec: dict) -> str:
        if "reason" in rec:
            return rec["reason"]
        if (rec["artist"] == "Unknown" or
                rec["title"] == "Unknown"):
            return "Missing tags"
        return "Filename mismatch"


    def _reason_for_display(self, path: str) -> str:
        proposed    = self._proposed_changes.get(path)
        orig_rec    = self._scanned_unorganized.get(
            path, {})
        orig_reason = self._reason_for_record(orig_rec)
        if not proposed:
            return orig_reason
        ready = True
        if "Missing tags" in orig_reason:
            p_artist = proposed.get("artist", "")
            p_title  = proposed.get("title",  "")
            p_album  = proposed.get("album",  "")
            if not (p_artist not in ("Unknown", "") and
                    p_title  not in ("Unknown", "") and
                    p_album  not in ("Unknown", "")):
                ready = False
        if "Filename mismatch" in orig_reason:
            p_artist = proposed.get("artist", "")
            p_title  = proposed.get("title",  "")
            if not (p_artist not in ("Unknown", "") and
                    p_title  not in ("Unknown", "")):
                ready = False
        if ready:
            return "Ready to save"
        return orig_reason


    def _has_suggestion(self, iid: str) -> bool:
        proposed = self._proposed_changes.get(iid)
        if not proposed:
            return False
        return any(
            proposed.get(f, "") not in ("", "Unknown")
            for f in ("artist", "title", "album"))


    def _retag_unorg_row(self, iid: str, index: int):
        """
        Tag priority (last in tuple wins for background):
            "even"/"odd"     — base alternating colour
            "has_suggestion" — amber tint over base


        NOTE: for tag backgrounds to work, the global
        Treeview ttk style must NOT set background/
        fieldbackground — see _setup_treeview_style.
        """
        base_tag   = "even" if index % 2 == 0 else "odd"
        tags: list = [base_tag]
        if self._has_suggestion(iid):
            tags.append("has_suggestion")
        self.unorg_tree.item(iid, tags=tuple(tags))


    def _rebuild_unorg_table(self):
        if hasattr(self, "_suggestion_overlay"):
            self._suggestion_overlay.hide()
        for item in self.unorg_tree.get_children():
            self.unorg_tree.delete(item)
        for idx, (path, rec) in enumerate(
                self._scanned_unorganized.items()):
            if path not in self._unorg_check_vars:
                self._unorg_check_vars[path] = \
                    ctk.BooleanVar(value=False)
            proposed   = self._proposed_changes.get(
                path)
            reason     = self._reason_for_display(path)
            if proposed:
                sug_artist = proposed.get("artist", "")
                sug_title  = proposed.get("title",  "")
                sug_album  = proposed.get("album",  "")
                confidence = proposed.get(
                    "confidence", "low")
            else:
                sug_artist = sug_title = sug_album = ""
                confidence = ""
            checked = self._is_path_checked(path)
            chk_sym = "☑" if checked else "☐"
            self.unorg_tree.insert(
                "", "end", iid=path,
                values=(
                    chk_sym, rec['filename'], reason,
                    rec["artist"],  sug_artist,
                    rec["title"],   sug_title,
                    rec["album"],   sug_album,
                    _format_confidence(confidence)
                    if confidence else "",
                ))
            self._retag_unorg_row(path, idx)

        # Reapply column visibility in case conditions were toggled
        # while the table was being rebuilt.
        self._refresh_unorg_displaycolumns()

    def _refresh_unorg_displaycolumns(self):
        """Update visible columns in-place without rebuilding the table.

        Called when a condition checkbox is toggled so the column
        visibility changes immediately with no scroll-position reset.
        """
        if not hasattr(self, "unorg_tree"):
            return
        visible = list(UNORG_COL_IDS)
        if not self.unorg_check_artist_var.get():
            visible = [
                c for c in visible
                if c not in ("current_artist", "suggest_artist")]
        if not self.unorg_check_title_var.get():
            visible = [
                c for c in visible
                if c not in ("current_title", "suggest_title")]
        if not self.unorg_check_album_var.get():
            visible = [
                c for c in visible
                if c not in ("current_album", "suggest_album")]
        self.unorg_tree.configure(displaycolumns=visible)
        for col_id in UNORG_COL_IDS:
            self.unorg_tree.column(col_id, stretch=False)
        for col_id in visible:
            if col_id != "check":
                self.unorg_tree.column(col_id, stretch=True)

    def _capture_unorg_view_state(self) -> tuple[list, str, float]:
        if not hasattr(self, "unorg_tree"):
            return [], "", 0.0
        try:
            selection = list(self.unorg_tree.selection())
        except Exception:
            selection = []
        try:
            focus = self.unorg_tree.focus()
        except Exception:
            focus = ""
        try:
            yview = self.unorg_tree.yview()[0]
        except Exception:
            yview = 0.0
        return selection, focus, yview

    def _restore_unorg_view_state(
            self,
            selection: list,
            focus: str,
            yview: float):
        if not hasattr(self, "unorg_tree"):
            return
        valid_selection = [
            iid for iid in selection
            if self.unorg_tree.exists(iid)]
        if valid_selection:
            self.unorg_tree.selection_set(valid_selection)
        else:
            self.unorg_tree.selection_remove(
                *self.unorg_tree.selection())
        if focus and self.unorg_tree.exists(focus):
            self.unorg_tree.focus(focus)
        try:
            self.unorg_tree.yview_moveto(yview)
        except Exception:
            pass

    def _sync_unorg_sidebar_from_tree_selection(self):
        if (getattr(self, "_active_tab", "")
                != "Unorganized"):
            return
        if not hasattr(self, "unorg_tree"):
            return
        highlighted = [
            iid for iid in self.unorg_tree.selection()
            if iid in self._scanned_unorganized]
        if len(highlighted) > 1:
            self._sync_sidebar_multi_unorg(highlighted)
        elif len(highlighted) == 1:
            self._sync_sidebar_from_unorg(highlighted[0])
        else:
            focus = self.unorg_tree.focus()
            if focus in self._scanned_unorganized:
                self._sync_sidebar_from_unorg(focus)
            else:
                self._clear_sidebar()

    def _sync_unorganized_after_record_changes(
            self,
            paths: list[str]):
        if not self._scanned_unorganized:
            return

        selection, focus, yview = \
            self._capture_unorg_view_state()
        membership_changed = False

        for path in dict.fromkeys(paths):
            updated = self._build_unorganized_record(path)
            exists = path in self._scanned_unorganized

            if updated is None:
                if exists:
                    membership_changed = True
                    self._scanned_unorganized.pop(path, None)
                    self._proposed_changes.pop(path, None)
                    self._unorg_check_vars.pop(path, None)
                    if (hasattr(self, "unorg_tree") and
                            self.unorg_tree.exists(path)):
                        try:
                            self.unorg_tree.delete(path)
                        except Exception:
                            pass
                continue

            self._scanned_unorganized[path] = updated
            if membership_changed:
                continue
            if not exists:
                membership_changed = True
                continue
            if (hasattr(self, "unorg_tree") and
                    self.unorg_tree.exists(path)):
                self._update_unorg_row(path)

        if membership_changed:
            self._scanned_unorganized = {
                path: self._scanned_unorganized[path]
                for path in self.all_files_data
                if path in self._scanned_unorganized
            }
            if hasattr(self, "unorg_tree"):
                self._rebuild_unorg_table()
                self._restore_unorg_view_state(
                    selection, focus, yview)

        self._sync_unorg_sidebar_from_tree_selection()
        self._update_unorg_checked_actions()


    def _update_unorg_row(self, path: str):
        if not self.unorg_tree.exists(path):
            return
        rec      = self._scanned_unorganized.get(path)
        proposed = self._proposed_changes.get(path)
        if not rec:
            return
        checked  = self._is_path_checked(path)
        chk_sym  = "☑" if checked else "☐"
        reason   = self._reason_for_display(path)
        if proposed:
            sug_artist = proposed.get("artist", "")
            sug_title  = proposed.get("title",  "")
            sug_album  = proposed.get("album",  "")
            confidence = proposed.get(
                "confidence", "low")
        else:
            sug_artist = sug_title = sug_album = ""
            confidence = ""
        self.unorg_tree.item(path, values=(
            chk_sym, rec["filename"], reason,
            rec["artist"],  sug_artist,
            rec["title"],   sug_title,
            rec["album"],   sug_album,
            _format_confidence(confidence)
            if confidence else "",
        ))
        all_iids = self.unorg_tree.get_children()
        idx      = (
            list(all_iids).index(path)
            if path in all_iids else 0)
        self._retag_unorg_row(path, idx)


    # ------------------------------------------------------------------
    # Row interaction
    # ------------------------------------------------------------------
    def _on_unorg_row_click(self, event):
        region = self.unorg_tree.identify_region(
            event.x, event.y)
        if region not in ("cell", "tree"):
            return
        iid = self.unorg_tree.identify_row(event.y)
        if not iid:
            return
        col = self.unorg_tree.identify_column(event.x)
        try:
            col_id = self.unorg_tree.column(col, "id")
        except Exception:
            col_id = ""
        shift_held = bool(event.state & 0x0001)
        ctrl_held  = bool(event.state & 0x0004)
        if col_id == "check":
            # Dedicated checkbox column — always toggles
            self._toggle_unorg_check(iid)
        elif shift_held:
            # Set every highlighted row as checked
            for sel_iid in self.unorg_tree.selection():
                self._set_check(sel_iid, True)
        elif ctrl_held:
            # Toggle checkbox of the clicked row
            self._toggle_unorg_check(iid)
        # Sync sidebar — single or multi depending on
        # how many rows are currently highlighted
        highlighted = list(self.unorg_tree.selection())
        if len(highlighted) > 1:
            self._sync_sidebar_multi_unorg(highlighted)
        else:
            self._sync_sidebar_from_unorg(iid)
        self._update_unorg_row(iid)

    def _on_unorg_select_change(self, event=None):
        self._sync_unorg_sidebar_from_tree_selection()
        self._update_unorg_checked_actions()


    def _on_unorg_space_toggle(self, _event):
        iid = self.unorg_tree.focus()
        if iid:
            self._toggle_unorg_check(iid)


    def _toggle_unorg_check(self, iid: str):
        if iid not in self._unorg_check_vars:
            self._unorg_check_vars[iid] = \
                ctk.BooleanVar(value=False)
        var = self._unorg_check_vars[iid]
        var.set(not var.get())
        self._update_unorg_row(iid)
        self._update_unorg_checked_actions()


    def _sync_sidebar_from_unorg(self, iid: str):
        proposed = self._proposed_changes.get(iid)
        if not proposed:
            self._clear_sidebar()
            self.multi_hint_header_lbl.configure(
                text="No suggestion yet.",
                text_color=TEXT_WARNING)
            self.multi_hint_lbl.configure(
                text="Highlighting controls the sidebar. "
                     "Check rows for Organize/Apply. "
                     "Use Organize to generate a suggestion "
                     "for this track.",
                text_color=TEXT_ADAPTIVE)
            self.analyze_track_btn.configure(
                state="normal"
                if self.organize_strategy_var.get()
                == "gemini"
                else "disabled")
            self._sidebar_active_path    = iid
            self._sidebar_selected_paths = [iid]
            self._unorg_sidebar_active_path = iid
            self._unorg_sidebar_selected_paths = [iid]
            # Context is unorg_suggestion even with no
            # proposal — the file is from the Unorganized
            # tab and should never route through the
            # all_files save path.
            self._sidebar_context = "unorg_suggestion"
            self.save_metadata_btn.configure(
                text="Update Suggestion",
                state="disabled")
            return
        self._display_cover_art(iid)
        self.meta_filename_var.set(
            proposed.get("filename", ""))
        self.meta_filename_entry.configure(
            state="normal")
        self.meta_title_var.set(
            proposed.get("title",  ""))
        self.meta_artist_var.set(
            proposed.get("artist", ""))
        self.meta_album_var.set(
            proposed.get("album",  ""))
        # Show <remove> and current proposed value in
        # each dropdown so the user can clear a field.
        for key, combo in self._field_combos.items():
            current = proposed.get(key, "")
            opts = [self._MULTI_REMOVE]
            if current:
                opts.append(current)
            combo.configure(
                values=opts,
                button_color=_COMBO_BTN_VISIBLE[0],
                button_hover_color=_COMBO_BTN_VISIBLE[1])
        self._sidebar_context = "unorg_suggestion"
        self.save_metadata_btn.configure(
            state="normal",
            text="Update Suggestion")
        self.analyze_track_btn.configure(
            state="normal"
            if self.organize_strategy_var.get()
            == "gemini"
            else "disabled")
        self._sidebar_active_path    = iid
        self._sidebar_selected_paths = [iid]
        self._unorg_sidebar_active_path = iid
        self._unorg_sidebar_selected_paths = [iid]
        self.multi_hint_header_lbl.configure(
            text="Editing suggestion.",
            text_color=TEXT_ADAPTIVE)
        self.multi_hint_lbl.configure(
            text="Sidebar edits apply to the highlighted "
                 "row only. Checked rows are used by "
                 "Organize/Apply actions.",
            text_color=TEXT_ADAPTIVE)


    def _sync_sidebar_multi_unorg(
            self, iids: list):
        """
        Called when multiple rows are highlighted in
        the Unorganized tab.

        Shows <multiple> in all fields by default.
        If all selected files' PROPOSALS share the same
        artist value, pre-populates the artist field
        and allows editing.
        If all selected files' PROPOSALS share the same
        album value, pre-populates the album field
        and allows editing.
        Title is never pre-populated across multiple
        files.
        Files with no proposal are ignored for the
        shared-value check.
        """
        # Collect proposals for all highlighted files
        proposals = {
            iid: self._proposed_changes[iid]
            for iid in iids
            if iid in self._proposed_changes
        }

        # Clear sidebar and set multi state
        self._clear_sidebar()

        # Disable filename and title — never batch edit
        self.meta_filename_var.set("<multiple>")
        self.meta_filename_entry.configure(
            state="disabled")
        self.meta_title_var.set("<multiple>")

        # Check artist shared value across proposals
        artist_values = {
            p.get("artist", "")
            for p in proposals.values()
            if p.get("artist", "") not in ("", "Unknown")
        }
        if len(artist_values) == 1:
            # All proposals share the same artist
            shared_artist = next(iter(artist_values))
            self.meta_artist_var.set(shared_artist)
            self._field_combos["artist"].configure(
                state="normal",
                button_color=_COMBO_BTN_VISIBLE[0],
                button_hover_color=_COMBO_BTN_VISIBLE[1])
        else:
            self.meta_artist_var.set("<multiple>")

        # Check album shared value across proposals
        album_values = {
            p.get("album", "")
            for p in proposals.values()
            if p.get("album", "") not in ("", "Unknown")
        }
        if len(album_values) == 1:
            # All proposals share the same album
            shared_album = next(iter(album_values))
            self.meta_album_var.set(shared_album)
            self._field_combos["album"].configure(
                state="normal",
                button_color=_COMBO_BTN_VISIBLE[0],
                button_hover_color=_COMBO_BTN_VISIBLE[1])
        else:
            self.meta_album_var.set("<multiple>")

        # Enable save only if there are proposals to
        # update and at least one field is editable
        has_editable = (
            len(artist_values) == 1 or
            len(album_values) == 1)

        self._sidebar_context = "unorg_suggestion"
        if proposals and has_editable:
            self.save_metadata_btn.configure(
                state="normal",
                text="Update Suggestion")
        else:
            self.save_metadata_btn.configure(
                state="disabled",
                text="Update Suggestion")

        self.analyze_track_btn.configure(
            state="disabled")
        self._sidebar_active_path    = None
        self._sidebar_selected_paths = list(iids)
        self._unorg_sidebar_active_path = None
        self._unorg_sidebar_selected_paths = list(iids)

        count = len(iids)
        has_proposals = len(proposals)
        self.multi_hint_header_lbl.configure(
            text=f"{count} files selected.",
            text_color=TEXT_ADAPTIVE)

        if has_proposals == 0:
            hint = (
                "None of the selected files have "
                "suggestions yet. Run 'Organize' "
                "first.")
        elif has_proposals < count:
            hint = (
                f"{has_proposals} of {count} selected "
                f"files have suggestions. "
                f"Sidebar edits apply to highlighted rows; "
                f"Organize/Apply buttons use checked rows.")
        else:
            hint = (
                "Shared fields can be edited below. "
                "'Update Suggestion' applies to highlighted "
                "rows; Organize/Apply buttons use checked rows.")

        self.multi_hint_lbl.configure(
            text=hint,
            text_color=TEXT_ADAPTIVE)


    def _refresh_sidebar_if_active(self, iid: str):
        """Re-sync the sidebar if iid is the currently displayed row."""
        if iid == self._sidebar_active_path:
            self._sync_sidebar_from_unorg(iid)

    def _on_select_all_unorg(self):
        for iid in self.unorg_tree.get_children():
            if iid not in self._unorg_check_vars:
                self._unorg_check_vars[iid] = \
                    ctk.BooleanVar(value=True)
            else:
                self._unorg_check_vars[iid].set(True)
            self._update_unorg_row(iid)
        self._update_unorg_checked_actions()


    def _on_unselect_all(self):
        for iid in self.unorg_tree.get_children():
            if iid in self._unorg_check_vars:
                self._unorg_check_vars[iid].set(False)
            self._update_unorg_row(iid)
        self._update_unorg_checked_actions()


    # ------------------------------------------------------------------
    # Unorganized actions
    # ------------------------------------------------------------------
    def _open_fix_filenames_dialog_for_checked(self):
        """
        Fix Filenames from the Unorganized tab.
        Only considers checked rows. Builds the mismatch
        list by filtering the full _find_filename_mismatches
        result to checked paths only, then opens the shared
        Fix Filenames dialog pre-filtered to those files.

        Uses _find_filename_mismatches so all naming
        convention, sanitization, and Unknown-tag rules
        stay in one place with no duplication.
        """
        if not self._scanned_unorganized:
            self._show_info_dialog(
                "No Scan Results",
                "Run 'Find Unorganized Files' "
                "first, then check at least one "
                "row before using Fix Filenames.")
            return

        checked_paths = {
            path for path in self._scanned_unorganized
            if self._is_path_checked(path)
        }
        if not checked_paths:
            self._show_info_dialog(
                "No Files Checked",
                "Check at least one row in the "
                "Unorganized tab before using "
                "Fix Filenames.")
            return

        all_mismatches = self._find_filename_mismatches()
        mismatches = [
            m for m in all_mismatches
            if m[0] in checked_paths
        ]

        if not mismatches:
            skipped = sum(
                1 for path in checked_paths
                if (
                    self.all_files_data.get(
                        path, {}).get(
                            "artist", "Unknown")
                    == "Unknown"
                    or
                    self.all_files_data.get(
                        path, {}).get(
                            "title", "Unknown")
                    == "Unknown"))
            if skipped:
                self._show_info_dialog(
                    "No Mismatches Found",
                    f"✔ All checked files already "
                    f"match their tags.\n\n"
                    f"Note: {skipped} file(s) were "
                    f"skipped because their Artist "
                    f"or Title tag is Unknown — a "
                    f"meaningful filename cannot be "
                    f"computed without both values.")
            else:
                self._show_info_dialog(
                    "No Mismatches Found",
                    "✔ All checked files already "
                    "match their tags.")
            return

        self._open_fix_filenames_dialog(mismatches)

    def _on_scan_clicked(self):
        if not self.all_files_data:
            self._set_unorg_status(
                "Load a directory first.",
                TEXT_WARNING)
            return
        if self._proposed_changes:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Unsaved Suggestions")
            dialog.resizable(False, False)
            dialog.grab_set()
            self._center_dialog(dialog, 420, 170)
            ctk.CTkLabel(
                dialog,
                text="You have unsaved suggestions.",
                font=("", 14, "bold"),
            ).pack(pady=(20, 6), padx=20)
            ctk.CTkLabel(
                dialog,
                text=(
                    "Running a new scan will discard "
                    "all current suggestions. "
                    "Save or apply them first, or "
                    "click Discard to clear them and "
                    "run the scan now."),
                font=("", 11),
                text_color=TEXT_MUTED,
                wraplength=380, justify="left",
            ).pack(pady=(0, 16), padx=20)
            btn_row = ctk.CTkFrame(
                dialog, fg_color="transparent")
            btn_row.pack()

            def _discard_and_scan():
                dialog.destroy()
                self._proposed_changes.clear()
                self._unorg_check_vars.clear()
                self._do_scan()

            ctk.CTkButton(
                btn_row,
                text="Discard & Rescan",
                width=130,
                fg_color=DANGER_RED,
                hover_color=DANGER_RED_HOVER,
                command=_discard_and_scan,
            ).pack(side="left", padx=8)
            ctk.CTkButton(
                btn_row, text="Cancel", width=100,
                fg_color=SAVE_BLUE,
                hover_color=SAVE_BLUE_HOVER,
                command=dialog.destroy,
            ).pack(side="left", padx=8)
            return
        self._do_scan()

    def _do_scan(self):
        """Runs the unorganized scan. Called directly
        or after the user confirms discarding suggestions."""
        self.scan_files_btn.configure(
            state="disabled", text="Scanning…")
        self.update_idletasks()
        unorganized = self._get_unorganized_records()
        self._scanned_unorganized = unorganized
        self._unorg_check_vars.clear()
        self._proposed_changes.clear()
        self._populate_unorganized_tab()
        if unorganized:
            self._set_unorg_status(
                f"Found {len(unorganized)} "
                f"unorganized file(s). "
                f"Select rows then click "
                f"'Organize'.",
                TEXT_WARNING,
                persist=True)
        else:
            self._set_unorg_status(
                "✔ All files are organized!",
                SUCCESS_GREEN)
        self.scan_files_btn.configure(
            state="normal",
            text="🔍 Find Unorganized Files")


    def _is_path_checked(self, path: str) -> bool:
        var = self._unorg_check_vars.get(path)
        return var.get() if var is not None else False

