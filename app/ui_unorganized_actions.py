# app/ui_unorganized_actions.py
"""
UnorganizedActionsMixin — Unorganized tab actions: analyze (local
+ Gemini), organize selected/all, save selected/all, confirm-and-
write-to-disk, and the Gemini API call.

Lives alongside UnorganizedMixin (ui_unorganized.py).
"""
import os
import copy
import json
import datetime
import threading
import customtkinter as ctk
import re


from google import genai
from google.genai import types


from app.constants import (
    WARNING_ON_LIGHT, WARNING_YELLOW,
    SUCCESS_GREEN,
    DANGER_RED, DANGER_RED_HOVER,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER,
    TEXT_WARNING, TEXT_SECONDARY, TEXT_ADAPTIVE,
    GEMINI_MODEL,
)
from app.helpers import _sanitize_filename_part




class UnorganizedActionsMixin:


    def _on_analyze_clicked(self, records: dict):
        if not records:
            self._set_unorg_status(
                "Nothing to analyze.",
                TEXT_SECONDARY)
            return
        strategy = self.organize_strategy_var.get()

        # ── Tags only strategy ────────────────────────
        if strategy == "tags_only":
            local_proposed: dict = {}
            naming = self.naming_convention_var.get()
            for path, rec in records.items():
                new_rec = copy.deepcopy(rec)
                if (rec["artist"] == "Unknown" or
                        rec["title"] == "Unknown"):
                    # Cannot resolve without Gemini —
                    # mark as low confidence for manual
                    # review
                    new_rec["confidence"] = "low"
                elif rec.get("extra_tags"):
                    new_rec["extra_tags"] = []
                    new_rec["confidence"] = "medium-local"
                else:
                    new_rec["confidence"] = "medium-local"
                local_proposed[path] = new_rec
            self._proposed_changes.update(
                local_proposed)
            for path in local_proposed:
                # Rebuild filename using the shared helper so
                # naming convention and sanitization rules stay
                # in one place. Only runs when artist and title
                # are both known — _rebuild_suggested_filename
                # is a no-op otherwise.
                self._rebuild_suggested_filename(path)
                self._update_unorg_row(path)
                self._refresh_sidebar_if_active(path)
            unresolvable = sum(
                1 for r in local_proposed.values()
                if r.get("confidence") == "low")
            resolved = len(local_proposed) - unresolvable
            if unresolvable:
                self._set_unorg_status(
                    f"✔ {resolved} file(s) resolved "
                    f"locally.  "
                    f"⚠ {unresolvable} file(s) have "
                    f"unknown tags and cannot be "
                    f"resolved without Gemini.",
                    WARNING_YELLOW)
            else:
                self._set_unorg_status(
                    f"✔ {resolved} file(s) resolved "
                    f"locally.",
                    SUCCESS_GREEN)
            return

        # ── Gemini strategy — all files go to Gemini ──
        if not self._check_api_key():
            return
        try:
            self.organize_selected_btn.configure(
                state="disabled")
            self.organize_all_btn.configure(
                state="disabled")
        except Exception:
            pass
        try:
            self.analyze_track_btn.configure(
                state="disabled")
        except Exception:
            pass
        self._set_unorg_status(
            f"⧑ Calling Gemini for "
            f"{len(records)} file(s)…",
            TEXT_WARNING,
            persist=True)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.progress_bar.pack(
            side="right", padx=10, pady=10)
        def _worker():
            proposed = self._call_gemini_api(records)
            self.after(
                0, lambda: self._on_analysis_done(
                    proposed))

        threading.Thread(
            target=_worker, daemon=True).start()


    def _on_analysis_done(self, proposed: dict):
        self._proposed_changes.update(proposed)
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.pack_forget()

        try:
            self.organize_selected_btn.configure(
                state="normal")
            self.organize_all_btn.configure(
                state="normal")
        except Exception:
            pass
        try:
            if self._sidebar_active_path:
                self.analyze_track_btn.configure(
                    state="normal")
        except Exception:
            pass
        for path in proposed:
            # Rebuild filename from sanitized title +
            # artist using the naming convention.
            # This ensures Gemini's raw suggested
            # filename is replaced with a clean one
            # that respects sanitization rules,
            # identical to the tags_only path and
            # the single-track analyzer path.
            self._rebuild_suggested_filename(path)
            self._update_unorg_row(path)
            self._refresh_sidebar_if_active(path)
        # Safety net: sync the sidebar for the active path
        # only if it was NOT already handled in the loop above.
        active = self._sidebar_active_path
        if (active and
                active in self._scanned_unorganized and
                active not in proposed):
            self._sync_sidebar_from_unorg(active)
        self._set_unorg_status(
            f"✔ {len(proposed)} AI suggestion(s) "
            f"ready.",
            SUCCESS_GREEN)


    def _on_organize_all(self):
        if not self._scanned_unorganized:
            self._set_unorg_status(
                "Run 'Find Unorganized Files' first.",
                TEXT_WARNING)
            return
        self._on_analyze_clicked(
            self._scanned_unorganized)


    def _on_organize_selected(self):
        if not self._scanned_unorganized:
            self._set_unorg_status(
                "Run 'Find Unorganized Files' first.",
                TEXT_WARNING)
            return
        # Only process files with checkboxes checked (user request)
        all_selected = {
            p for p in self._scanned_unorganized
            if self._is_path_checked(p)}
        selected = {
            path: rec
            for path, rec in
            self._scanned_unorganized.items()
            if path in all_selected
        }
        if not selected:
            self._set_unorg_status(
                "No checked rows. Highlighting only "
                "updates the sidebar; use the check "
                "column for Organize Checked.",
                TEXT_WARNING)
            return
        self._on_analyze_clicked(selected)


    def _on_save_all_proposed(self):
        if not self._proposed_changes:
            self._set_unorg_status(
                "No suggestions to apply. "
                "Run 'Organize' first.",
                TEXT_WARNING)
            return
        self._confirm_and_write(
            dict(self._proposed_changes), bulk=True)


    def _on_save_selected_proposed(self):
        if not self._proposed_changes:
            self._set_unorg_status(
                "No suggestions to apply. "
                "Run 'Organize' first.",
                TEXT_WARNING)
            return

        checked_paths = [
            path for path in self._scanned_unorganized
            if self._is_path_checked(path)
        ]
        if not checked_paths:
            self._set_unorg_status(
                "No checked rows. Highlighting only "
                "updates the sidebar; use the check "
                "column for Apply Changes to Checked.",
                TEXT_WARNING)
            return

        selected = {
            path: rec
            for path, rec in
            self._proposed_changes.items()
            if path in checked_paths
        }
        if not selected:
            self._set_unorg_status(
                "Checked rows do not have suggestions "
                "yet. Run 'Organize Checked' first.",
                TEXT_WARNING)
            return
        self._confirm_and_write(selected, bulk=False)


    def _confirm_and_write(self, changes: dict,
                            bulk: bool):
        scope = "ALL" if bulk else "SELECTED"
        count = len(changes)
        dialog = ctk.CTkToplevel(self)
        dialog.title("Stage Changes for Review")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 400, 170)
        ctk.CTkLabel(
            dialog,
            text=(f"Apply changes to {scope} "
                  f"{count} file(s)?"),
            font=("", 14, "bold"),
        ).pack(pady=(24, 8), padx=20)
        ctk.CTkLabel(
            dialog,
            text=(
                "Changes will be staged for review. "
                "You will be asked to confirm before "
                "anything is written to disk."),
            text_color=WARNING_ON_LIGHT, font=("", 11),
            wraplength=360,
        ).pack(pady=(0, 16), padx=20)
        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack()

        def _confirmed():
            dialog.destroy()
            self._stage_proposed_changes(changes)

        ctk.CTkButton(
            btn_row, text="Confirm", width=100,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=_confirmed,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy,
        ).pack(side="left", padx=8)

    def _stage_proposed_changes(self, changes: dict):
        """
        Merges proposed changes into all_files_data and
        _dirty_paths without writing to disk.
        Saves unorg context to _staged_from_unorg so
        that _revert_single_file can restore the file
        to the Unorganized tab correctly.
        """
        if not changes:
            return

        self._push_undo_snapshot()

        for path, proposed_rec in changes.items():
            # Save unorg context before removing
            # so _revert_single_file can restore it
            self._staged_from_unorg[path] = {
                "unorg_rec": (
                    self._scanned_unorganized.get(
                        path)),
                "proposal": (
                    self._proposed_changes.get(path)),
            }

            # Snapshot original before mutation
            self._snapshot_original(path)

            # Apply proposed values to all_files_data
            rec = self.all_files_data.get(path)
            if rec:
                rec["title"]    = proposed_rec.get(
                    "title",    rec["title"])
                rec["artist"]   = proposed_rec.get(
                    "artist",   rec["artist"])
                rec["album"]    = proposed_rec.get(
                    "album",    rec["album"])

                # Always recompute the filename from
                # the final tags using the naming
                # convention and sanitization rules.
                # This ensures the filename is always
                # correct after Apply, regardless of
                # what Gemini suggested or what the
                # original filename was.
                # Only rename if both artist and title
                # are known — unknown tags cannot
                # produce a meaningful filename.
                artist = rec["artist"]
                title  = rec["title"]
                if (artist not in ("Unknown", "") and
                        title  not in ("Unknown", "")):
                    from app.helpers import (
                        _sanitize_filename_part)
                    _repl = (
                        self._get_filename_replacements())
                    naming = (
                        self.naming_convention_var.get())
                    safe_a = _sanitize_filename_part(
                        artist, _repl)
                    safe_t = _sanitize_filename_part(
                        title, _repl)
                    ext = os.path.splitext(
                        rec["filename"])[1]
                    if naming == "Artist - Title":
                        rec["filename"] = (
                            f"{safe_a} - {safe_t}{ext}")
                    else:
                        rec["filename"] = (
                            f"{safe_t} - {safe_a}{ext}")
                else:
                    # Tags still unknown — keep
                    # whatever filename the proposal
                    # suggested
                    rec["filename"] = proposed_rec.get(
                        "filename", rec["filename"])

            # Stage as dirty — will be written when
            # user confirms in Review & Save dialog
            self._dirty_paths.add(path)
            self._fuzzy_stale = True

            # Remove from unorg tracking
            self._scanned_unorganized.pop(path, None)
            self._proposed_changes.pop(path, None)
            self._unorg_check_vars.pop(path, None)
            if (hasattr(self, "unorg_tree") and
                    self.unorg_tree.exists(path)):
                self.unorg_tree.delete(path)

        self.distinct_artists = {
            r["artist"]
            for r in self.all_files_data.values()
            if r["artist"] not in ("Unknown", "")
        }
        self._invalidate_unorg_cache()
        self._update_status_bar()
        self._update_unsaved_banner()
        self._update_unorg_checked_actions()

    # ------------------------------------------------------------------
    # Gemini API
    # ------------------------------------------------------------------
    def _call_gemini_api(self, records: dict) -> dict:
        client         = genai.Client()
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch())
        config         = types.GenerateContentConfig(
            tools=[grounding_tool])

        # Read field toggle state once at call time
        search_title  = self.gemini_search_title_var.get()
        search_artist = self.gemini_search_artist_var.get()
        search_album  = self.gemini_search_album_var.get()

        batch = [
            {"index": i,
             "filename":       rec["filename"],
             "current_artist": rec["artist"],
             "current_title":  rec["title"],
             "current_album":  rec["album"]}
            for i, rec in enumerate(records.values())
        ]
        naming = self.naming_convention_var.get()

        # =============================================================
        # SECTION 1 — PROMPT CONSTRUCTION
        # Build the field-specific instructions based on
        # which fields the user has enabled. Fields that
        # are toggled off receive an explicit "do not
        # change" instruction so Gemini focuses only on
        # what was asked for.
        # =============================================================

        # Build the list of fields Gemini should search
        fields_to_search = []
        if search_title:
            fields_to_search.append("Title")
        if search_artist:
            fields_to_search.append("Artist")
        if search_album:
            fields_to_search.append("Album")

        # Fallback — should never happen due to UI guard
        # but defend against it anyway
        if not fields_to_search:
            fields_to_search = ["Title", "Artist", "Album"]

        fields_str = ", ".join(fields_to_search)

        # Build preservation instructions for toggled-off
        # fields
        preserve_lines = []
        if not search_title:
            preserve_lines.append(
                "- Do NOT change the Title. "
                "Use the current_title value exactly "
                "as provided in the input.")
        if not search_artist:
            preserve_lines.append(
                "- Do NOT change the Artist. "
                "Use the current_artist value exactly "
                "as provided in the input.")
        if not search_album:
            preserve_lines.append(
                "- Do NOT change the Album. "
                "Use the current_album value exactly "
                "as provided in the input.")

        preserve_block = (
            "\n" + "\n".join(preserve_lines)
            if preserve_lines else "")

        from app.constants import GEMINI_DEFAULT_PROMPT

        # Use custom prompt if one has been saved,
        # otherwise fall back to the default.
        _raw_prompt = (
            self.gemini_prompt_var.get().strip()
            if self.gemini_prompt_var.get().strip()
            else GEMINI_DEFAULT_PROMPT)

        # Inject the dynamic runtime values into the
        # static prompt text, then append the file data.
        # Fall back to the default if the user's prompt
        # has broken/missing format tokens.
        try:
            prompt = (
                _raw_prompt.format(
                    fields_str=fields_str,
                    naming=naming,
                    preserve_block=preserve_block)
                + f"\n\nInput:\n{json.dumps(batch, indent=2)}\n")
        except (KeyError, ValueError) as _fmt_err:
            print(
                f"[Gemini] Custom prompt formatting "
                f"failed ({_fmt_err}); using default.")
            prompt = (
                GEMINI_DEFAULT_PROMPT.format(
                    fields_str=fields_str,
                    naming=naming,
                    preserve_block=preserve_block)
                + f"\n\nInput:\n{json.dumps(batch, indent=2)}\n")

        log = self.gemini_logging_var.get()
        if log:
            import datetime as _dt
            _ts = _dt.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*60}")
            print(f"[Gemini → {_ts}]")
            print(
                f"[Gemini → sending "
                f"{len(batch)} file(s)]")
            print(
                f"[Gemini → fields: {fields_str}]")
            if preserve_lines:
                print(
                    f"[Gemini → preserving: "
                    f"{', '.join(f for f in ('Title', 'Artist', 'Album') if f not in fields_to_search)}]")
            for entry in batch:
                print(
                    f"  [{entry['index']}] "
                    f"\"{entry['filename']}\"  "
                    f"artist="
                    f"{entry['current_artist']!r}"
                    f"  title="
                    f"{entry['current_title']!r}"
                    f"  album="
                    f"{entry['current_album']!r}")
            print(f"{'='*60}\n")

        proposed     = {}
        records_list = list(records.items())
        response     = None

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=config)
            raw_text = response.text.strip()

            if log:
                print(f"\n{'='*60}")
                print(
                    f"[Gemini ← raw response "
                    f"({len(raw_text)} chars)]")
                print(raw_text[:1000])
                if len(raw_text) > 1000:
                    print(
                        f"  … "
                        f"({len(raw_text) - 1000}"
                        f" more chars)")
                print(f"{'='*60}\n")

            # Robust extraction of the JSON block out of the raw response text
            extracted_json = raw_text
            match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', raw_text, re.DOTALL)
            if match:
                extracted_json = match.group(1).strip()
            else:
                array_start = raw_text.find('[')
                array_end = raw_text.rfind(']')
                if array_start != -1 and array_end != -1 and array_end > array_start:
                    extracted_json = raw_text[array_start:array_end + 1].strip()
                else:
                    obj_start = raw_text.find('{')
                    obj_end = raw_text.rfind('}')
                    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
                        extracted_json = raw_text[obj_start:obj_end + 1].strip()

            suggestions    = json.loads(extracted_json)
            suggestion_map = {
                int(s["index"]): s
                for s in suggestions}

            if log:
                print(
                    f"[Gemini ← parsed "
                    f"{len(suggestions)} "
                    f"suggestion(s)]")
                for s in suggestions:
                    print(
                        f"  [{s.get('index')}] "
                        f"artist="
                        f"{s.get('suggested_artist')!r}"
                        f"  title="
                        f"{s.get('suggested_title')!r}"
                        f"  confidence="
                        f"{s.get('confidence')!r}")
                print()

            for i, (path, rec) in enumerate(
                    records_list):
                new_rec = copy.deepcopy(rec)
                s       = suggestion_map.get(i)

                if s:
                    # =============================================
                    # SECTION 2 — FIELD BLOCKING ON RECEIPT
                    # Safety net: even if Gemini ignored the
                    # prompt instructions and returned values for
                    # toggled-off fields, we discard them here
                    # and preserve the original tag values.
                    # This section is independent of Section 1
                    # and can be modified without affecting the
                    # prompt logic above.
                    # =============================================
                    if search_title:
                        new_rec["title"] = s.get(
                            "suggested_title",
                            rec["title"])
                    # else: title stays as rec["title"]
                    # (copy.deepcopy already copied it)

                    if search_artist:
                        new_rec["artist"] = s.get(
                            "suggested_artist",
                            rec["artist"])
                    # else: artist stays as rec["artist"]

                    if search_album:
                        new_rec["album"] = s.get(
                            "suggested_album",
                            rec["album"])
                    # else: album stays as rec["album"]

                    # Filename is always rebuilt from
                    # whatever title and artist ended up
                    # being set above — either from Gemini
                    # or preserved from original tags
                    new_rec["filename"] = s.get(
                        "suggested_filename",
                        rec["filename"])

                    new_rec["confidence"] = s.get(
                        "confidence", "low").lower()
                else:
                    new_rec["confidence"] = "low"

                proposed[path] = new_rec

        except json.JSONDecodeError as exc:
            print(
                f"\n[Gemini ✗ JSON parse error]: "
                f"{exc}")
            if response is not None:
                print(
                    f"[Gemini ✗ full raw response]:\n"
                    f"{response.text}\n")
            for path, rec in records_list:
                new_rec = copy.deepcopy(rec)
                new_rec["confidence"] = "low"
                proposed[path] = new_rec

        except Exception as exc:
            print(f"\n[Gemini ✗ API error]: {exc}\n")
            for path, rec in records_list:
                new_rec = copy.deepcopy(rec)
                new_rec["confidence"] = "low"
                proposed[path] = new_rec

        return proposed

