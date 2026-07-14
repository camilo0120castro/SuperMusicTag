# app/ui_sidebar.py
"""
SidebarMixin — all sidebar-related methods.
"""
import os
import io
import copy
import threading


import customtkinter as ctk


from app.constants import (
    _COMBO_BTN_HIDDEN, _COMBO_BTN_VISIBLE,
    ORANGE_PRIMARY, ORANGE_HOVER, SUCCESS_GREEN,
    WARNING_YELLOW, DANGER_RED, DANGER_RED_HOVER,
    TEXT_ADAPTIVE, TEXT_MUTED,
    CANCEL_BG, CANCEL_BG_HOVER,
    _COVER_SIZE,
)
from app.helpers import (
    _PILLOW_AVAILABLE, _PILImage, _extract_cover_art_bytes,
    _validate_new_filename, _sanitize_filename_part,
)




class SidebarMixin:
    _MULTI_KEEP     = "<keep>"
    _MULTI_REMOVE   = "<remove>"
    _MULTI_FILENAME = "<multiple>"


    # ------------------------------------------------------------------
    # Blank cover image helper
    # ------------------------------------------------------------------
    def _get_blank_cover_image(self) -> ctk.CTkImage:
        """
        Returns a 1×1 transparent CTkImage used to reliably
        clear the cover label display. Created once and cached.


        In CTk 5.x, configure(image=None) does not actually
        clear the displayed image. Passing a real CTkImage
        (even a blank one) forces CTk to replace the internal
        label's image properly.
        """
        if self._blank_cover_image is None:
            if _PILLOW_AVAILABLE:
                blank = _PILImage.new(
                    "RGBA", (1, 1), (0, 0, 0, 0))
                self._blank_cover_image = ctk.CTkImage(
                    light_image=blank,
                    dark_image=blank,
                    size=(1, 1))
            else:
                self._blank_cover_image = None
        return self._blank_cover_image


    # ------------------------------------------------------------------
    # Build sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        self._status_clear_id: str | None = None

        sidebar = ctk.CTkFrame(
            self, width=260, corner_radius=0)
        sidebar.grid(row=3, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # Pin bottom widgets directly on sidebar FIRST
        # so they are always visible regardless of
        # scroll position. Pack order matters in tkinter
        # — bottom-packed widgets must be packed before
        # fill/expand widgets to ensure correct layout.
        self.status_bar_lbl = ctk.CTkLabel(
            sidebar, text="",
            text_color=TEXT_MUTED,
            font=("", 10), anchor="w")
        self.status_bar_lbl.pack(
            side="bottom", fill="x",
            padx=10, pady=(0, 4))

        ctk.CTkButton(
            sidebar, text="⚙ Configuration",
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._open_configuration_view,
        ).pack(side="bottom", fill="x",
               padx=10, pady=(0, 6))

        # Scrollable content area — all other sidebar
        # widgets go inside this frame.
        scroll_area = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            corner_radius=0,
            width=242)
        scroll_area.pack(
            side="top", fill="both", expand=True)

        # All content widgets go into scroll_area
        # instead of directly into sidebar.
        ctk.CTkLabel(
            scroll_area, text="Active Track",
            font=("", 18, "bold"),
        ).pack(pady=(12, 6))

        self.cover_lbl = ctk.CTkLabel(
            scroll_area, text="",
            width=150, height=150,
            fg_color="gray30",
            cursor="hand2")
        self.cover_lbl.pack(pady=5, padx=12)
        self.cover_lbl.bind(
            "<Double-1>",
            self._on_cover_double_click)

        ctk.CTkLabel(
            scroll_area, text="Filename:",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(6, 0))
        self.meta_filename_var   = ctk.StringVar()
        self.meta_filename_entry = ctk.CTkEntry(
            scroll_area,
            textvariable=self.meta_filename_var,
            state="disabled")
        self.meta_filename_entry.pack(
            fill="x", padx=12, pady=(0, 5))

        self.meta_title_var  = ctk.StringVar()
        self.meta_artist_var = ctk.StringVar()
        self.meta_album_var  = ctk.StringVar()

        for label, var, key in [
                ("Title:",  self.meta_title_var,  "title"),
                ("Artist:", self.meta_artist_var, "artist"),
                ("Album:",  self.meta_album_var,  "album")]:
            ctk.CTkLabel(
                scroll_area, text=label, anchor="w",
            ).pack(fill="x", padx=12, pady=(2, 0))
            combo = ctk.CTkComboBox(
                scroll_area, variable=var, values=[],
                state="normal",
                button_color=_COMBO_BTN_HIDDEN[0],
                button_hover_color=_COMBO_BTN_HIDDEN[1])
            combo.pack(
                fill="x", padx=12, pady=(0, 5))
            self._field_combos[key] = combo

        btn_row = ctk.CTkFrame(
            scroll_area, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(10, 0))

        self.save_metadata_btn = ctk.CTkButton(
            btn_row, text="Save Changes",
            state="disabled",
            command=self._save_metadata)
        self.save_metadata_btn.pack(
            side="left", expand=True, fill="x",
            padx=(0, 3))

        self.analyze_track_btn = ctk.CTkButton(
            btn_row, text="Analyze",
            state="disabled",
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            command=self._analyze_single_track)
        self.analyze_track_btn.pack(
            side="left", expand=True, fill="x",
            padx=(3, 0))

        # ── Tab traversal ──────────────────────────────
        def _tab_to(from_w, to_w):
            def _forward(e):
                to_w.focus_set()
                return "break"
            def _backward(e):
                from_w.focus_set()
                return "break"
            from_w.bind("<Tab>",       _forward,  add="+")
            to_w.bind(  "<Shift-Tab>", _backward, add="+")

        title_inner  = self._field_combos["title"]._entry
        artist_inner = self._field_combos["artist"]._entry
        album_inner  = self._field_combos["album"]._entry

        _tab_to(self.meta_filename_entry._entry,
                title_inner)
        _tab_to(title_inner,  artist_inner)
        _tab_to(artist_inner, album_inner)
        _tab_to(album_inner,  self.save_metadata_btn)

        for _w in (title_inner, artist_inner, album_inner):
            _w.bind("<Return>",
                    lambda e: self._save_metadata(),
                    add="+")

        for _w in (self.meta_filename_entry._entry,
                   title_inner, artist_inner, album_inner):
            _w.bind("<Key>",
                    self._clear_sidebar_status_on_edit,
                    add="+")

        self.multi_hint_header_lbl = ctk.CTkLabel(
            scroll_area, text="",
            text_color=TEXT_ADAPTIVE,
            font=("", 12, "bold"),
            wraplength=210,
            justify="center", anchor="center")
        self.multi_hint_header_lbl.pack(
            fill="x", padx=6, pady=(0, 2))

        self.multi_hint_lbl = ctk.CTkLabel(
            scroll_area, text="",
            text_color=TEXT_ADAPTIVE,
            font=("", 12), wraplength=210,
            justify="left", anchor="w")
        self.multi_hint_lbl.pack(
            fill="x", padx=6, pady=(0, 4))

        self.sidebar_status_lbl = ctk.CTkLabel(
            scroll_area, text="",
            text_color=SUCCESS_GREEN, font=("", 11))
        self.sidebar_status_lbl.pack(
            fill="x", padx=6, pady=(0, 2))


    # ------------------------------------------------------------------
    # Sidebar field population helpers
    # ------------------------------------------------------------------
    def _set_sidebar_single(self, rec: dict):
        self.meta_filename_var.set(
            rec.get("filename", ""))
        self.meta_filename_entry.configure(
            state="normal")
        self.meta_title_var.set(rec["title"])
        self.meta_artist_var.set(rec["artist"])
        self.meta_album_var.set(rec["album"])

        for key, combo in self._field_combos.items():
            current = rec.get(key, "")
            # Single file: no <keep> option — the user
            # is either changing the value or leaving
            # the field untouched. Sentinel values at
            # top, current value below.
            opts = [self._MULTI_REMOVE]
            if current:
                opts.append(current)
            combo.configure(
                values=opts,
                button_color=_COMBO_BTN_VISIBLE[0],
                button_hover_color=_COMBO_BTN_VISIBLE[1])


    def _set_sidebar_multi(self, selected_paths: list,
                            records: dict):
        self.meta_filename_var.set(self._MULTI_FILENAME)
        self.meta_filename_entry.configure(
            state="disabled")


        titles  = [
            records[p]["title"]
            for p in selected_paths if p in records]
        artists = [
            records[p]["artist"]
            for p in selected_paths if p in records]
        albums  = [
            records[p]["album"]
            for p in selected_paths if p in records]


        def _opts(values: list) -> list:
            unique = list(dict.fromkeys(values))
            return (
                [self._MULTI_KEEP, self._MULTI_REMOVE]
                + unique)


        self.meta_title_var.set(self._MULTI_KEEP)
        self.meta_artist_var.set(self._MULTI_KEEP)
        self.meta_album_var.set(self._MULTI_KEEP)


        self._field_combos["title"].configure(
            values=_opts(titles),
            button_color=_COMBO_BTN_VISIBLE[0],
            button_hover_color=_COMBO_BTN_VISIBLE[1])
        self._field_combos["artist"].configure(
            values=_opts(artists),
            button_color=_COMBO_BTN_VISIBLE[0],
            button_hover_color=_COMBO_BTN_VISIBLE[1])
        self._field_combos["album"].configure(
            values=_opts(albums),
            button_color=_COMBO_BTN_VISIBLE[0],
            button_hover_color=_COMBO_BTN_VISIBLE[1])


    # ------------------------------------------------------------------
    # Cover art
    # ------------------------------------------------------------------
    def _display_cover_art(self, path: str):
        if not _PILLOW_AVAILABLE:
            self._set_cover_text("")
            return
        self._set_cover_text("⏳")
        self._cover_load_generation += 1
        my_generation = self._cover_load_generation
        target_path   = path


        def _worker():
            raw = _extract_cover_art_bytes(target_path)
            self.after(
                0, lambda: self._on_cover_loaded(
                    raw, my_generation))


        threading.Thread(
            target=_worker, daemon=True).start()


    def _on_cover_loaded(self, raw: bytes | None,
                          generation: int):
        if generation != self._cover_load_generation:
            return
        if raw is None:
            self._set_cover_text("[No Cover Art]")
            return
        try:
            img = (
                _PILImage.open(io.BytesIO(raw))
                .convert("RGB"))
            img     = img.resize(
                _COVER_SIZE, _PILImage.LANCZOS)
            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img,
                size=_COVER_SIZE)
            self.cover_lbl.configure(
                image=ctk_img, text="")
            self.cover_lbl._cover_image_ref = ctk_img
        except Exception:
            self._set_cover_text("[No Cover Art]")


    def _set_cover_text(self, text: str):
        """
        Reliably clear the cover label and show text.


        In CTk 5.x, configure(image=None) does NOT clear
        the displayed image. We pass a cached 1×1 blank
        CTkImage to force CTk to replace it properly.
        """
        blank = self._get_blank_cover_image()
        try:
            if blank is not None:
                self.cover_lbl.configure(
                    image=blank, text=text)
            else:
                self.cover_lbl.configure(text=text)
        except Exception:
            try:
                self.cover_lbl.configure(text=text)
            except Exception:
                pass
        if hasattr(self.cover_lbl, "_cover_image_ref"):
            self.cover_lbl._cover_image_ref = None
            del self.cover_lbl._cover_image_ref

    def _on_cover_double_click(self, _event=None):
        """
        Opens the CoverArtDialog for the currently
        active track. Only available when a single
        file is selected in the All Files tab.
        """
        path = self._sidebar_active_path
        if not path:
            return
        rec = self.all_files_data.get(path)
        if not rec:
            return

        from app.ui_cover_art import CoverArtDialog

        def _after_save(saved_path: str,
                         image_bytes: bytes):
            """
            Called by CoverArtDialog after a
            successful disk write.
            Updates has_cover_art in the record
            and refreshes the sidebar display.
            """
            rec = self.all_files_data.get(
                saved_path)
            if rec:
                rec["has_cover_art"] = True
            # Reload the sidebar cover display
            self._display_cover_art(saved_path)
            self._set_sidebar_status(
                "✔ Cover art saved.",
                SUCCESS_GREEN)

        CoverArtDialog(
            parent=self,
            path=path,
            rec=rec,
            on_save=_after_save)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _update_status_bar(self):
        total    = len(self.all_files_data)
        modified = len(self._dirty_paths)
        if total == 0:
            self.status_bar_lbl.configure(text="")
            return
        parts = [f"{total} file(s)"]
        if modified:
            parts.append(f"{modified} modified")
        self.status_bar_lbl.configure(
            text="  |  ".join(parts))


    def _set_sidebar_status(self, text: str,
                             colour: str,
                             persist: bool | None = None):
        self.sidebar_status_lbl.configure(
            text=text, text_color=colour)
        # Cancel any existing auto-clear timer
        if hasattr(self, "_status_clear_id") and \
                self._status_clear_id is not None:
            try:
                self.after_cancel(self._status_clear_id)
            except Exception:
                pass
            self._status_clear_id = None
        # Errors persist until the user edits; success auto-clears
        should_persist = (
            persist if persist is not None
            else colour in (DANGER_RED, WARNING_YELLOW))
        if not should_persist:
            self._status_clear_id = self.after(
                5000,
                lambda: self.sidebar_status_lbl.configure(
                    text=""))
        else:
            self._status_clear_id = None

    def _clear_sidebar_status_on_edit(self, *_):
        """Clear the status label on the next keystroke in a sidebar field."""
        if hasattr(self, "sidebar_status_lbl"):
            self.sidebar_status_lbl.configure(text="")


    # ------------------------------------------------------------------
    # Clear sidebar
    # ------------------------------------------------------------------
    def _clear_sidebar(self):
        self.meta_filename_var.set("")
        self.meta_filename_entry.configure(
            state="disabled")
        self.meta_title_var.set("")
        self.meta_artist_var.set("")
        self.meta_album_var.set("")
        for combo in self._field_combos.values():
            combo.configure(
                values=[],
                button_color=_COMBO_BTN_HIDDEN[0],
                button_hover_color=_COMBO_BTN_HIDDEN[1])
        self.save_metadata_btn.configure(
            state="disabled",
            text="Save Changes")
        self._sidebar_context = "all_files"
        self.analyze_track_btn.configure(
            state="disabled")
        self._set_cover_text("")
        self._sidebar_active_path    = None
        self._sidebar_selected_paths = []
        self.multi_hint_header_lbl.configure(
            text="", text_color=TEXT_ADAPTIVE)
        self.multi_hint_lbl.configure(
            text="", text_color=TEXT_ADAPTIVE)


    # ------------------------------------------------------------------
    # Save metadata
    # ------------------------------------------------------------------
    def _save_metadata(self):
        paths = self._sidebar_selected_paths


        # ----------------------------------------------------------
        # Single-file path
        # ----------------------------------------------------------
        if len(paths) == 1:
            path = paths[0]

            if self._sidebar_context == "unorg_suggestion":
                self._save_metadata_as_suggestion(path)
                return

            if path not in self.all_files_data:
                return


            new_filename = (
                self.meta_filename_var.get().strip())
            new_title    = (
                self.meta_title_var.get().strip())
            new_artist   = (
                self.meta_artist_var.get().strip())
            new_album    = (
                self.meta_album_var.get().strip())
            rec          = self.all_files_data[path]


            filename_changed = (
                bool(new_filename) and
                new_filename != rec["filename"])
            ext_warning: str | None = None


            if filename_changed:
                valid, msg = _validate_new_filename(
                    new_filename, rec["filename"])
                if not valid:
                    self._set_sidebar_status(
                        f"⚠ {msg}", DANGER_RED)
                    return
                ext_warning = msg


            # Resolve <remove> sentinel to empty string
            if new_title  == self._MULTI_REMOVE:
                new_title  = ""
            if new_artist == self._MULTI_REMOVE:
                new_artist = ""
            if new_album  == self._MULTI_REMOVE:
                new_album  = ""

            title_changed  = rec["title"]  != new_title
            artist_changed = rec["artist"] != new_artist
            tags_changed   = (
                title_changed  or
                artist_changed or
                rec["album"]   != new_album)


            if not filename_changed and not tags_changed:
                self._set_sidebar_status(
                    "No changes to save.",
                    WARNING_YELLOW)
                return


            self._snapshot_original(path)
            self._push_undo_snapshot()


            if filename_changed:
                rec["filename"] = new_filename
            rec["title"]  = new_title
            rec["artist"] = new_artist
            rec["album"]  = new_album


            self.distinct_artists = {
                r["artist"]
                for r in self.all_files_data.values()
                if r["artist"] not in ("Unknown", "")
            }
            self._dirty_paths.add(path)
            self._fuzzy_stale = True
            self._invalidate_unorg_cache()

            if self._scanned_unorganized:
                self._sync_unorganized_after_record_changes(
                    [path])


            self._update_tree_row(path, rec)


            if ext_warning:
                status_text   = (
                    f"✔ Saved. {ext_warning}")
                status_colour = WARNING_YELLOW
            else:
                status_text   = "✔ Saved."
                status_colour = SUCCESS_GREEN
            self._set_sidebar_status(
                status_text, status_colour)


            self._update_status_bar()
            self._update_unsaved_banner()

            # Ask about filename rebuild if title
            # or artist changed — but only if the
            # user did not also manually set the
            # filename in this same save operation
            if (title_changed or artist_changed) \
                    and not filename_changed:
                self._show_filename_rebuild_notification(
                    path)

            return


        # ----------------------------------------------------------
        # Multi-file path
        # ----------------------------------------------------------
        if len(paths) < 2:
            return

        if self._sidebar_context == "unorg_suggestion":
            self._save_metadata_as_suggestion_multi()
            return

        new_title  = self.meta_title_var.get().strip()
        new_artist = self.meta_artist_var.get().strip()
        new_album  = self.meta_album_var.get().strip()


        apply_title  = new_title  not in (
            self._MULTI_KEEP, "")
        apply_artist = new_artist not in (
            self._MULTI_KEEP, "")
        apply_album  = new_album  not in (
            self._MULTI_KEEP, "")
        remove_title  = new_title  == self._MULTI_REMOVE
        remove_artist = new_artist == self._MULTI_REMOVE
        remove_album  = new_album  == self._MULTI_REMOVE


        if not any([
                apply_title,  apply_artist,  apply_album,
                remove_title, remove_artist, remove_album]):
            self._set_sidebar_status(
                "No changes to save.", WARNING_YELLOW)
            return


        self._push_undo_snapshot()
        changed = 0
        changed_paths: list[str] = []


        for path in paths:
            rec = self.all_files_data.get(path)
            if rec is None:
                continue
            self._snapshot_original(path)
            file_changed = False
            if apply_title or remove_title:
                new_val = "" if remove_title else new_title
                if rec["title"] != new_val:
                    rec["title"] = new_val
                    file_changed = True
            if apply_artist or remove_artist:
                new_val = "" if remove_artist else new_artist
                if rec["artist"] != new_val:
                    rec["artist"] = new_val
                    file_changed = True
            if apply_album or remove_album:
                new_val = "" if remove_album else new_album
                if rec["album"] != new_val:
                    rec["album"] = new_val
                    file_changed = True
            if file_changed:
                self._dirty_paths.add(path)
                self._fuzzy_stale = True
                self._update_tree_row(path, rec)
                changed_paths.append(path)
                changed += 1

        if changed == 0:
            self._set_sidebar_status(
                "No actual changes were applied.",
                WARNING_YELLOW)
            return


        self.distinct_artists = {
            r["artist"]
            for r in self.all_files_data.values()
            if r["artist"] not in ("Unknown", "")
        }
        self._invalidate_unorg_cache()

        if self._scanned_unorganized:
            self._sync_unorganized_after_record_changes(
                changed_paths)


        self._set_sidebar_status(
            f"✔ Saved {changed} file(s).",
            SUCCESS_GREEN)
        self._update_status_bar()
        self._update_unsaved_banner()

        # Ask about filename rebuild for each file
        # where title or artist was changed.
        if apply_title or apply_artist or \
                remove_title or remove_artist:
            self._show_filename_rebuild_notifications(
                changed_paths)


    def _save_metadata_as_suggestion(self, path: str):
        """
        Single-file path: updates _proposed_changes
        for one file.
        Called from _save_metadata when one unorganized
        file is selected.
        """
        new_filename = (
            self.meta_filename_var.get().strip())
        new_title    = (
            self.meta_title_var.get().strip())
        new_artist   = (
            self.meta_artist_var.get().strip())
        new_album    = (
            self.meta_album_var.get().strip())

        _invalid = {
            "",
            self._MULTI_KEEP,
            self._MULTI_FILENAME,
            "<multiple>",
        }

        base = (
            copy.deepcopy(
                self._proposed_changes[path])
            if path in self._proposed_changes
            else copy.deepcopy(
                self._scanned_unorganized[path]))

        changed     = False
        ext_warning: str | None = None

        # Track fields explicitly cleared via <remove>
        # before resolving to empty string, so we can
        # distinguish "user cleared" from "left blank"
        title_cleared  = new_title  == self._MULTI_REMOVE
        artist_cleared = new_artist == self._MULTI_REMOVE
        album_cleared  = new_album  == self._MULTI_REMOVE

        if new_title  == self._MULTI_REMOVE:
            new_title  = ""
        if new_artist == self._MULTI_REMOVE:
            new_artist = ""
        if new_album  == self._MULTI_REMOVE:
            new_album  = ""

        if (new_filename not in _invalid and
                new_filename != base.get(
                    "filename", "")):
            valid, msg = _validate_new_filename(
                new_filename,
                base.get("filename", ""))
            if not valid:
                self._set_sidebar_status(
                    f"⚠ {msg}", DANGER_RED)
                return
            ext_warning      = msg
            base["filename"] = new_filename
            changed          = True

        if (title_cleared or
                (new_title not in _invalid and
                 new_title != base.get("title", ""))):
            base["title"] = new_title
            changed       = True

        if (artist_cleared or
                (new_artist not in _invalid and
                 new_artist != base.get("artist", ""))):
            base["artist"] = new_artist
            changed        = True

        if (album_cleared or
                (new_album not in _invalid and
                 new_album != base.get("album", ""))):
            base["album"] = new_album
            changed       = True

        if not changed:
            self._set_sidebar_status(
                "No changes to save.", WARNING_YELLOW)
            return

        base["confidence"] = "manual"
        self._proposed_changes[path] = base

        if new_filename in _invalid:
            self._rebuild_suggested_filename(path)

        self._update_unorg_row(path)

        if ext_warning:
            status_text   = (
                f"✔ Suggestion updated. {ext_warning}")
            status_colour = WARNING_YELLOW
        else:
            status_text   = (
                "✔ Suggestion updated in Unorganized tab.")
            status_colour = SUCCESS_GREEN
        self._set_sidebar_status(
            status_text, status_colour)

    def _save_metadata_as_suggestion_multi(self):
        """
        Multi-file path: updates _proposed_changes for
        all currently selected unorganized files.
        Only applies fields that are not <multiple>
        and not blank. Only files that already have a
        proposal are updated. Files without a proposal
        are skipped (Option B).
        Filename is rebuilt from new artist + existing
        proposed title where possible.
        """
        new_artist = self.meta_artist_var.get().strip()
        new_album  = self.meta_album_var.get().strip()

        _invalid = {
            "",
            "<multiple>",
            self._MULTI_KEEP,
            self._MULTI_REMOVE,
        }

        apply_artist = new_artist not in _invalid
        apply_album  = new_album  not in _invalid

        if not apply_artist and not apply_album:
            self._set_sidebar_status(
                "No changes to save.", WARNING_YELLOW)
            return

        paths = self._sidebar_selected_paths
        changed = 0
        skipped = 0

        for path in paths:
            if path not in self._proposed_changes:
                # Skip files with no proposal (Option B)
                skipped += 1
                continue

            proposal = self._proposed_changes[path]

            if apply_artist:
                proposal["artist"] = new_artist
            if apply_album:
                proposal["album"] = new_album

            proposal["confidence"] = "manual"

            # Rebuild filename from new artist +
            # existing proposed title if both are known.
            # If title is missing, leave filename as-is.
            if apply_artist:
                self._rebuild_suggested_filename(path)

            self._update_unorg_row(path)
            changed += 1

        if changed:
            suffix = (
                f" Skipped {skipped} file(s) with no "
                f"existing suggestion."
                if skipped else "")
            self._set_sidebar_status(
                f"✔ Suggestions updated for "
                f"{changed} file(s).{suffix}",
                SUCCESS_GREEN,
                persist=bool(skipped))
        else:
            self._set_sidebar_status(
                "No files with existing suggestions "
                "were selected.",
                WARNING_YELLOW)


    # ------------------------------------------------------------------
    # Analyze single track (Gemini)
    # Priority 8: auto-route result to _proposed_changes
    # if the file is in _scanned_unorganized.
    # ------------------------------------------------------------------
    def _analyze_single_track(self):
        path = self._sidebar_active_path
        if not path or path not in self.all_files_data:
            return
        if self.organize_strategy_var.get() == "tags_only":
            self._run_local_analyze_single_track(path)
            return
        # Warn if overwriting an existing suggestion
        if path in self._proposed_changes:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Overwrite Suggestion?")
            dialog.resizable(False, False)
            dialog.grab_set()
            self._center_dialog(dialog, 420, 180)
            ctk.CTkLabel(
                dialog,
                text="Overwrite existing suggestion?",
                font=("", 14, "bold"),
            ).pack(pady=(20, 6), padx=20)
            ctk.CTkLabel(
                dialog,
                text=(
                    "This file already has a suggestion."
                    " Running Analyze will overwrite it"
                    " with a new Gemini result. Any"
                    " manual edits will be lost."),
                font=("", 11),
                text_color=TEXT_MUTED,
                wraplength=380, justify="left",
            ).pack(pady=(0, 16), padx=20)
            btn_row = ctk.CTkFrame(
                dialog, fg_color="transparent")
            btn_row.pack()

            def _confirmed():
                dialog.destroy()
                self._run_analyze_single_track(path)

            ctk.CTkButton(
                btn_row, text="Analyze anyway",
                width=120,
                fg_color=ORANGE_PRIMARY,
                hover_color=ORANGE_HOVER,
                command=_confirmed,
            ).pack(side="left", padx=8)
            ctk.CTkButton(
                btn_row, text="Cancel", width=100,
                fg_color=CANCEL_BG,
                hover_color=CANCEL_BG_HOVER,
                text_color=TEXT_ADAPTIVE,
                command=dialog.destroy,
            ).pack(side="left", padx=8)
            return

        if not self._check_api_key():
            return
        self._run_analyze_single_track(path)

    def _run_local_analyze_single_track(self, path: str):
        rec = self.all_files_data.get(path)
        if not rec:
            return

        artist = rec.get("artist", "")
        title  = rec.get("title",  "")
        album  = rec.get("album",  "")

        # Build suggested filename
        ext = os.path.splitext(rec["filename"])[1]
        _repl  = self._get_filename_replacements()
        safe_a = _sanitize_filename_part(artist, _repl)
        safe_t = _sanitize_filename_part(title, _repl)
        naming = self.naming_convention_var.get()
        suggested_filename = (
            f"{safe_a} - {safe_t}{ext}"
            if naming == "Artist - Title"
            else f"{safe_t} - {safe_a}{ext}")

        # Update sidebar variables so the user sees the changes in the details panel
        self.meta_filename_var.set(suggested_filename)
        self.meta_title_var.set(title)
        self.meta_artist_var.set(artist)
        self.meta_album_var.set(album)

        # Enable save/update button
        self.save_metadata_btn.configure(state="normal")

        # If in Unorganized tab or the file is unorganized, update suggestions
        if path in self._scanned_unorganized:
            confidence = "low" if (artist == "Unknown" or title == "Unknown") else "medium-local"
            self._proposed_changes[path] = {
                "filename": suggested_filename,
                "title": title,
                "artist": artist,
                "album": album,
                "confidence": confidence,
            }
            self._update_unorg_row(path)
            self.save_metadata_btn.configure(text="Update Suggestion")

        self._set_sidebar_status(
            "✔ Resolved locally.",
            SUCCESS_GREEN)

    def _run_analyze_single_track(self, path: str):
        """
        Executes the Gemini API call for a single track.
        Called directly when no existing suggestion,
        or after user confirms overwrite.
        """
        if not self._check_api_key():
            return
        rec = self.all_files_data.get(path)
        if not rec:
            return
        self.analyze_track_btn.configure(
            state="disabled", text="Analyzing…")
        self._set_sidebar_status(
            "⏳ Calling Gemini…", WARNING_YELLOW, persist=False)

        def _worker():
            result = self._call_gemini_api({path: rec})
            self.after(
                0, lambda:
                self._on_single_analyze_done(
                    path, result))

        threading.Thread(
            target=_worker, daemon=True).start()


    def _on_single_analyze_done(self, path: str,
                                 result: dict):
        self.analyze_track_btn.configure(
            state="normal", text="Analyze")
        suggested = result.get(path)
        if not suggested:
            self._set_sidebar_status(
                "Gemini returned no suggestion.",
                DANGER_RED)
            return


        confidence = suggested.get("confidence", "low")
        colour_map = {
            "high":   SUCCESS_GREEN,
            "medium": WARNING_YELLOW,
            "low":    DANGER_RED,
        }


        # Populate sidebar fields from Gemini result
        suggested_filename = suggested.get(
            "filename", "")
        if suggested_filename:
            self.meta_filename_var.set(
                suggested_filename)
        self.meta_title_var.set(
            suggested.get("title",  ""))
        self.meta_artist_var.set(
            suggested.get("artist", ""))
        self.meta_album_var.set(
            suggested.get("album",  ""))


        # Priority 8 — if the file is in
        # _scanned_unorganized, auto-write the Gemini
        # result directly to _proposed_changes so the
        # Unorganized tab reflects it immediately without
        # the user having to click Save Changes.
        if path in self._scanned_unorganized:
            self._proposed_changes[path] = suggested


            # Rebuild filename using the user's naming
            # convention rather than Gemini's suggestion
            self._rebuild_suggested_filename(path)


            # Sync the filename field with the rebuilt value
            rebuilt = self._proposed_changes.get(
                path, {}).get("filename", "")
            if rebuilt:
                self.meta_filename_var.set(rebuilt)


            # Load cover art (was never triggered from
            # this code path before this fix)
            self._display_cover_art(path)


            self._update_unorg_row(path)
            self._set_sidebar_status(
                f"✔ Suggestion ready "
                f"(confidence: {confidence})"
                f" — saved to Unorganized tab.",
                colour_map.get(
                    confidence, WARNING_YELLOW))
        else:
            self._set_sidebar_status(
                f"✔ Suggestion ready  "
                f"(confidence: {confidence})",
                colour_map.get(
                    confidence, WARNING_YELLOW))

