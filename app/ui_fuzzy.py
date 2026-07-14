# app/ui_fuzzy.py
"""
FuzzyMixin — everything for the Fuzzy Matches tab.


Three cluster types:
  artist_title — artist portion and/or title portion mismatches
  separator    — separator format mismatches
  collab       — collaboration tag mismatches


Each card is self-contained. Per-file checkbox state lives in a
local dict inside the card builder closure — no persistent state
on self is needed since the tab is rebuilt on every refresh.
"""
import os
import threading
import tkinter as tk
import customtkinter as ctk
from collections import Counter


from app.constants import (
    ACCENT_BLUE, ACCENT_BLUE_MID, SAVE_BLUE, SAVE_BLUE_HOVER,
    DANGER_RED, DANGER_RED_HOVER,
    ORANGE_PRIMARY, ORANGE_HOVER,
    WARNING_YELLOW, SUCCESS_GREEN, TEXT_MUTED, TEXT_ADAPTIVE,
    TEXT_SECONDARY, TEXT_PRIMARY, TEXT_BLACK,
    CANCEL_BG, CANCEL_BG_HOVER,
)
from app.fuzzy_worker import (
    _run_fuzzy_clustering_thread,
    _SEP_VARIANTS, _COLLAB_KEYWORDS,
    _split_stem,
    _scan_collab_normalizations,
    _apply_collab_normalization,
)
from app.config import _save_config




_SEP_OPTIONS    = [" - ", "--", "_", "/"]
_COLLAB_OPTIONS = ["ft.", "feat.", "x", "&", "vs.", "with"]
_COLLAB_NORMALIZE_OPTIONS = [
    "ft.", "feat.", "featuring", "x", "vs.", "with", "w/"]




