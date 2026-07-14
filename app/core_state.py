# app/core_state.py
"""
StateMixin — manages application state, original-values snapshots,
unorganized cache, and undo/redo stacks.
"""
import os
import copy

from app.constants import _MAX_UNDO_STEPS
from app.helpers import _sanitize_filename_part


class StateMixin:
    def _editable_fields_for_record(self, rec: dict) -> dict:
        return {
            "filename": rec["filename"],
            "title":    rec["title"],
            "artist":   rec["artist"],
            "album":    rec["album"],
        }

    def _capture_editable_snapshot(self) -> dict:
        return {
            path: self._editable_fields_for_record(rec)
            for path, rec in self.all_files_data.items()
        }

    def _set_load_snapshot_from_current(self):
        self._load_snapshot = self._capture_editable_snapshot()

    def _rebuild_dirty_tracking_from_load_snapshot(self):
        self._dirty_paths.clear()
        self._original_values.clear()
        if self._load_snapshot is None:
            return

        for path, rec in self.all_files_data.items():
            baseline = self._load_snapshot.get(path)
            if not baseline:
                continue
            current = self._editable_fields_for_record(rec)
            if any(
                    current[field] != baseline.get(field)
                    for field in current):
                self._dirty_paths.add(path)
                self._original_values[path] = dict(baseline)

    # ------------------------------------------------------------------
    # Original-values snapshot (for Review Changes dialog)
    # ------------------------------------------------------------------
    def _snapshot_original(self, path: str):
        """
        Snapshot a file's current values before the first
        mutation. Only snapshots once — subsequent edits do
        not overwrite the original so before/after always
        shows the true original state.
        """
        if path not in self._original_values:
            rec = self.all_files_data.get(path)
            if rec:
                self._original_values[path] = {
                    "filename": rec["filename"],
                    "title":    rec["title"],
                    "artist":   rec["artist"],
                    "album":    rec["album"],
                }

    def _clear_original_values(self):
        """
        Clear snapshots — called whenever _dirty_paths
        is cleared (undo, redo, new directory load).
        """
        self._original_values.clear()

    # ------------------------------------------------------------------
    # Unorganized records cache
    # ------------------------------------------------------------------
    def _invalidate_unorg_cache(self):
        self._unorg_cache     = None
        self._unorg_cache_key = ()

    def _build_unorganized_record(self, path: str) -> dict | None:
        rec = self.all_files_data.get(path)
        if not rec:
            return None

        naming = self.naming_convention_var.get()
        _repl = self._get_filename_replacements()
        check_artist   = self.unorg_check_artist_var.get()
        check_title    = self.unorg_check_title_var.get()
        check_album    = self.unorg_check_album_var.get()
        check_filename = self.unorg_check_filename_var.get()
        check_cover    = self.unorg_check_cover_art_var.get()

        reasons = []

        if check_artist and rec["artist"] == "Unknown":
            reasons.append("Missing tags")

        if check_title and rec["title"] == "Unknown":
            if "Missing tags" not in reasons:
                reasons.append("Missing tags")

        if check_album and rec["album"] == "Unknown":
            if "Missing tags" not in reasons:
                reasons.append("Missing tags")

        if (check_filename and
                rec["artist"] != "Unknown" and
                rec["title"]  != "Unknown"):
            safe_artist = _sanitize_filename_part(
                rec["artist"], _repl)
            safe_title  = _sanitize_filename_part(
                rec["title"], _repl)
            expected = (
                f"{safe_artist} - {safe_title}"
                if naming == "Artist - Title"
                else
                f"{safe_title} - {safe_artist}")
            stem = os.path.splitext(
                rec["filename"])[0]
            if stem != expected:
                reasons.append("Filename mismatch")

        if (check_cover and
                not rec.get("has_cover_art", True)):
            reasons.append("Missing cover art")

        if not reasons:
            return None

        return dict(rec, reason=" + ".join(reasons))

    def _get_unorganized_records(self) -> dict:
        naming = self.naming_convention_var.get()
        _repl = self._get_filename_replacements()
        repltuple = tuple(sorted(_repl.items()))
        key    = (
            id(self.all_files_data),
            naming,
            self.unorg_check_artist_var.get(),
            self.unorg_check_title_var.get(),
            self.unorg_check_album_var.get(),
            self.unorg_check_filename_var.get(),
            self.unorg_check_cover_art_var.get(),
            repltuple,
        )
        if (self._unorg_cache is not None and
                self._unorg_cache_key == key):
            return self._unorg_cache

        result = {}
        for path in self.all_files_data:
            rec = self._build_unorganized_record(path)
            if rec is not None:
                result[path] = rec

        self._unorg_cache     = result
        self._unorg_cache_key = key
        return result

    def _find_filename_mismatches(self) -> list:
        """
        Scans all_files_data for files whose current
        filename does not match what the naming
        convention and sanitization rules would
        produce from their current tags.

        Only considers files where both artist and
        title are known — files with unknown tags
        cannot produce a meaningful expected filename.

        Returns a list of tuples:
            (path, current_filename, expected_filename)
        sorted by current_filename ascending.
        """
        naming = self.naming_convention_var.get()
        _repl  = self._get_filename_replacements()
        results = []

        for path, rec in self.all_files_data.items():
            artist = rec.get("artist", "Unknown")
            title  = rec.get("title",  "Unknown")

            # Skip files with unknown tags — cannot
            # compute a meaningful expected filename
            if artist == "Unknown" or title == "Unknown":
                continue

            safe_artist = _sanitize_filename_part(
                artist, _repl)
            safe_title  = _sanitize_filename_part(
                title, _repl)

            if naming == "Artist - Title":
                expected_stem = (
                    f"{safe_artist} - {safe_title}")
            else:
                expected_stem = (
                    f"{safe_title} - {safe_artist}")

            ext = os.path.splitext(
                rec["filename"])[1]
            expected_filename = expected_stem + ext

            if rec["filename"] != expected_filename:
                results.append((
                    path,
                    rec["filename"],
                    expected_filename,
                ))

        results.sort(
            key=lambda t: t[1].lower())
        return results

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    def _push_undo_snapshot(self):
        # Only snapshot the four user-editable fields.
        # Read-only fields (bitrate, length, location,
        # date_modified, has_cover_art, extra_tags,
        # path, rel_path) are excluded — they are never
        # changed by user edits and do not need to
        # participate in undo/redo.
        snapshot = self._capture_editable_snapshot()
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > _MAX_UNDO_STEPS:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        self.undo_btn.configure(
            state="normal"
            if self._undo_stack else "disabled")
        self.redo_btn.configure(
            state="normal"
            if self._redo_stack else "disabled")
        self._update_unsaved_banner()

    def _on_undo(self):
        if not self._undo_stack:
            return
        self._do_undo()

    def _do_undo(self):
        if not self._undo_stack:
            return
        # Save current state as lightweight redo snapshot
        redo_snapshot = self._capture_editable_snapshot()
        self._redo_stack.append(redo_snapshot)
        # Restore the four mutable fields from snapshot.
        # Read-only fields are left untouched in the
        # live records — they reflect current disk state.
        snapshot = self._undo_stack.pop()
        for path, fields in snapshot.items():
            rec = self.all_files_data.get(path)
            if rec:
                rec["filename"] = fields["filename"]
                rec["title"]    = fields["title"]
                rec["artist"]   = fields["artist"]
                rec["album"]    = fields["album"]
        self.distinct_artists = {
            rec["artist"]
            for rec in self.all_files_data.values()
            if rec["artist"] not in ("Unknown", "")
        }
        self._rebuild_dirty_tracking_from_load_snapshot()
        self._invalidate_unorg_cache()
        self._update_undo_redo_buttons()
        self._refresh_all_views()

    def _on_redo(self):
        if not self._redo_stack:
            return
        # Save current state as lightweight undo snapshot
        undo_snapshot = self._capture_editable_snapshot()
        self._undo_stack.append(undo_snapshot)
        if len(self._undo_stack) > _MAX_UNDO_STEPS:
            self._undo_stack.pop(0)
        # Restore the four mutable fields from snapshot
        snapshot = self._redo_stack.pop()
        for path, fields in snapshot.items():
            rec = self.all_files_data.get(path)
            if rec:
                rec["filename"] = fields["filename"]
                rec["title"]    = fields["title"]
                rec["artist"]   = fields["artist"]
                rec["album"]    = fields["album"]
        self.distinct_artists = {
            rec["artist"]
            for rec in self.all_files_data.values()
            if rec["artist"] not in ("Unknown", "")
        }
        self._rebuild_dirty_tracking_from_load_snapshot()
        self._invalidate_unorg_cache()
        self._update_undo_redo_buttons()
        self._refresh_all_views()

    def _refresh_all_views(self):
        self._populate_all_files_tab()
        if self._scanned_unorganized:
            self._scanned_unorganized = \
                self._get_unorganized_records()
        self._populate_unorganized_tab()
        self._populate_fuzzy_tab()
        self._clear_sidebar()

    def _revert_single_file(self, path: str):
        orig = self._original_values.get(path)
        rec  = self.all_files_data.get(path)
        if not orig or not rec:
            return
        self._push_undo_snapshot()
        rec["filename"] = orig["filename"]
        rec["title"]    = orig["title"]
        rec["artist"]   = orig["artist"]
        rec["album"]    = orig["album"]
        self._dirty_paths.discard(path)
        self._original_values.pop(path, None)
        self._invalidate_unorg_cache()
        self.distinct_artists = {
            r["artist"]
            for r in self.all_files_data.values()
            if r["artist"] not in ("Unknown", "")
        }
        self._update_tree_row(path, rec)
        self._update_status_bar()
        self._update_unsaved_banner()
        # If this file was staged from the Unorganized
        # tab, restore it there so it reappears exactly
        # as it was before staging — including its
        # original suggestion if one existed.
        if path in self._staged_from_unorg:
            import customtkinter as ctk
            saved = self._staged_from_unorg.pop(path)
            self._scanned_unorganized[path] = (
                saved["unorg_rec"])
            if saved["proposal"] is not None:
                self._proposed_changes[path] = (
                    saved["proposal"])
            if path not in self._unorg_check_vars:
                self._unorg_check_vars[path] = (
                    ctk.BooleanVar(value=False))
            # Rebuild the unorg table so the restored
            # row appears in the correct position
            self._populate_unorganized_tab()
        elif path in self._scanned_unorganized:
            self._update_unorg_row(path)

