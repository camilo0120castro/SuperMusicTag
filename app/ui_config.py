# app/ui_config.py
"""
ConfigMixin — manages the global configuration overlay screen,
config-dict helpers, and the on-config-change handler.
"""
import customtkinter as ctk

from app.config import _save_config
from app.constants import (
    DANGER_RED, DANGER_RED_HOVER,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER,
    SUCCESS_GREEN, WARNING_YELLOW, TEXT_MUTED,
    TEXT_DISABLED, TEXT_ADAPTIVE, TEXT_PRIMARY,
)


class ConfigMixin:
    def _capture_config_view_state(self) -> dict:
        state = self._current_config_dict().copy()
        state["filename_replacements"] = dict(
            state["filename_replacements"])
        if hasattr(self, "_prompt_textbox"):
            state["_prompt_textbox"] = self._prompt_textbox.get(
                "1.0", "end").strip()
        else:
            state["_prompt_textbox"] = self.gemini_prompt_var.get().strip()
        return state

    def _restore_config_view_state(self, state: dict):
        self.naming_convention_var.set(
            state.get("naming_convention", "Artist - Title"))
        self.fuzzy_threshold_var.set(
            state.get("fuzzy_threshold", 85.0))
        self.fuzzy_show_collaboration_var.set(
            state.get("fuzzy_show_collaboration", True))
        self._saved_column_order = list(
            state.get("column_order", self._saved_column_order))
        self._fuzzy_ignore_pairs = set(
            state.get("fuzzy_ignore_pairs", []))
        self.unorg_check_artist_var.set(
            state.get("unorg_check_artist", True))
        self.unorg_check_title_var.set(
            state.get("unorg_check_title", True))
        self.unorg_check_album_var.set(
            state.get("unorg_check_album", True))
        self.unorg_check_filename_var.set(
            state.get("unorg_check_filename", True))
        self.unorg_check_cover_art_var.set(
            state.get("unorg_check_cover_art", False))
        self.organize_strategy_var.set(
            state.get("organize_strategy", "gemini"))
        self.gemini_search_title_var.set(
            state.get("gemini_search_title", True))
        self.gemini_search_artist_var.set(
            state.get("gemini_search_artist", True))
        self.gemini_search_album_var.set(
            state.get("gemini_search_album", True))
        self.gemini_logging_var.set(
            state.get("gemini_logging", False))
        self.gemini_prompt_var.set(
            state.get("gemini_prompt", ""))
        self.table_theme_var.set(
            state.get("table_theme", "dark"))
        replacements = state.get("filename_replacements", {})
        for char, var in self.filename_replacements_vars.items():
            var.set(replacements.get(char, var.get()))
        if hasattr(self, "_prompt_textbox"):
            prompt_text = state.get(
                "_prompt_textbox",
                self.gemini_prompt_var.get().strip())
            self._prompt_textbox.delete("1.0", "end")
            self._prompt_textbox.insert("1.0", prompt_text)
        if hasattr(self, "fuzzy_val_label"):
            self.fuzzy_val_label.configure(
                text=f"{int(self.fuzzy_threshold_var.get())}%")
        self._apply_table_theme()
        self._on_unorg_conditions_change()
        self._on_strategy_change()
        self._on_config_change("")

    def _has_unsaved_config_changes(self) -> bool:
        if not hasattr(self, "_config_open_state"):
            return False
        return self._capture_config_view_state() != self._config_open_state

    def _save_config_overlay_state(self):
        if hasattr(self, "_prompt_textbox"):
            text = self._prompt_textbox.get(
                "1.0", "end").strip()
            self.gemini_prompt_var.set(text)
        self._saved_naming_convention = \
            self.naming_convention_var.get()
        self._saved_fuzzy_threshold = \
            self.fuzzy_threshold_var.get()
        _save_config(self._current_config_dict())
        self._config_open_state = \
            self._capture_config_view_state()
        if hasattr(self, "_config_saved_label"):
            self._config_saved_label.configure(
                text="✓ Saved!")
            self.after(
                2000, lambda:
                self._config_saved_label.configure(
                    text=""))

    def _sync_config_open_state_to_current(self):
        if hasattr(self, "_config_open_state"):
            self._config_open_state = \
                self._capture_config_view_state()

    # ------------------------------------------------------------------
    # Config helper
    # ------------------------------------------------------------------
    def _current_config_dict(self) -> dict:
        return {
            "naming_convention":
                self.naming_convention_var.get(),
            "fuzzy_threshold":
                self.fuzzy_threshold_var.get(),
            "fuzzy_show_collaboration":
                self.fuzzy_show_collaboration_var.get(),
            "column_order":
                self._saved_column_order,
            "fuzzy_ignore_pairs":
                list(self._fuzzy_ignore_pairs),
            "unorg_check_artist":
                self.unorg_check_artist_var.get(),
            "unorg_check_title":
                self.unorg_check_title_var.get(),
            "unorg_check_album":
                self.unorg_check_album_var.get(),
            "unorg_check_filename":
                self.unorg_check_filename_var.get(),
            "unorg_check_cover_art":
                self.unorg_check_cover_art_var.get(),
            "organize_strategy":
                self.organize_strategy_var.get(),
            "gemini_search_title":
                self.gemini_search_title_var.get(),
            "gemini_search_artist":
                self.gemini_search_artist_var.get(),
            "gemini_search_album":
                self.gemini_search_album_var.get(),
            "gemini_logging":
                self.gemini_logging_var.get(),
            "gemini_prompt":
                self.gemini_prompt_var.get(),
            "table_theme":
                self.table_theme_var.get(),
            "filename_replacements": {
                char: var.get()
                for char, var in
                self.filename_replacements_vars.items()
            },
        }

    def _on_config_change(self, _new_val: str):
        if not self.all_files_data:
            return
        self._invalidate_unorg_cache()
        if self._scanned_unorganized:
            self._scanned_unorganized = \
                self._get_unorganized_records()
        if hasattr(self, "unorg_tree"):
            self._rebuild_unorg_table()
        elif self._scanned_unorganized:
            self._populate_unorganized_tab()

    def _on_strategy_change(self):
        """
        Called when the organize strategy radio button
        changes. Greys out the Gemini logging switch
        and field checkboxes when tags_only is selected.

        When re-enabling for gemini strategy, respects
        the condition toggle state — a Gemini field
        checkbox is only re-enabled if its corresponding
        condition toggle is also on.
        """
        is_gemini = (
            self.organize_strategy_var.get() == "gemini")

        # Grey out the logging switch when Gemini
        # is not in use
        if hasattr(self, "_gemini_log_switch"):
            self._gemini_log_switch.configure(
                state="normal" if is_gemini
                else "disabled")

        # Grey out / re-enable field checkboxes.
        # When re-enabling, also check the corresponding
        # condition toggle — if the condition is off,
        # the Gemini field stays greyed out.
        if hasattr(self, "_gemini_title_chk"):
            if not is_gemini:
                self._gemini_title_chk.configure(
                    state="disabled")
            else:
                self._gemini_title_chk.configure(
                    state="normal"
                    if self.unorg_check_title_var.get()
                    else "disabled")

        if hasattr(self, "_gemini_artist_chk"):
            if not is_gemini:
                self._gemini_artist_chk.configure(
                    state="disabled")
            else:
                self._gemini_artist_chk.configure(
                    state="normal"
                    if self.unorg_check_artist_var.get()
                    else "disabled")

        if hasattr(self, "_gemini_album_chk"):
            if not is_gemini:
                self._gemini_album_chk.configure(
                    state="disabled")
            else:
                self._gemini_album_chk.configure(
                    state="normal"
                    if self.unorg_check_album_var.get()
                    else "disabled")

        # Update the sidebar Analyze button
        if hasattr(self, "analyze_track_btn"):
            if self._sidebar_active_path:
                self.analyze_track_btn.configure(
                    state="normal")
            else:
                self.analyze_track_btn.configure(
                    state="disabled")

        if hasattr(self, "_update_unorg_strategy_label"):
            self._update_unorg_strategy_label()

    def _on_gemini_fields_change(self):
        """
        Called when any Gemini field checkbox changes.
        Blocks the operation if all independently
        controllable fields are unchecked — at least
        one must remain on.

        Fields whose condition toggle is off are
        excluded from the count since they are forced
        off by the condition and are not user-controlled.
        """
        # Only count fields whose condition is active
        # as "independently controllable"
        title_active  = self.unorg_check_title_var.get()
        artist_active = self.unorg_check_artist_var.get()
        album_active  = self.unorg_check_album_var.get()

        title  = self.gemini_search_title_var.get()
        artist = self.gemini_search_artist_var.get()
        album  = self.gemini_search_album_var.get()

        # Build list of fields that are both condition-
        # active and Gemini-searchable
        controllable_on = [
            title  and title_active,
            artist and artist_active,
            album  and album_active,
        ]

        # If at least one condition is active and all
        # active-condition fields are unchecked, block it
        any_condition_active = any([
            title_active, artist_active, album_active])

        if any_condition_active and not any(
                controllable_on):
            # Restore only the fields whose conditions
            # are active
            if title_active:
                self.gemini_search_title_var.set(True)
            if artist_active:
                self.gemini_search_artist_var.set(True)
            if album_active:
                self.gemini_search_album_var.set(True)
            self._show_info_dialog(
                "Invalid Configuration",
                "At least one active field must be "
                "selected for Gemini to search. "
                "Fields have been re-enabled.")

    def _on_unorg_conditions_change(self):
        """
        Called when any unorganized condition checkbox
        changes.

        Two responsibilities:
        1. Block all-five-off by resetting to defaults.
        2. Sync the corresponding Gemini field toggle
           when artist/title/album conditions change:
           - Condition turned off → force Gemini field
             off and grey out its checkbox.
           - Condition turned back on → re-enable the
             Gemini field checkbox and restore it to True
             so the user can choose independently.
        """
        artist   = self.unorg_check_artist_var.get()
        title    = self.unorg_check_title_var.get()
        album    = self.unorg_check_album_var.get()
        filename = self.unorg_check_filename_var.get()
        cover    = self.unorg_check_cover_art_var.get()

        if not any([artist, title, album,
                    filename, cover]):
            # Reset to defaults
            self.unorg_check_artist_var.set(True)
            self.unorg_check_title_var.set(True)
            self.unorg_check_album_var.set(True)
            self.unorg_check_filename_var.set(True)
            self.unorg_check_cover_art_var.set(False)
            self._show_info_dialog(
                "Invalid Configuration",
                "At least one condition must be "
                "selected. Settings have been "
                "reset to defaults.")
            # Re-read after reset
            artist = True
            title  = True
            album  = True

        # Only sync Gemini checkboxes when strategy
        # is gemini — when tags_only, _on_strategy_change
        # already handles the greyed-out state and we
        # should not interfere with it
        is_gemini = (
            self.organize_strategy_var.get() == "gemini")

        # Artist
        if hasattr(self, "_gemini_artist_chk"):
            if not artist:
                self.gemini_search_artist_var.set(False)
                self._gemini_artist_chk.configure(
                    state="disabled")
            elif is_gemini:
                self.gemini_search_artist_var.set(True)
                self._gemini_artist_chk.configure(
                    state="normal")

        # Title
        if hasattr(self, "_gemini_title_chk"):
            if not title:
                self.gemini_search_title_var.set(False)
                self._gemini_title_chk.configure(
                    state="disabled")
            elif is_gemini:
                self.gemini_search_title_var.set(True)
                self._gemini_title_chk.configure(
                    state="normal")

        # Album
        if hasattr(self, "_gemini_album_chk"):
            if not album:
                self.gemini_search_album_var.set(False)
                self._gemini_album_chk.configure(
                    state="disabled")
            elif is_gemini:
                self.gemini_search_album_var.set(True)
                self._gemini_album_chk.configure(
                    state="normal")

        # Update visible columns in-place — no full rebuild needed.
        if hasattr(self, "unorg_tree"):
            self._refresh_unorg_displaycolumns()

    def _apply_table_theme(self):
        """
        Apply the current table_theme_var value to all
        active treeviews immediately.
        Affects: _all_files_tree, unorg_tree, and the
        review changes dialog treeview (handled at
        dialog build time via _get_tv_theme_colours).
        """
        from app.constants import (
            TV_DARK_ROW_EVEN,  TV_DARK_ROW_ODD,
            TV_DARK_TEXT,
            TV_DARK_DIRTY_BG,  TV_DARK_DIRTY_FG,
            TV_DARK_SUGGESTION_BG,
            TV_DARK_SUGGESTION_FG,
            TV_LIGHT_ROW_EVEN, TV_LIGHT_ROW_ODD,
            TV_LIGHT_TEXT,
            TV_LIGHT_DIRTY_BG, TV_LIGHT_DIRTY_FG,
            TV_LIGHT_SUGGESTION_BG,
            TV_LIGHT_SUGGESTION_FG,
        )
        is_light = self.table_theme_var.get() == "light"

        row_even      = TV_LIGHT_ROW_EVEN      if is_light else TV_DARK_ROW_EVEN
        row_odd       = TV_LIGHT_ROW_ODD       if is_light else TV_DARK_ROW_ODD
        text          = TV_LIGHT_TEXT          if is_light else TV_DARK_TEXT
        dirty_bg      = TV_LIGHT_DIRTY_BG      if is_light else TV_DARK_DIRTY_BG
        dirty_fg      = TV_LIGHT_DIRTY_FG      if is_light else TV_DARK_DIRTY_FG
        suggestion_bg = TV_LIGHT_SUGGESTION_BG if is_light else TV_DARK_SUGGESTION_BG
        suggestion_fg = TV_LIGHT_SUGGESTION_FG if is_light else TV_DARK_SUGGESTION_FG

        # --- All Files treeview ---
        if hasattr(self, "_all_files_tree") and \
                self._all_files_tree.winfo_exists():
            tree = self._all_files_tree
            tree.tag_configure(
                "even",
                background=row_even,
                foreground=text)
            tree.tag_configure(
                "odd",
                background=row_odd,
                foreground=text)
            tree.tag_configure(
                "dirty",
                background=dirty_bg,
                foreground=dirty_fg)
            tree.tag_configure(
                "even_dirty",
                background=dirty_bg,
                foreground=dirty_fg)
            tree.tag_configure(
                "odd_dirty",
                background=dirty_bg,
                foreground=dirty_fg)
            # Force a visual refresh by toggling
            # each row's tags in place
            for iid in tree.get_children(""):
                current = list(tree.item(iid, "tags"))
                tree.item(iid, tags=tuple(current))

        # --- Unorganized treeview ---
        if hasattr(self, "unorg_tree") and \
                self.unorg_tree.winfo_exists():
            tree = self.unorg_tree
            tree.tag_configure(
                "even",
                background=row_even,
                foreground=text)
            tree.tag_configure(
                "odd",
                background=row_odd,
                foreground=text)
            tree.tag_configure(
                "has_suggestion",
                background=suggestion_bg,
                foreground=suggestion_fg)
            for iid in tree.get_children(""):
                current = list(tree.item(iid, "tags"))
                tree.item(iid, tags=tuple(current))

    def _get_filename_replacements(self) -> dict:
        """
        Returns the current filename replacement mapping
        as a plain dict. Used by _sanitize_filename_part
        at runtime.
        """
        return {
            char: var.get()
            for char, var in
            self.filename_replacements_vars.items()
        }

    def _get_tv_theme_colours(self) -> dict:
        """
        Returns a dict of colour values for the current
        table theme. Used by treeview builders and the
        Review & Save Changes dialog to read the correct
        colours at build time.
        """
        from app.constants import (
            TV_DARK_ROW_EVEN,  TV_DARK_ROW_ODD,
            TV_DARK_TEXT,
            TV_DARK_DIRTY_BG,  TV_DARK_DIRTY_FG,
            TV_DARK_SUGGESTION_BG,
            TV_DARK_SUGGESTION_FG,
            TV_LIGHT_ROW_EVEN, TV_LIGHT_ROW_ODD,
            TV_LIGHT_TEXT,
            TV_LIGHT_DIRTY_BG, TV_LIGHT_DIRTY_FG,
            TV_LIGHT_SUGGESTION_BG,
            TV_LIGHT_SUGGESTION_FG,
        )
        is_light = self.table_theme_var.get() == "light"
        return {
            "row_even":      TV_LIGHT_ROW_EVEN      if is_light else TV_DARK_ROW_EVEN,
            "row_odd":       TV_LIGHT_ROW_ODD       if is_light else TV_DARK_ROW_ODD,
            "text":          TV_LIGHT_TEXT          if is_light else TV_DARK_TEXT,
            "dirty_bg":      TV_LIGHT_DIRTY_BG      if is_light else TV_DARK_DIRTY_BG,
            "dirty_fg":      TV_LIGHT_DIRTY_FG      if is_light else TV_DARK_DIRTY_FG,
            "suggestion_bg": TV_LIGHT_SUGGESTION_BG if is_light else TV_DARK_SUGGESTION_BG,
            "suggestion_fg": TV_LIGHT_SUGGESTION_FG if is_light else TV_DARK_SUGGESTION_FG,
        }

    # ------------------------------------------------------------------
    # Configuration overlay
    # ------------------------------------------------------------------
    def _build_config_overlay(self):
        self.config_view_frame = ctk.CTkFrame(
            self, corner_radius=0,
            fg_color="transparent")

        # _on_save_btn defined here so it can be
        # referenced by both the header Save button
        # and the Developer Tools logging switch.
        def _on_save_btn():
            self._save_config_overlay_state()

        # Fixed header — stays visible while scrolling
        header = ctk.CTkFrame(
            self.config_view_frame,
            fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 0))
        title_frame = ctk.CTkFrame(
            header, fg_color="transparent")
        title_frame.pack(side="left")
        ctk.CTkLabel(
            title_frame,
            text="Global Application Settings",
            font=("", 20, "bold"),
        ).pack(anchor="w")
        self._config_origin_lbl = ctk.CTkLabel(
            title_frame,
            text="",
            font=("", 11),
            text_color=TEXT_MUTED,
        )
        self._config_origin_lbl.pack(anchor="w")

        # Right side of header — Save then Close
        ctk.CTkButton(
            header, text="✕  Close", width=80,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=self._close_configuration_view,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            header, text="💾 Save",
            width=80,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=_on_save_btn,
        ).pack(side="right", padx=(0, 4))

        self._config_saved_label = ctk.CTkLabel(
            header, text="",
            text_color=SUCCESS_GREEN,
            font=("", 11))
        self._config_saved_label.pack(
            side="right", padx=(0, 8))

        # Scrollable content area — all settings go here
        inner = ctk.CTkScrollableFrame(
            self.config_view_frame)
        inner.pack(
            fill="both", expand=True,
            padx=0, pady=(10, 0))

        # ── Naming Convention ──────────────────────────
        ctk.CTkLabel(
            inner,
            text=(
                "Naming Convention for "
                "'Unorganized' Analysis:"),
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(10, 5))
        ctk.CTkOptionMenu(
            inner,
            values=[
                "Artist - Title",
                "Title - Artist"],
            variable=self.naming_convention_var,
            command=self._on_config_change,
            width=300,
        ).pack(anchor="w", padx=20, pady=(0, 20))

        # ── Fuzzy Threshold ───────────────────────────
        ctk.CTkLabel(
            inner,
            text="Fuzzy Match Percentage Threshold:",
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(10, 5))
        slider_row = ctk.CTkFrame(
            inner, fg_color="transparent")
        slider_row.pack(fill="x", padx=20)
        fuzzy_slider = ctk.CTkSlider(
            slider_row, from_=50.0, to=100.0,
            variable=self.fuzzy_threshold_var,
            command=self._on_fuzzy_slider_change)
        fuzzy_slider.pack(side="left")
        fuzzy_slider.bind(
            "<ButtonRelease-1>",
            self._fuzzy_threshold_release_cb)
        self.fuzzy_val_label = ctk.CTkLabel(
            slider_row,
            text=(
                f"{int(self.fuzzy_threshold_var.get())}"
                f"%"))
        self.fuzzy_val_label.pack(
            side="left", padx=10)

        # ── Fuzzy Matches — Collaboration Section ─────
        ctk.CTkLabel(
            inner,
            text="Fuzzy Matches — Collaboration Section:",
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(15, 5))

        collab_frame = ctk.CTkFrame(
            inner, fg_color="transparent")
        collab_frame.pack(
            anchor="w", padx=20, pady=(0, 6))

        ctk.CTkRadioButton(
            collab_frame,
            text="Show collaboration mismatches and normalization section",
            variable=self.fuzzy_show_collaboration_var,
            value=True,
            command=self._on_fuzzy_collab_toggle,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkRadioButton(
            collab_frame,
            text="Hide collaboration mismatches and normalization section",
            variable=self.fuzzy_show_collaboration_var,
            value=False,
            command=self._on_fuzzy_collab_toggle,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(20, 10))

        # ── Organize Strategy ─────────────────────────
        ctk.CTkLabel(
            inner,
            text="Organize Strategy:",
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(10, 5))
        ctk.CTkLabel(
            inner,
            text=(
                "Controls how files are organized in "
                "the Unorganized tab and how the "
                "Analyze button works throughout "
                "the app."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 10))

        strategy_frame = ctk.CTkFrame(
            inner, fg_color="transparent")
        strategy_frame.pack(
            anchor="w", padx=20, pady=(0, 6))

        ctk.CTkRadioButton(
            strategy_frame,
            text="Use Gemini AI",
            variable=self.organize_strategy_var,
            value="gemini",
            command=self._on_strategy_change,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            strategy_frame,
            text=(
                "Every file is sent to Gemini. "
                "Tags are verified and corrected "
                "by AI. The Analyze button is "
                "enabled."),
            font=("", 11),
            text_color=TEXT_MUTED,
            justify="left",
        ).pack(anchor="w", padx=(24, 0),
               pady=(0, 10))

        ctk.CTkRadioButton(
            strategy_frame,
            text="Use tags only",
            variable=self.organize_strategy_var,
            value="tags_only",
            command=self._on_strategy_change,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            strategy_frame,
            text=(
                "No Gemini calls. Files with known "
                "tags are renamed locally. Files "
                "with unknown tags are marked as "
                "unresolvable. The Analyze button "
                "uses local tags."),
            font=("", 11),
            text_color=TEXT_MUTED,
            justify="left",
        ).pack(anchor="w", padx=(24, 0),
               pady=(0, 4))

        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(10, 0))

        # ── Unorganized Conditions ────────────────────
        ctk.CTkLabel(
            inner,
            text="Unorganized Tab — Conditions:",
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(10, 5))

        ctk.CTkLabel(
            inner,
            text=(
                "A file is flagged as unorganized if "
                "any checked condition is true. "
                "Changes take effect immediately."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        unorg_frame = ctk.CTkFrame(
            inner, fg_color="transparent")
        unorg_frame.pack(
            anchor="w", padx=20, pady=(0, 6))

        ctk.CTkCheckBox(
            unorg_frame,
            text="Missing Artist tag",
            variable=self.unorg_check_artist_var,
            command=self._on_unorg_conditions_change,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkCheckBox(
            unorg_frame,
            text="Missing Title tag",
            variable=self.unorg_check_title_var,
            command=self._on_unorg_conditions_change,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkCheckBox(
            unorg_frame,
            text="Missing Album tag",
            variable=self.unorg_check_album_var,
            command=self._on_unorg_conditions_change,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkCheckBox(
            unorg_frame,
            text="Filename does not match tags",
            variable=self.unorg_check_filename_var,
            command=self._on_unorg_conditions_change,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkCheckBox(
            unorg_frame,
            text="Missing cover art",
            variable=self.unorg_check_cover_art_var,
            command=self._on_unorg_conditions_change,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(10, 0))

        # ── Gemini Field Selection ────────────────────
        ctk.CTkLabel(
            inner,
            text="Gemini — Fields to Search:",
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(10, 5))

        ctk.CTkLabel(
            inner,
            text=(
                "When Gemini is called, it will only "
                "search for the fields checked below. "
                "Unchecked fields are preserved from "
                "the current tags unchanged."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        gemini_fields_frame = ctk.CTkFrame(
            inner, fg_color="transparent")
        gemini_fields_frame.pack(
            anchor="w", padx=20, pady=(0, 6))

        self._gemini_title_chk = ctk.CTkCheckBox(
            gemini_fields_frame,
            text="Title",
            variable=self.gemini_search_title_var,
            command=self._on_gemini_fields_change,
        )
        self._gemini_title_chk.pack(
            anchor="w", pady=(0, 4))

        self._gemini_artist_chk = ctk.CTkCheckBox(
            gemini_fields_frame,
            text="Artist",
            variable=self.gemini_search_artist_var,
            command=self._on_gemini_fields_change,
        )
        self._gemini_artist_chk.pack(
            anchor="w", pady=(0, 4))

        self._gemini_album_chk = ctk.CTkCheckBox(
            gemini_fields_frame,
            text="Album",
            variable=self.gemini_search_album_var,
            command=self._on_gemini_fields_change,
        )
        self._gemini_album_chk.pack(
            anchor="w", pady=(0, 4))

        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(10, 0))

        # ── Table / Spreadsheet Theme ─────────────────
        ctk.CTkLabel(
            inner,
            text="Table / Spreadsheet Theme:",
            font=("", 14),
        ).pack(anchor="w", padx=20, pady=(10, 5))

        ctk.CTkLabel(
            inner,
            text=(
                "Controls the row colours for all "
                "treeviews (All Files, Unorganized, "
                "Review & Save Changes). "
                "Takes effect immediately."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        theme_frame = ctk.CTkFrame(
            inner, fg_color="transparent")
        theme_frame.pack(
            anchor="w", padx=20, pady=(0, 6))

        ctk.CTkRadioButton(
            theme_frame,
            text="Dark mode",
            variable=self.table_theme_var,
            value="dark",
            command=self._apply_table_theme,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkRadioButton(
            theme_frame,
            text="Light mode",
            variable=self.table_theme_var,
            value="light",
            command=self._apply_table_theme,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(10, 0))

        # ── Developer Tools ───────────────────────────
        ctk.CTkLabel(
            inner, text="Developer Tools",
            font=("", 15, "bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=20, pady=(10, 4))

        dev_gemini_row = ctk.CTkFrame(
            inner, fg_color="transparent")
        dev_gemini_row.pack(
            fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(
            dev_gemini_row,
            text=(
                "Log Gemini requests and responses "
                "to terminal:"),
            font=("", 13),
        ).pack(side="left")
        self._gemini_log_switch = ctk.CTkSwitch(
            dev_gemini_row, text="",
            variable=self.gemini_logging_var,
            onvalue=True, offvalue=False,
            command=_on_save_btn,
        )
        self._gemini_log_switch.pack(
            side="left", padx=12)
        ctk.CTkLabel(
            dev_gemini_row,
            text=(
                "(takes effect immediately — "
                "no restart needed)"),
            text_color=TEXT_MUTED, font=("", 11),
        ).pack(side="left")

        # ── Filename Character Replacements ───────────
        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(16, 0))

        ctk.CTkLabel(
            inner,
            text="Filename Character Replacements:",
            font=("", 13),
        ).pack(anchor="w", padx=20, pady=(10, 2))

        ctk.CTkLabel(
            inner,
            text=(
                "Each forbidden filename character and "
                "its replacement. Leave blank to remove "
                "the character entirely. Replacement "
                "cannot itself be a forbidden character."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        from app.constants import \
            FILENAME_REPLACEMENTS_DEFAULT
        from app.config import _load_config as \
            _load_cfg_for_revert

        _forbidden_set = set(
            FILENAME_REPLACEMENTS_DEFAULT.keys())

        repl_frame = ctk.CTkFrame(
            inner, fg_color="transparent")
        repl_frame.pack(
            anchor="w", padx=20, pady=(0, 6))

        _repl_entries: dict = {}

        for char in FILENAME_REPLACEMENTS_DEFAULT:
            row = ctk.CTkFrame(
                repl_frame, fg_color="transparent")
            row.pack(anchor="w", pady=2)

            display = {
                "\\": "backslash  \\",
                "\"": 'quote  "',
            }.get(char, char)

            ctk.CTkLabel(
                row,
                text=f"  {display}  →",
                font=("Courier", 12),
                width=120,
                anchor="w",
            ).pack(side="left")

            entry = ctk.CTkEntry(
                row,
                textvariable=(
                    self.filename_replacements_vars[
                        char]),
                width=80,
                font=("Courier", 12))
            entry.pack(side="left", padx=(4, 0))
            _repl_entries[char] = entry

        repl_btn_row = ctk.CTkFrame(
            inner, fg_color="transparent")
        repl_btn_row.pack(
            fill="x", padx=20, pady=(6, 0))

        def _on_save_replacements():
            errors = []
            for char, var in \
                    self.filename_replacements_vars\
                    .items():
                val = var.get()
                for fc in _forbidden_set:
                    if fc in val:
                        errors.append(
                            f"'{char}' replacement "
                            f"contains forbidden "
                            f"character '{fc}'")
                        break
            if errors:
                _repl_status_lbl.configure(
                    text=(
                        "⚠ " + errors[0]
                        + ". Not saved."),
                    text_color=WARNING_YELLOW)
                saved = _load_cfg_for_revert().get(
                    "filename_replacements", {})
                for char in \
                        self.filename_replacements_vars:
                    default = \
                        FILENAME_REPLACEMENTS_DEFAULT[
                            char]
                    current = saved.get(char, default)
                    val = self\
                        .filename_replacements_vars[
                            char].get()
                    for fc in _forbidden_set:
                        if fc in val:
                            self\
                                .filename_replacements_vars[
                                    char].set(current)
                            break
                return
            _save_config(self._current_config_dict())
            self._sync_config_open_state_to_current()
            _repl_status_lbl.configure(
                text="✓ Replacements saved.",
                text_color=SUCCESS_GREEN)
            self.after(
                2000, lambda:
                _repl_status_lbl.configure(text=""))

        def _on_restore_replacements():
            for char, default_val in \
                    FILENAME_REPLACEMENTS_DEFAULT\
                    .items():
                self.filename_replacements_vars[
                    char].set(default_val)
            _save_config(self._current_config_dict())
            self._sync_config_open_state_to_current()
            _repl_status_lbl.configure(
                text="✓ Restored to defaults.",
                text_color=SUCCESS_GREEN)
            self.after(
                2000, lambda:
                _repl_status_lbl.configure(text=""))

        ctk.CTkButton(
            repl_btn_row,
            text="💾 Save Replacements",
            width=150,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=_on_save_replacements,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            repl_btn_row,
            text="↺ Restore Defaults",
            width=130,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=_on_restore_replacements,
        ).pack(side="left")

        _repl_status_lbl = ctk.CTkLabel(
            inner, text="",
            text_color=SUCCESS_GREEN,
            font=("", 11))
        _repl_status_lbl.pack(
            anchor="w", padx=20, pady=(4, 0))

        # ── Custom Gemini Prompt ──────────────────────
        ctk.CTkFrame(
            inner, height=1, fg_color="gray40",
        ).pack(fill="x", padx=20, pady=(16, 0))

        ctk.CTkLabel(
            inner,
            text="Custom Gemini Prompt:",
            font=("", 13),
        ).pack(anchor="w", padx=20, pady=(10, 2))

        ctk.CTkLabel(
            inner,
            text=(
                "Edit the static instruction text sent "
                "to Gemini. The tokens {fields_str}, "
                "{naming}, and {preserve_block} are "
                "replaced automatically at runtime — "
                "keep them in place. The file data is "
                "always appended after this text."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 6))

        # Resolve the displayed value — show the saved
        # custom prompt if one exists, otherwise show
        # the default so the user has a starting point.
        from app.constants import GEMINI_DEFAULT_PROMPT

        _displayed_prompt = (
            self.gemini_prompt_var.get()
            if self.gemini_prompt_var.get().strip()
            else GEMINI_DEFAULT_PROMPT)

        self._prompt_textbox = ctk.CTkTextbox(
            inner,
            height=260,
            wrap="word",
            font=("Courier", 11))
        self._prompt_textbox.pack(
            fill="x", padx=20, pady=(0, 6))
        self._prompt_textbox.insert("1.0", _displayed_prompt)

        prompt_btn_row = ctk.CTkFrame(
            inner, fg_color="transparent")
        prompt_btn_row.pack(
            fill="x", padx=20, pady=(0, 4))

        self._prompt_saved_lbl = ctk.CTkLabel(
            prompt_btn_row, text="",
            text_color=SUCCESS_GREEN,
            font=("", 11))
        self._prompt_saved_lbl.pack(
            side="right", padx=(10, 0))

        def _on_restore_default():
            self._prompt_textbox.delete("1.0", "end")
            self._prompt_textbox.insert(
                "1.0", GEMINI_DEFAULT_PROMPT)
            # Clear the saved custom prompt so the
            # default is used at runtime
            self.gemini_prompt_var.set("")
            _save_config(self._current_config_dict())
            self._sync_config_open_state_to_current()
            self._prompt_saved_lbl.configure(
                text="✓ Restored to default.")
            self.after(
                2000, lambda:
                self._prompt_saved_lbl.configure(
                    text=""))

        def _on_save_prompt():
            text = self._prompt_textbox.get(
                "1.0", "end").strip()
            if text == GEMINI_DEFAULT_PROMPT.strip():
                # User saved the default unchanged —
                # store as blank to keep config clean
                self.gemini_prompt_var.set("")
            else:
                self.gemini_prompt_var.set(text)
            _save_config(self._current_config_dict())
            self._sync_config_open_state_to_current()
            self._prompt_saved_lbl.configure(
                text="✓ Prompt saved.")
            self.after(
                2000, lambda:
                self._prompt_saved_lbl.configure(
                    text=""))

        def _on_cancel_prompt():
            # Revert textbox to last saved state
            # without saving
            current_saved = self.gemini_prompt_var.get()
            reverted = (
                current_saved.strip()
                if current_saved.strip()
                else GEMINI_DEFAULT_PROMPT)
            self._prompt_textbox.delete("1.0", "end")
            self._prompt_textbox.insert("1.0", reverted)
            self._prompt_saved_lbl.configure(
                text="✓ Changes discarded.")
            self.after(
                2000, lambda:
                self._prompt_saved_lbl.configure(
                    text=""))

        ctk.CTkButton(
            prompt_btn_row,
            text="💾 Save Prompt",
            width=120,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=_on_save_prompt,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            prompt_btn_row,
            text="Cancel",
            width=90,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=_on_cancel_prompt,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            prompt_btn_row,
            text="↺ Restore Default",
            width=130,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=_on_restore_default,
        ).pack(side="left")

        # Set initial state of all dependent controls.
        # _on_unorg_conditions_change first so condition-
        # based grey-outs are applied, then
        # _on_strategy_change applies strategy-based
        # grey-outs on top. Order matters.
        self._on_unorg_conditions_change()
        self._on_strategy_change()

    def _open_configuration_view(self):
        self._config_open_state = self._capture_config_view_state()
        self._config_origin_tab = self._active_tab
        if hasattr(self, "_config_origin_lbl"):
            self._config_origin_lbl.configure(
                text=f"Returning to: {self._config_origin_tab}")
        self._tab_content.grid_remove()
        self.config_view_frame.grid(
            row=3, column=1, sticky="nsew",
            padx=10, pady=10)
        # Deactivate all tab buttons visually so none
        # appears highlighted while config is open
        for btn in self._tab_buttons.values():
            btn.configure(
                fg_color="transparent",
                text_color=TEXT_DISABLED)

    def _close_configuration_view(self):
        if self._has_unsaved_config_changes():
            dialog = ctk.CTkToplevel(self)
            dialog.title("Unsaved Configuration")
            dialog.resizable(False, False)
            dialog.grab_set()
            self._center_dialog(dialog, 430, 190)

            ctk.CTkLabel(
                dialog,
                text="Save configuration changes before closing?",
                font=("", 14, "bold"),
                wraplength=390,
            ).pack(pady=(22, 8), padx=20)

            ctk.CTkLabel(
                dialog,
                text=(
                    "Some configuration changes apply immediately in the UI, "
                    "but are not persisted until you save them."),
                font=("", 11),
                text_color=TEXT_MUTED,
                wraplength=390,
                justify="left",
            ).pack(pady=(0, 16), padx=20)

            btn_row = ctk.CTkFrame(
                dialog, fg_color="transparent")
            btn_row.pack(pady=(0, 16))

            def _save_and_close():
                self._save_config_overlay_state()
                dialog.destroy()
                self._close_configuration_view()

            def _discard_and_close():
                state = dict(self._config_open_state)
                dialog.destroy()
                self._restore_config_view_state(state)
                self._close_configuration_view()

            ctk.CTkButton(
                btn_row,
                text="Save",
                width=100,
                fg_color=SAVE_BLUE,
                hover_color=SAVE_BLUE_HOVER,
                command=_save_and_close,
            ).pack(side="left", padx=6)
            ctk.CTkButton(
                btn_row,
                text="Discard",
                width=100,
                fg_color=DANGER_RED,
                hover_color=DANGER_RED_HOVER,
                command=_discard_and_close,
            ).pack(side="left", padx=6)
            ctk.CTkButton(
                btn_row,
                text="Cancel",
                width=100,
                fg_color=CANCEL_BG,
                hover_color=CANCEL_BG_HOVER,
                text_color=TEXT_ADAPTIVE,
                command=dialog.destroy,
            ).pack(side="left", padx=6)
            return

        self.config_view_frame.grid_remove()
        self._tab_content.grid(
            row=3, column=1, sticky="nsew")
        # Restore the active tab button highlight
        self._switch_tab(
            self._active_tab, clear_sidebar=False)

    def _on_fuzzy_collab_toggle(self):
        self._fuzzy_stale = True
        self._populate_fuzzy_tab()