class FuzzyMixin:


    # ------------------------------------------------------------------
    # Tab setup
    # ------------------------------------------------------------------
    def _setup_fuzzy_tab(self):
        top_bar = ctk.CTkFrame(
            self.tab_fuzzy, fg_color="transparent")
        top_bar.pack(fill="x", padx=5, pady=(5, 0))


        ctk.CTkLabel(
            top_bar, text="Fuzzy Matches",
            font=("", 14, "bold"),
        ).pack(side="left", padx=10)


        ctk.CTkButton(
            top_bar, text="↻ Refresh View", width=120,
            command=self._populate_fuzzy_tab,
        ).pack(side="right", padx=10)


        self.fuzzy_loading_lbl = ctk.CTkLabel(
            top_bar, text="",
            text_color=WARNING_YELLOW, font=("", 11))
        self.fuzzy_loading_lbl.pack(
            side="right", padx=(0, 8))


        self.fuzzy_scroll = ctk.CTkScrollableFrame(
            self.tab_fuzzy)
        self.fuzzy_scroll.pack(
            fill="both", expand=True, padx=5, pady=5)


        ctk.CTkLabel(
            self.fuzzy_scroll,
            text="Fuzzy matches will appear here.",
            text_color=TEXT_SECONDARY,
        ).pack(pady=20)


        def _on_threshold_release(_event):
            self._populate_fuzzy_tab()


        self._fuzzy_threshold_release_cb = \
            _on_threshold_release


    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------
    def _populate_fuzzy_tab(self):
        if not hasattr(self, "fuzzy_scroll"):
            return


        if not self.all_files_data:
            for w in self.fuzzy_scroll.winfo_children():
                w.destroy()
            ctk.CTkLabel(
                self.fuzzy_scroll,
                text=(
                    "Load a directory to find fuzzy "
                    "matches."),
                text_color=TEXT_SECONDARY,
            ).pack(pady=20)
            return


        if self._fuzzy_thread_running:
            self._fuzzy_rerun_pending = True
            return


        self._fuzzy_thread_running = True
        self._fuzzy_rerun_pending  = False
        self.fuzzy_loading_lbl.configure(
            text="⏳ Calculating…")


        threshold    = int(self.fuzzy_threshold_var.get())
        naming       = self.naming_convention_var.get()
        stems        = list({
            os.path.splitext(rec["filename"])[0]
            for rec in self.all_files_data.values()
        })
        ignore_pairs = set(self._fuzzy_ignore_pairs)

        self._fuzzy_generation += 1
        my_gen = self._fuzzy_generation

        def _deliver(result: dict):
            self.after(
                0, lambda:
                self._on_fuzzy_results_ready(
                    result, threshold, my_gen))


        threading.Thread(
            target=_run_fuzzy_clustering_thread,
            args=(stems, naming, threshold,
                  ignore_pairs, _deliver),
            daemon=True,
        ).start()


    def _on_fuzzy_results_ready(self, result: dict,
                                  threshold: int,
                                  gen: int):
        self._fuzzy_thread_running = False
        if gen == self._fuzzy_generation:
            self._fuzzy_stale = False
        self.fuzzy_loading_lbl.configure(text="")


        for widget in self.fuzzy_scroll.winfo_children():
            widget.destroy()


        artist_title = result.get("artist_title", [])
        separator    = result.get("separator",    [])
        collab       = result.get("collab",       []) if self.fuzzy_show_collaboration_var.get() else []
        total = (len(artist_title) + len(separator)
                 + len(collab))

        # Always build the normalization section
        # regardless of whether clusters were found.
        # It runs its own independent scan.
        if self.fuzzy_show_collaboration_var.get():
            self._build_collab_normalization_section()

        if total == 0:
            ctk.CTkLabel(
                self.fuzzy_scroll,
                text=(
                    f"No mismatches found at the current"
                    f" threshold ({threshold}%)."),
                text_color=TEXT_SECONDARY,
            ).pack(pady=20)
        else:
            if artist_title:
                self._add_section_header(
                    "Artist / Title Mismatches",
                    f"{len(artist_title)} group(s)")
                for cluster in artist_title:
                    self._build_mismatch_card(cluster)


            if separator:
                self._add_section_header(
                    "Separator Mismatches",
                    f"{len(separator)} group(s)")
                for cluster in separator:
                    self._build_mismatch_card(cluster)


            if collab:
                self._add_section_header(
                    "Collaboration Tag Mismatches",
                    f"{len(collab)} group(s)")
                for cluster in collab:
                    self._build_mismatch_card(cluster)


        if self._fuzzy_rerun_pending:
            self._populate_fuzzy_tab()


    # ------------------------------------------------------------------
    # Section header
    # ------------------------------------------------------------------
    def _add_section_header(self, title: str,
                             subtitle: str):
        ctk.CTkFrame(
            self.fuzzy_scroll, height=1,
            fg_color="gray40",
        ).pack(fill="x", padx=10, pady=(16, 0))


        row = ctk.CTkFrame(
            self.fuzzy_scroll, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(6, 2))


        ctk.CTkLabel(
            row, text=title,
            font=("", 20, "bold"),
            text_color=TEXT_BLACK, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            row, text=subtitle,
            font=("", 11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(10, 0))


    # ------------------------------------------------------------------
    # Collaboration keyword normalization — global scan
    # ------------------------------------------------------------------
    def _build_collab_normalization_section(self):
        """
        Scans all filename stems for collaboration
        keyword variants and builds a normalization
        panel at the top of the Fuzzy Matches tab.
        Hidden if no matches are found.
        """
        if not self.all_files_data:
            return

        naming = self.naming_convention_var.get()
        stems  = list({
            os.path.splitext(rec["filename"])[0]
            for rec in self.all_files_data.values()
        })

        matches = _scan_collab_normalizations(
            stems, naming)

        if not matches:
            return

        # Group by keyword found for display
        found_keywords = sorted({
            m["keyword"].lower()
            for m in matches})

        # Section header
        ctk.CTkFrame(
            self.fuzzy_scroll, height=1,
            fg_color="gray40",
        ).pack(fill="x", padx=10, pady=(16, 0))

        hdr_row = ctk.CTkFrame(
            self.fuzzy_scroll,
            fg_color="transparent")
        hdr_row.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            hdr_row,
            text="Collaboration Keyword Normalization",
            font=("", 20, "bold"),
            text_color=TEXT_BLACK, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            hdr_row,
            text=f"{len(matches)} file(s)",
            font=("", 11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(10, 0))

        # Card
        card = ctk.CTkFrame(
            self.fuzzy_scroll,
            corner_radius=8, border_width=1)
        card.pack(fill="x", pady=8, padx=5)

        # Description
        kw_display = ", ".join(
            f'"{k}"' for k in found_keywords)
        ctk.CTkLabel(
            card,
            text=(
                f"Detected collaboration keyword "
                f"variants: {kw_display}\n"
                f"Parentheses/brackets will be "
                f"removed. Both filename and tag "
                f"value will be updated."),
            font=("", 11),
            text_color=TEXT_MUTED,
            justify="left", anchor="w",
            wraplength=560,
        ).pack(anchor="w", padx=12, pady=(10, 6))

        # File list
        file_list_frame = ctk.CTkFrame(
            card, fg_color="transparent")
        file_list_frame.pack(
            fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(
            file_list_frame,
            text="Affected files:",
            font=("", 11, "bold"), anchor="w",
        ).pack(anchor="w")

        # Build path lookup by stem
        stem_to_path: dict = {}
        for rec in self.all_files_data.values():
            stem = os.path.splitext(
                rec["filename"])[0]
            stem_to_path[stem] = rec["path"]

        checked_vars: dict = {}
        for match in matches:
            path = stem_to_path.get(match["stem"])
            if not path:
                continue
            checked_vars[path] = tk.BooleanVar(
                value=True)
            row = ctk.CTkFrame(
                file_list_frame,
                fg_color="transparent")
            row.pack(fill="x", pady=1)
            # Show before → after preview
            rec  = self.all_files_data.get(path, {})
            ctk.CTkCheckBox(
                row,
                text=(
                    f"{os.path.basename(path)}"),
                variable=checked_vars[path],
                font=("Courier", 11),
                checkbox_width=16,
                checkbox_height=16,
            ).pack(side="left", padx=(4, 0))
            ctk.CTkLabel(
                row,
                text=(
                    f"  [{match['position']}]  "
                    f'"{match["keyword"]}" →'),
                font=("", 10),
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=(8, 0))

        # Select/Deselect all
        sel_row = ctk.CTkFrame(
            file_list_frame, fg_color="transparent")
        sel_row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            sel_row, text="Select All",
            width=90, height=22, font=("", 11),
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=lambda: [
                v.set(True)
                for v in checked_vars.values()],
        ).pack(side="left", padx=(4, 4))
        ctk.CTkButton(
            sel_row, text="Deselect All",
            width=90, height=22, font=("", 11),
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=lambda: [
                v.set(False)
                for v in checked_vars.values()],
        ).pack(side="left")

        # Divider
        ctk.CTkFrame(
            card, height=1, fg_color="gray30",
        ).pack(fill="x", padx=12, pady=(6, 0))

        # Keyword picker
        pick_sec = ctk.CTkFrame(
            card, fg_color="transparent")
        pick_sec.pack(
            fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            pick_sec,
            text="Normalize keyword to:",
            font=("", 11, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        pick_row = ctk.CTkFrame(
            pick_sec, fg_color="transparent")
        pick_row.pack(fill="x")

        canon_var = ctk.StringVar(value="ft.")
        pick_buttons: list = []

        _style_default = dict(
            fg_color="transparent",
            border_width=1,
            border_color=ACCENT_BLUE_MID,
            text_color=TEXT_ADAPTIVE,
        )
        _style_selected = dict(
            fg_color=ORANGE_PRIMARY,
            border_width=2,
            border_color=ORANGE_HOVER,
            text_color=TEXT_PRIMARY,
        )

        def _on_pick(opt: str, idx: int):
            canon_var.set(opt)
            for i, b in enumerate(pick_buttons):
                b.configure(
                    **(_style_selected
                       if i == idx
                       else _style_default))

        for idx, opt in enumerate(
                _COLLAB_NORMALIZE_OPTIONS):
            btn = ctk.CTkButton(
                pick_row,
                text=opt,
                width=0, height=26,
                font=("", 11),
                **(_style_selected
                   if opt == "ft."
                   else _style_default),
                hover_color=ACCENT_BLUE,
                command=lambda o=opt, i=idx:
                _on_pick(o, i))
            btn.pack(side="left", padx=3)
            pick_buttons.append(btn)

        custom_entry = ctk.CTkEntry(
            pick_row,
            textvariable=canon_var,
            width=100,
            placeholder_text="or type here…")
        custom_entry.pack(
            side="left", padx=(8, 0))

        # Status label
        status_lbl = ctk.CTkLabel(
            card, text="", font=("", 11),
            text_color=SUCCESS_GREEN, anchor="w")

        # Apply buttons
        apply_row = ctk.CTkFrame(
            card, fg_color="transparent")
        apply_row.pack(
            fill="x", padx=12, pady=(6, 10))

        def _apply(paths: list):
            canonical = canon_var.get().strip()
            if not canonical:
                status_lbl.configure(
                    text=(
                        "⚠ Please select or type "
                        "a canonical keyword."),
                    text_color=WARNING_YELLOW)
                return
            if not paths:
                status_lbl.configure(
                    text=(
                        "⚠ No files selected."),
                    text_color=WARNING_YELLOW)
                return
            self._show_apply_options_dialog(
                lambda ut, uf: self._apply_collab_normalization_bulk(
                    paths, canonical, naming,
                    stem_to_path, status_lbl, ut, uf)
            )

        ctk.CTkButton(
            apply_row,
            text="Apply to selected",
            width=130, height=26, font=("", 11),
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=lambda: _apply([
                p for p in checked_vars
                if checked_vars[p].get()]),
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            apply_row,
            text="Apply to all",
            width=100, height=26, font=("", 11),
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=lambda: _apply(
                list(checked_vars.keys())),
        ).pack(side="left")

        status_lbl.pack(
            fill="x", padx=12, pady=(0, 6))

    def _apply_collab_normalization_bulk(
            self,
            paths: list,
            canonical_kw: str,
            naming: str,
            stem_to_path: dict,
            status_lbl,
            update_tags: bool = True,
            update_filenames: bool = True):
        """
        Applies collaboration keyword normalization
        to a list of file paths.
        Updates both the filename stem and the
        corresponding tag value (artist or title).
        All changes go through _dirty_paths.
        """
        if not canonical_kw.strip():
            return
        if not paths:
            status_lbl.configure(
                text="No files are checked. Check at least one file to apply.",
                text_color=WARNING_YELLOW)
            return

        changed      = 0
        snapshot_pushed = False

        for path in paths:
            rec = self.all_files_data.get(path)
            if not rec:
                continue

            stem, ext = os.path.splitext(
                rec["filename"])
            new_stem = _apply_collab_normalization(
                stem, naming, canonical_kw)

            if new_stem is None or new_stem == stem:
                continue

            # Sync the corresponding tag value.
            # Re-split the NEW stem to get updated
            # artist/title parts.
            new_artist_part, new_title_part = \
                _split_stem(new_stem, naming)
            old_artist_part, old_title_part = \
                _split_stem(stem, naming)

            fn_changed = (rec["filename"] != new_stem + ext) if update_filenames else False
            artist_changed = (new_artist_part != old_artist_part) if update_tags else False
            title_changed = (new_title_part != old_title_part) if update_tags else False

            if not fn_changed and not artist_changed and not title_changed:
                continue

            if not snapshot_pushed:
                self._push_undo_snapshot()
                snapshot_pushed = True
            self._snapshot_original(path)

            if update_filenames:
                rec["filename"] = new_stem + ext

            if update_tags:
                if new_artist_part != old_artist_part:
                    rec["artist"] = new_artist_part
                if new_title_part != old_title_part:
                    rec["title"] = new_title_part

            self._dirty_paths.add(path)
            self._update_tree_row(path, rec)

            if path in self._scanned_unorganized:
                self._update_unorg_row(path)

            changed += 1

        if changed:
            self._fuzzy_stale = True
            self.distinct_artists = {
                r["artist"]
                for r in self.all_files_data.values()
                if r["artist"] not in (
                    "Unknown", "")
            }
            self._invalidate_unorg_cache()
            self._update_status_bar()
            self._update_unsaved_banner()
            status_lbl.configure(
                text=(
                    f"✔ Normalized {changed} "
                    f"file(s). Refresh to update "
                    f"remaining matches."),
                text_color=SUCCESS_GREEN)
        else:
            status_lbl.configure(
                text=(
                    "No changes were needed — files "
                    "may already use the selected keyword."),
                text_color=WARNING_YELLOW)

    # ------------------------------------------------------------------
    # Unified mismatch card
    # ------------------------------------------------------------------
    def _build_mismatch_card(self, cluster: dict):
        kind  = cluster["kind"]
        stems = cluster["stems"]


        stem_to_recs: dict = {}
        for rec in self.all_files_data.values():
            stem = os.path.splitext(rec["filename"])[0]
            if stem in stems:
                stem_to_recs.setdefault(
                    stem, []).append(rec)


        all_paths = sorted(
            [rec["path"]
             for stem in stems
             for rec in stem_to_recs.get(stem, [])],
            key=lambda p: os.path.basename(p).lower(),
        )


        if not all_paths:
            return


        checked_vars: dict = {
            path: tk.BooleanVar(value=True)
            for path in all_paths
        }


        card = ctk.CTkFrame(
            self.fuzzy_scroll,
            corner_radius=8, border_width=1)
        card.pack(fill="x", pady=8, padx=5)


        # Header
        header_text = self._cluster_header_text(cluster)
        header_row  = ctk.CTkFrame(
            card, fg_color="transparent")
        header_row.pack(
            fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            header_row, text=header_text,
            font=("", 13, "bold"),
            text_color=ACCENT_BLUE, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            header_row,
            text=f"{len(all_paths)} file(s)",
            font=("", 11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(8, 0))


        # File list with checkboxes
        file_list_frame = ctk.CTkFrame(
            card, fg_color="transparent")
        file_list_frame.pack(
            fill="x", padx=12, pady=(0, 4))


        ctk.CTkLabel(
            file_list_frame,
            text="Files in this group:",
            font=("", 11, "bold"), anchor="w",
        ).pack(anchor="w")


        for path in all_paths:
            row = ctk.CTkFrame(
                file_list_frame,
                fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkCheckBox(
                row,
                text=os.path.basename(path),
                variable=checked_vars[path],
                font=("Courier", 11),
                checkbox_width=16,
                checkbox_height=16,
            ).pack(side="left", padx=(4, 0))


        sel_row = ctk.CTkFrame(
            file_list_frame, fg_color="transparent")
        sel_row.pack(fill="x", pady=(2, 0))
        ctk.CTkButton(
            sel_row, text="Select All",
            width=90, height=22, font=("", 11),
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=lambda: [
                v.set(True)
                for v in checked_vars.values()],
        ).pack(side="left", padx=(4, 4))
        ctk.CTkButton(
            sel_row, text="Deselect All",
            width=90, height=22, font=("", 11),
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=lambda: [
                v.set(False)
                for v in checked_vars.values()],
        ).pack(side="left")


        # Thin divider
        ctk.CTkFrame(
            card, height=1, fg_color="gray30",
        ).pack(fill="x", padx=12, pady=(6, 0))


        # Shared status label
        status_lbl = ctk.CTkLabel(
            card, text="", font=("", 11),
            text_color=SUCCESS_GREEN, anchor="w")


        # Mismatch-specific sections
        if kind == "artist_title":
            self._build_at_sections(
                card, cluster, stem_to_recs,
                checked_vars, all_paths, status_lbl)
        elif kind == "separator":
            self._build_sep_section(
                card, cluster, stem_to_recs,
                checked_vars, all_paths, status_lbl)
        elif kind == "collab":
            self._build_collab_section(
                card, cluster, stem_to_recs,
                checked_vars, all_paths, status_lbl)


        status_lbl.pack(
            fill="x", padx=12, pady=(6, 0))
        self._build_dismiss_row(
            card, cluster, stems,
            all_paths, checked_vars,
            status_lbl)


    # ------------------------------------------------------------------
    # Header text
    # ------------------------------------------------------------------
    def _cluster_header_text(self,
                               cluster: dict) -> str:
        kind = cluster["kind"]
        if kind == "artist_title":
            parts = []
            if cluster.get("artist_mismatch"):
                parts.append("Artist")
            if cluster.get("title_mismatch"):
                parts.append("Title")
            return (
                (" + ".join(parts) + " Mismatch")
                if parts else "Mismatch")
        if kind == "separator":
            return "Separator Mismatch"
        if kind == "collab":
            return "Collaboration Tag Mismatch"
        return "Mismatch"


    # ------------------------------------------------------------------
    # Artist + Title sections
    # ------------------------------------------------------------------
    def _build_at_sections(self, card, cluster,
                            stem_to_recs, checked_vars,
                            all_paths, status_lbl):
        artist_parts = cluster["artist_parts"]
        title_parts  = cluster["title_parts"]


        if cluster.get("artist_mismatch"):
            variants = list(
                dict.fromkeys(artist_parts.values()))
            default  = self._dominant_variant(
                artist_parts, stem_to_recs)
            self._build_field_section(
                card=card,
                section_label="🎤 Artist mismatch",
                variants=variants,
                default=default,
                apply_callback=lambda canon, paths, ut=True, uf=True, _c=cluster: self._apply_artist_fix(
                    canon, paths, _c, status_lbl, ut, uf),
                checked_vars=checked_vars,
                all_paths=all_paths,
                status_lbl=status_lbl,
            )


        if cluster.get("title_mismatch"):
            variants = list(
                dict.fromkeys(title_parts.values()))
            default  = self._dominant_variant(
                title_parts, stem_to_recs)
            self._build_field_section(
                card=card,
                section_label="📝 Title mismatch",
                variants=variants,
                default=default,
                apply_callback=lambda canon, paths, ut=True, uf=True, _c=cluster: self._apply_title_fix(
                    canon, paths, _c, status_lbl, ut, uf),
                checked_vars=checked_vars,
                all_paths=all_paths,
                status_lbl=status_lbl,
            )


    # ------------------------------------------------------------------
    # Generic field section
    # ------------------------------------------------------------------
    def _build_field_section(self, card, section_label,
                              variants, default,
                              apply_callback,
                              checked_vars, all_paths, status_lbl):
        """
        Generic field section for artist or title mismatches.


        Changes vs previous version:
        - entry_var starts EMPTY — placeholder_text guides
          the user to pick or type.
        - Quick-pick buttons track which is selected and
          highlight the active one in orange.
        - Apply is blocked if the entry is empty.
        """
        ctk.CTkFrame(
            card, height=1, fg_color="gray30",
        ).pack(fill="x", padx=12, pady=(4, 0))


        sec = ctk.CTkFrame(card, fg_color="transparent")
        sec.pack(fill="x", padx=12, pady=(6, 2))


        ctk.CTkLabel(
            sec, text=section_label,
            font=("", 12, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 4))


        pick_row = ctk.CTkFrame(
            sec, fg_color="transparent")
        pick_row.pack(fill="x")


        ctk.CTkLabel(
            pick_row, text="Normalize to:",
            font=("", 11),
        ).pack(side="left", padx=(0, 6))


        entry_var = ctk.StringVar(value="")


        # Keep references to quick-pick buttons so we can
        # update their appearance when one is selected
        pick_buttons: list[ctk.CTkButton] = []


        # Styles
        _style_default = dict(
            fg_color="transparent",
            border_width=1,
            border_color=ACCENT_BLUE_MID,
            text_color=TEXT_ADAPTIVE,
        )
        _style_selected = dict(
            fg_color=ORANGE_PRIMARY,
            border_width=2,
            border_color=ORANGE_HOVER,
            text_color=TEXT_PRIMARY,
        )


        def _on_pick(variant: str, btn_idx: int):
            """Set entry value and highlight the clicked button."""
            entry_var.set(variant)
            for i, b in enumerate(pick_buttons):
                if i == btn_idx:
                    b.configure(**_style_selected)
                else:
                    b.configure(**_style_default)


        def _on_entry_change(*_):
            """
            When the user types manually, deselect all
            quick-pick buttons since none matches anymore.
            """
            typed = entry_var.get()
            for i, b in enumerate(pick_buttons):
                # Re-highlight if typed value matches
                # this button's variant exactly
                if typed == variants[i]:
                    b.configure(**_style_selected)
                else:
                    b.configure(**_style_default)


        entry_var.trace_add("write", _on_entry_change)


        for idx, variant in enumerate(variants[:6]):
            btn = ctk.CTkButton(
                pick_row,
                text=variant,
                width=0, height=26, font=("", 11),
                **_style_default,
                hover_color=ACCENT_BLUE,
                command=lambda v=variant, i=idx:
                _on_pick(v, i),
            )
            btn.pack(side="left", padx=3)
            pick_buttons.append(btn)


        entry = ctk.CTkEntry(
            pick_row,
            textvariable=entry_var,
            width=180,
            placeholder_text=(
                "Pick a variant or type here…"),
        )
        entry.pack(side="left", padx=(8, 0))

        undo_stack = [""]

        def _on_entry_write(*_):
            val = entry_var.get()
            if not undo_stack or undo_stack[-1] != val:
                undo_stack.append(val)
                if len(undo_stack) > 50:
                    undo_stack.pop(0)

        entry_var.trace_add("write", _on_entry_write)

        def _on_ctrl_z(event):
            if len(undo_stack) > 1:
                undo_stack.pop() # remove current state
                prev = undo_stack[-1]
                entry_var.set(prev)
                entry.icursor("end")
            return "break"

        def _on_escape(event):
            self.focus_set()  # Move focus away from entry

        entry.bind("<Escape>", _on_escape)
        entry.bind("<Control-z>", _on_ctrl_z)
        
        # Local click-away unfocus (safe for multiple entries)
        def _on_bg_click(event):
            self.focus_set()
            
        pick_row.bind("<Button-1>", _on_bg_click)
        sec.bind("<Button-1>", _on_bg_click)


        apply_row = ctk.CTkFrame(
            sec, fg_color="transparent")
        apply_row.pack(fill="x", pady=(4, 0))


        def _apply_checked():
            val = entry_var.get().strip()
            if not val:
                status_lbl.configure(
                    text=(
                        "⚠ Pick a variant or type "
                        "a value before applying."),
                    text_color=WARNING_YELLOW)
                self._set_sidebar_status(
                    "⚠ No value selected.",
                    WARNING_YELLOW)
                return
            checked_paths = [p for p in all_paths if checked_vars[p].get()]
            if not checked_paths:
                status_lbl.configure(
                    text="No files are checked. Check at least one file to apply.",
                    text_color=WARNING_YELLOW)
                return
            self._show_apply_options_dialog(
                lambda ut, uf: apply_callback(val, checked_paths, ut, uf)
            )


        def _apply_all():
            val = entry_var.get().strip()
            if not val:
                status_lbl.configure(
                    text=(
                        "⚠ Pick a variant or type "
                        "a value before applying."),
                    text_color=WARNING_YELLOW)
                self._set_sidebar_status(
                    "⚠ No value selected.",
                    WARNING_YELLOW)
                return
            self._show_apply_options_dialog(
                lambda ut, uf: apply_callback(val, list(all_paths), ut, uf)
            )


        ctk.CTkButton(
            apply_row, text="Apply to checked",
            width=130, height=26, font=("", 11),
            command=_apply_checked,
        ).pack(side="left", padx=(0, 6))


        ctk.CTkButton(
            apply_row, text="Apply to all",
            width=100, height=26, font=("", 11),
            command=_apply_all,
        ).pack(side="left")


    # ------------------------------------------------------------------
    # Separator section
    # ------------------------------------------------------------------
    def _build_sep_section(self, card, cluster,
                            stem_to_recs, checked_vars,
                            all_paths, status_lbl):
        separators = cluster.get("separators", {})
        found_seps = sorted({
            v for v in separators.values()
            if v != " - "})


        ctk.CTkFrame(
            card, height=1, fg_color="gray30",
        ).pack(fill="x", padx=12, pady=(4, 0))


        sec = ctk.CTkFrame(card, fg_color="transparent")
        sec.pack(fill="x", padx=12, pady=(6, 2))


        ctk.CTkLabel(
            sec, text="⚠ Separator mismatch",
            font=("", 12, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 2))


        if found_seps:
            found_text = "  ".join(
                f'"{s.strip()}"' for s in found_seps)
            ctk.CTkLabel(
                sec,
                text=(
                    f"Non-standard separators found: "
                    f"{found_text}"),
                font=("", 11),
                text_color=TEXT_MUTED, anchor="w",
            ).pack(anchor="w", pady=(0, 4))


        pick_row = ctk.CTkFrame(
            sec, fg_color="transparent")
        pick_row.pack(fill="x")
        ctk.CTkLabel(
            pick_row, text="Normalize to:",
            font=("", 11),
        ).pack(side="left", padx=(0, 6))


        sep_var = ctk.StringVar(value=" - ")
        for opt in _SEP_OPTIONS:
            ctk.CTkButton(
                pick_row, text=f'"{opt}"',
                width=0, height=26, font=("", 11),
                fg_color=(
                    ACCENT_BLUE_MID
                    if opt == " - "
                    else "transparent"),
                border_width=(
                    0 if opt == " - " else 1),
                hover_color=ACCENT_BLUE,
                text_color=TEXT_ADAPTIVE,
                command=lambda o=opt: sep_var.set(o),
            ).pack(side="left", padx=3)
        ctk.CTkEntry(
            pick_row,
            textvariable=sep_var, width=80,
        ).pack(side="left", padx=(8, 0))


        apply_row = ctk.CTkFrame(
            sec, fg_color="transparent")
        apply_row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            apply_row, text="Apply to checked",
            width=130, height=26, font=("", 11),
            command=lambda sv=sep_var,
            cv=checked_vars, ap=all_paths: (
                self._apply_separator_fix(
                    sv.get(),
                    [p for p in ap if cv[p].get()],
                    cluster, status_lbl)),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            apply_row, text="Apply to all",
            width=100, height=26, font=("", 11),
            command=lambda sv=sep_var,
            ap=all_paths: (
                self._apply_separator_fix(
                    sv.get(), list(ap),
                    cluster, status_lbl)),
        ).pack(side="left")


    # ------------------------------------------------------------------
    # Collaboration tag section
    # ------------------------------------------------------------------
    def _build_collab_section(self, card, cluster,
                               stem_to_recs,
                               checked_vars,
                               all_paths, status_lbl):
        keywords    = cluster.get("keywords", {})
        base_artist = cluster.get("base_artist", "")
        found_kws   = sorted({
            v for v in keywords.values() if v})


        ctk.CTkFrame(
            card, height=1, fg_color="gray30",
        ).pack(fill="x", padx=12, pady=(4, 0))


        sec = ctk.CTkFrame(card, fg_color="transparent")
        sec.pack(fill="x", padx=12, pady=(6, 2))


        ctk.CTkLabel(
            sec,
            text="🤝 Collaboration tag mismatch",
            font=("", 12, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 2))


        kw_display = ", ".join(
            f'"{k}"' for k in found_kws)
        ctk.CTkLabel(
            sec,
            text=(
                f"Base artist: \"{base_artist}\"  —  "
                f"Keyword variants: {kw_display}"),
            font=("", 11),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(anchor="w", pady=(0, 4))


        pick_row = ctk.CTkFrame(
            sec, fg_color="transparent")
        pick_row.pack(fill="x")
        ctk.CTkLabel(
            pick_row, text="Normalize to:",
            font=("", 11),
        ).pack(side="left", padx=(0, 6))


        collab_var = ctk.StringVar(value="ft.")
        shown: list = list(found_kws)
        for opt in _COLLAB_OPTIONS:
            if opt.lower() not in [
                    s.lower() for s in shown]:
                shown.append(opt)


        for opt in shown[:7]:
            is_detected = opt in found_kws
            ctk.CTkButton(
                pick_row, text=opt,
                width=0, height=26, font=("", 11),
                fg_color=(
                    ACCENT_BLUE_MID
                    if is_detected
                    else "transparent"),
                border_width=(
                    0 if is_detected else 1),
                hover_color=ACCENT_BLUE,
                text_color=TEXT_ADAPTIVE,
                command=lambda o=opt:
                collab_var.set(o),
            ).pack(side="left", padx=3)
        ctk.CTkEntry(
            pick_row,
            textvariable=collab_var, width=80,
        ).pack(side="left", padx=(8, 0))


        apply_row = ctk.CTkFrame(
            sec, fg_color="transparent")
        apply_row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            apply_row, text="Apply to checked",
            width=130, height=26, font=("", 11),
            command=lambda cv_=collab_var,
            cv=checked_vars, ap=all_paths: (
                self._apply_collab_fix_with_dialog(
                    cv_.get().strip(),
                    [p for p in ap if cv[p].get()],
                    cluster, status_lbl)),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            apply_row, text="Apply to all",
            width=100, height=26, font=("", 11),
            command=lambda cv_=collab_var,
            ap=all_paths: (
                self._apply_collab_fix_with_dialog(
                    cv_.get().strip(), list(ap),
                    cluster, status_lbl)),
        ).pack(side="left")


    # ------------------------------------------------------------------
    # Dismiss / Never show again / View files
    # ------------------------------------------------------------------
    def _build_dismiss_row(self, card, cluster,
                            stems, all_paths,
                            checked_vars,
                            status_lbl):
        # ── View files row ────────────────────────────
        view_row = ctk.CTkFrame(
            card, fg_color="transparent")
        view_row.pack(
            fill="x", padx=12, pady=(6, 2))

        def _view_selected():
            selected = [
                p for p in all_paths
                if checked_vars[p].get()]
            if not selected:
                status_lbl.configure(
                    text=(
                        "⚠ No files are checked. "
                        "Check at least one file "
                        "to use 'View Selected'."),
                    text_color=WARNING_YELLOW)
                return
            self._fix_filename_cluster(selected)

        def _view_all():
            self._fix_filename_cluster(
                set(all_paths))

        ctk.CTkButton(
            view_row,
            text="🔍 View Selected",
            width=120,
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            font=("", 11, "bold"),
            command=_view_selected,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            view_row,
            text="🔍 View All Files",
            width=120,
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            font=("", 11, "bold"),
            command=_view_all,
        ).pack(side="left")

        # ── Dismiss row ───────────────────────────────
        dismiss_row = ctk.CTkFrame(
            card, fg_color="transparent")
        dismiss_row.pack(
            fill="x", padx=12, pady=(2, 10))

        def _dismiss():
            try:
                card.destroy()
            except Exception:
                pass

        def _never_show():
            for i, a in enumerate(stems):
                for b in stems[i + 1:]:
                    lo, hi = sorted(
                        [a.lower(), b.lower()])
                    self._fuzzy_ignore_pairs.add(
                        f"{lo}|||{hi}")
            _save_config(self._current_config_dict())
            try:
                card.destroy()
            except Exception:
                pass

        ctk.CTkButton(
            dismiss_row, text="Dismiss", width=90,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=_dismiss,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            dismiss_row,
            text="Never show again", width=130,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            font=("", 11),
            command=_never_show,
        ).pack(side="right", padx=(0, 4))


    # ------------------------------------------------------------------
    # Apply actions
    # ------------------------------------------------------------------
    def _dominant_variant(self, parts_dict: dict,
                           stem_to_recs: dict) -> str:
        counts: Counter = Counter()
        for stem, val in parts_dict.items():
            counts[val] += len(
                stem_to_recs.get(stem, []))
        return (
            counts.most_common(1)[0][0]
            if counts else "")


    def _apply_artist_fix(self, canonical: str,
                           paths: list,
                           cluster: dict,
                           status_lbl,
                           update_tags: bool = True,
                           update_filenames: bool = True):
        if not canonical.strip():
            return
        if not paths:
            status_lbl.configure(
                text="No files are checked. Check at least one file to apply.",
                text_color=WARNING_YELLOW)
            return
        naming  = self.naming_convention_var.get()
        changed = 0
        snapshot_pushed = False
        for path in paths:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            stem, ext     = os.path.splitext(
                rec["filename"])
            _, title_part = _split_stem(stem, naming)
            if not title_part:
                continue
            new_fn = (
                f"{canonical} - {title_part}{ext}"
                if naming == "Artist - Title"
                else
                f"{title_part} - {canonical}{ext}")
            
            # Skip if nothing actually changed
            fn_changed = (rec["filename"] != new_fn) if update_filenames else False
            tag_changed = (rec.get("artist") != canonical) if update_tags else False
            if not fn_changed and not tag_changed:
                continue

            if not snapshot_pushed:
                self._push_undo_snapshot()
                snapshot_pushed = True
            self._snapshot_original(path)
            if update_filenames:
                rec["filename"] = new_fn
            if update_tags:
                rec["artist"]   = canonical
            self._dirty_paths.add(path)
            self._update_tree_row(path, rec)
            if path in self._scanned_unorganized:
                self._update_unorg_row(path)
            changed += 1
        if changed:
            self._fuzzy_stale = True
            self.distinct_artists = {
                r["artist"]
                for r in self.all_files_data.values()
                if r["artist"] not in ("Unknown", "")
            }
            self._invalidate_unorg_cache()
            self._update_status_bar()
            self._update_unsaved_banner()
            status_lbl.configure(
                text=(
                    f"✔ Artist updated for "
                    f"{changed} file(s). "
                    f"Refresh to update remaining "
                    f"mismatches."),
                text_color=SUCCESS_GREEN)
        else:
            status_lbl.configure(
                text=(
                    "No changes needed — selected "
                    "files already use this value."),
                text_color=WARNING_YELLOW)


    def _apply_title_fix(self, canonical: str,
                           paths: list,
                           cluster: dict,
                           status_lbl,
                           update_tags: bool = True,
                           update_filenames: bool = True):
        if not canonical.strip():
            return
        if not paths:
            status_lbl.configure(
                text="No files are checked. Check at least one file to apply.",
                text_color=WARNING_YELLOW)
            return
        naming  = self.naming_convention_var.get()
        changed = 0
        snapshot_pushed = False
        for path in paths:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            stem, ext      = os.path.splitext(
                rec["filename"])
            artist_part, _ = _split_stem(stem, naming)
            if not artist_part:
                continue
            new_fn = (
                f"{artist_part} - {canonical}{ext}"
                if naming == "Artist - Title"
                else
                f"{canonical} - {artist_part}{ext}")
            
            # Skip if nothing actually changed
            fn_changed = (rec["filename"] != new_fn) if update_filenames else False
            tag_changed = (rec.get("title") != canonical) if update_tags else False
            if not fn_changed and not tag_changed:
                continue

            if not snapshot_pushed:
                self._push_undo_snapshot()
                snapshot_pushed = True
            self._snapshot_original(path)
            if update_filenames:
                rec["filename"] = new_fn
            if update_tags:
                rec["title"]    = canonical
            self._dirty_paths.add(path)
            self._update_tree_row(path, rec)
            if path in self._scanned_unorganized:
                self._update_unorg_row(path)
            changed += 1
        if changed:
            self._fuzzy_stale = True
            self._invalidate_unorg_cache()
            self._update_status_bar()
            self._update_unsaved_banner()
            status_lbl.configure(
                text=(
                    f"✔ Title updated for "
                    f"{changed} file(s). "
                    f"Refresh to update remaining "
                    f"mismatches."),
                text_color=SUCCESS_GREEN)
        else:
            status_lbl.configure(
                text=(
                    "No changes needed — selected "
                    "files already use this value."),
                text_color=WARNING_YELLOW)


    def _apply_separator_fix(self, canonical_sep: str,
                              paths: list,
                              cluster: dict,
                              status_lbl):
        if not canonical_sep:
            return
        if not paths:
            status_lbl.configure(
                text="No files are checked. Check at least one file to apply.",
                text_color=WARNING_YELLOW)
            return
        changed = 0
        snapshot_pushed = False
        for path in paths:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            stem, ext = os.path.splitext(
                rec["filename"])
            new_stem  = _SEP_VARIANTS.sub(
                canonical_sep, stem, count=1)
            if new_stem == stem:
                continue
            if not snapshot_pushed:
                self._push_undo_snapshot()
                snapshot_pushed = True
            self._snapshot_original(path)
            rec["filename"] = new_stem + ext
            self._dirty_paths.add(path)
            self._update_tree_row(path, rec)
            if path in self._scanned_unorganized:
                self._update_unorg_row(path)
            changed += 1
        if changed:
            self._fuzzy_stale = True
            self._invalidate_unorg_cache()
            self._update_status_bar()
            self._update_unsaved_banner()
            status_lbl.configure(
                text=(
                    f"✔ Separator fixed for "
                    f"{changed} file(s). "
                    f"Refresh to update remaining "
                    f"mismatches."),
                text_color=SUCCESS_GREEN)
        else:
            status_lbl.configure(
                text=(
                    "No changes needed — selected "
                    "files already use this separator."),
                text_color=WARNING_YELLOW)


    def _apply_collab_fix(self, canonical_kw: str,
                           paths: list,
                           cluster: dict,
                           status_lbl,
                           update_tags: bool = True,
                           update_filenames: bool = True):
        if not canonical_kw.strip():
            return
        if not paths:
            status_lbl.configure(
                text="No files are checked. Check at least one file to apply.",
                text_color=WARNING_YELLOW)
            return
        naming  = self.naming_convention_var.get()
        changed = 0
        snapshot_pushed = False
        for path in paths:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            stem, ext = os.path.splitext(
                rec["filename"])
            artist_part, title_part = _split_stem(
                stem, naming)
            if not artist_part:
                continue
            new_artist = _COLLAB_KEYWORDS.sub(
                canonical_kw, artist_part, count=1)
            if new_artist == artist_part:
                continue
            new_fn = (
                f"{new_artist} - {title_part}{ext}"
                if naming == "Artist - Title"
                else
                f"{title_part} - {new_artist}{ext}")
            
            # Skip if nothing actually changed
            fn_changed = (rec["filename"] != new_fn) if update_filenames else False
            tag_changed = (rec.get("artist") != new_artist) if update_tags else False
            if not fn_changed and not tag_changed:
                continue

            if not snapshot_pushed:
                self._push_undo_snapshot()
                snapshot_pushed = True
            self._snapshot_original(path)
            if update_filenames:
                rec["filename"] = new_fn
            if update_tags:
                rec["artist"]   = new_artist
            self._dirty_paths.add(path)
            self._update_tree_row(path, rec)
            if path in self._scanned_unorganized:
                self._update_unorg_row(path)
            changed += 1
        if changed:
            self._fuzzy_stale = True
            self.distinct_artists = {
                r["artist"]
                for r in self.all_files_data.values()
                if r["artist"] not in ("Unknown", "")
            }
            self._invalidate_unorg_cache()
            self._update_status_bar()
            self._update_unsaved_banner()
            status_lbl.configure(
                text=(
                    f"✔ Collaboration tag updated for "
                    f"{changed} file(s). "
                    f"Refresh to update remaining "
                    f"mismatches."),
                text_color=SUCCESS_GREEN)
        else:
            status_lbl.configure(
                text=(
                    "No changes needed — selected "
                    "files already use this keyword."),
                text_color=WARNING_YELLOW)


    def _on_fuzzy_slider_change(self, value: float):
        self.fuzzy_val_label.configure(
            text=f"{int(value)}%")

    def _apply_collab_fix_with_dialog(self, canonical_kw: str, paths: list, cluster: dict, status_lbl):
        if not canonical_kw.strip():
            return
        if not paths:
            status_lbl.configure(
                text="No files are checked. Check at least one file to apply.",
                text_color=WARNING_YELLOW)
            return
        self._show_apply_options_dialog(
            lambda ut, uf: self._apply_collab_fix(canonical_kw, paths, cluster, status_lbl, ut, uf)
        )

    def _show_apply_options_dialog(self, on_confirm):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Apply Options")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 380, 180)

        ctk.CTkLabel(
            dialog,
            text="Choose what to update:",
            font=("", 13, "bold"),
        ).pack(pady=(16, 8), padx=20, anchor="w")

        update_tags_var = ctk.BooleanVar(value=True)
        update_filenames_var = ctk.BooleanVar(value=True)

        ctk.CTkCheckBox(
            dialog,
            text="Update audio tags (Artist / Title)",
            variable=update_tags_var,
        ).pack(pady=4, padx=24, anchor="w")

        ctk.CTkCheckBox(
            dialog,
            text="Update filenames",
            variable=update_filenames_var,
        ).pack(pady=4, padx=24, anchor="w")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(pady=(12, 12))

        def _confirmed():
            ut = update_tags_var.get()
            uf = update_filenames_var.get()
            if not ut and not uf:
                self._show_info_dialog(
                    "Invalid Selection",
                    "You must select at least one option (Tags or Filenames) to update.")
                return
            dialog.destroy()
            on_confirm(ut, uf)

        ctk.CTkButton(
            btn_row, text="Apply", width=90,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=_confirmed,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            btn_row, text="Cancel", width=90,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy,
        ).pack(side="left", padx=6)

