# app/ui_all_files.py
"""
AllFilesMixin — All Files tab core: spreadsheet treeview, search,
refresh-from-disk, populate, selection sync, location tooltip, and
the O(1) row-update helper.

Inline filename editing and the right-click revert menu live in
AllFilesEditMixin (ui_all_files_edit.py).
File deletion and duplicate detection live in AllFilesActionsMixin
(ui_all_files_actions.py).
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk


from app.constants import (
    COL_IDS, COL_DEFS, COL_LABELS,
    PINNED_BG, PINNED_FG,
    WARNING_ON_LIGHT, DANGER_RED, DANGER_RED_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_ADAPTIVE,
    TEXT_WARNING, SAVE_BLUE, SAVE_BLUE_HOVER,
    HEADING_BG, HEADING_BG_ACTIVE,
    SUCCESS_GREEN,
)
from app.helpers import (
    _format_length, _sort_key, _TreeviewTooltip,
    _setup_treeview_keyboard_navigation,
)




class AllFilesMixin:
    # _is_path_checked lives in UnorganizedMixin.


    # ------------------------------------------------------------------
    # Treeview style
    # ------------------------------------------------------------------
    def _setup_treeview_style(self):
        """
        Configure the ttk Treeview style.


        IMPORTANT: do NOT set background or fieldbackground
        on the global "Treeview" style. On Windows, doing so
        overrides all tag-based background colours, making
        tag_configure("has_suggestion", background=...) and
        tag_configure("dirty", background=...) invisible.
        Row backgrounds are provided entirely by the "even",
        "odd", "dirty", and "has_suggestion" tags instead.
        """
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure(
            "Treeview",
            foreground=TEXT_PRIMARY,
            rowheight=30,
            font=("", 11))
        # NOTE: do NOT add background here. On Windows, any background
        # entry in style.map overrides ALL tag_configure backgrounds,
        # making dirty/even/odd/has_suggestion colours invisible.
        # The native Windows selection colour (blue) is used instead.
        style.map(
            "Treeview",
            foreground=[("selected", TEXT_PRIMARY)])
        style.configure(
            "Treeview.Heading",
            background=HEADING_BG,
            foreground=TEXT_PRIMARY,
            font=("", 12, "bold"),
            relief="raised")
        style.map(
            "Treeview.Heading",
            background=[("active", HEADING_BG_ACTIVE)],
            foreground=[
                ("active",    TEXT_PRIMARY),
                ("!disabled", TEXT_PRIMARY)])


    # ------------------------------------------------------------------
    # Spreadsheet factory
    # ------------------------------------------------------------------
    def _create_spreadsheet(self, parent) -> ttk.Treeview:
        frame = ctk.CTkFrame(parent, corner_radius=0)
        frame.pack(fill="both", expand=True, padx=5, pady=5)


        y_bar = ctk.CTkScrollbar(frame, orientation="vertical")
        y_bar.pack(side="right", fill="y")
        x_bar = ctk.CTkScrollbar(frame, orientation="horizontal")
        x_bar.pack(side="bottom", fill="x")


        tree = ttk.Treeview(
            frame, columns=COL_IDS, show="headings",
            selectmode="extended",
            yscrollcommand=y_bar.set,
            xscrollcommand=x_bar.set)
        y_bar.configure(command=tree.yview)
        x_bar.configure(command=tree.xview)
        tree.sort_states = {col: False for col in COL_IDS}


        def sort_column(col: str):
            reverse = tree.sort_states[col]
            rows    = [(tree.set(k, col), k)
                       for k in tree.get_children("")]
            rows.sort(key=lambda t: _sort_key(t[0]),
                      reverse=reverse)
            for i, (_, k) in enumerate(rows):
                tree.move(k, "", i)
                base_tag = "even" if i % 2 == 0 else "odd"
                if k in self._dirty_paths:
                    tags = (f"{base_tag}_dirty",)
                else:
                    tags = (base_tag,)
                tree.item(k, tags=tags)
            for cid in COL_IDS:
                base      = COL_LABELS[cid]
                indicator = ((" ▼" if reverse else " ▲")
                             if cid == col else "")
                tree.heading(cid, text=base + indicator,
                             command=lambda c=cid: sort_column(c))
            tree.sort_states[col] = not reverse


        for col_id, label, w, mw, stretch in COL_DEFS:
            tree.heading(col_id, text=label, anchor="w",
                         command=lambda c=col_id: sort_column(c))
            tree.column(col_id, width=w, minwidth=mw,
                        stretch=stretch)


        _tv = self._get_tv_theme_colours()
        tree.tag_configure(
            "even",
            background=_tv["row_even"],
            foreground=_tv["text"])
        tree.tag_configure(
            "odd",
            background=_tv["row_odd"],
            foreground=_tv["text"])
        tree.tag_configure(
            "dirty",
            background=_tv["dirty_bg"],
            foreground=_tv["dirty_fg"])
        tree.tag_configure(
            "even_dirty",
            background=_tv["dirty_bg"],
            foreground=_tv["dirty_fg"])
        tree.tag_configure(
            "odd_dirty",
            background=_tv["dirty_bg"],
            foreground=_tv["dirty_fg"])
        tree.pack(side="left", fill="both", expand=True)
        self.active_trees.append(tree)


        tree.bind("<Delete>",
                  lambda e: self._on_delete_key(e, tree))
        tree.bind("<Double-1>",
                  lambda e, t=tree:
                  self._on_all_files_double_click(e, t))
        tree.bind("<F2>",
                  lambda e, t=tree:
                  self._on_all_files_f2(e, t))
        tree.bind("<Button-3>",
                  lambda e, t=tree:
                  self._on_all_files_right_click(e, t))



        _TreeviewTooltip(
            tree,
            col_id="location",
            text_getter=lambda iid: (
                self.all_files_data[iid]["path"]
                if iid in self.all_files_data else ""))

        _setup_treeview_keyboard_navigation(tree)

        return tree


    def _record_to_row(self, rec: dict) -> tuple:
        return (
            rec["filename"],
            rec["title"],
            rec["artist"],
            rec["album"],
            f"{rec['bitrate']} kbps",
            _format_length(rec["length"]),
            rec["date_modified"],
            rec.get("location", ""),
        )


    def _populate_spreadsheet(self, tree: ttk.Treeview,
                               records: dict):
        for idx, rec in enumerate(records.values()):
            base_tag = "even" if idx % 2 == 0 else "odd"
            if rec["path"] in self._dirty_paths:
                tags = (f"{base_tag}_dirty",)
            else:
                tags = (base_tag,)
            tree.insert("", "end", iid=rec["path"],
                        tags=tags,
                        values=self._record_to_row(rec))


    def _bind_row_click(self, tree: ttk.Treeview, records: dict):
        def on_click(_event):
            if self._select_debounce_id is not None:
                try:
                    self.after_cancel(self._select_debounce_id)
                except Exception:
                    pass
            self._select_debounce_id = self.after(
                50,
                lambda:
                self._on_all_files_selection_changed(
                    tree, records))
        tree.bind("<<TreeviewSelect>>", on_click)
        # Arrow key navigation also fires
        # <<TreeviewSelect>> in ttk but with a short
        # delay the selection may not have updated yet.
        # Binding directly to key events with a slightly
        # longer delay ensures the sidebar updates
        # correctly when the user navigates with arrows.
        def on_arrow(_event):
            if self._select_debounce_id is not None:
                try:
                    self.after_cancel(self._select_debounce_id)
                except Exception:
                    pass
            self._select_debounce_id = self.after(
                80,
                lambda:
                self._on_all_files_selection_changed(
                    tree, records))
        tree.bind("<Up>",    on_arrow, add="+")
        tree.bind("<Down>",  on_arrow, add="+")


    def _on_all_files_selection_changed(self, tree: ttk.Treeview,
                                         records: dict):
        selected = tree.selection()
        if not selected:
            return
        self._sidebar_selected_paths = list(selected)
        self._all_files_sidebar_selected_paths = list(selected)
        if len(selected) == 1:
            iid = selected[0]
            rec = records.get(iid)
            if rec is None:
                return
            self._display_cover_art(iid)
            self._set_sidebar_single(rec)
            self._sidebar_context = "all_files"
            self.save_metadata_btn.configure(
                state="normal",
                text="Save Changes")
            self.analyze_track_btn.configure(
                state="normal"
                if self.organize_strategy_var.get()
                == "gemini"
                else "disabled")
            self._sidebar_active_path = iid
            self._all_files_sidebar_active_path = iid
            self.multi_hint_lbl.configure(
                text="", text_color=TEXT_ADAPTIVE)
            self.multi_hint_header_lbl.configure(
                text="", text_color=TEXT_ADAPTIVE)
        else:
            self._set_sidebar_multi(list(selected), records)
            self._set_cover_text("[Multiple\nSelected]")
            self._sidebar_context = "all_files"
            self.save_metadata_btn.configure(
                state="normal",
                text="Save Changes")
            self.analyze_track_btn.configure(state="disabled")
            self._sidebar_active_path = None
            self._all_files_sidebar_active_path = None
            self.multi_hint_header_lbl.configure(
                text=f"{len(selected)} files selected.",
                text_color=TEXT_ADAPTIVE)
            self.multi_hint_lbl.configure(
                text=(
                    f"Select a field value from the dropdown or "
                    f"type a new value to apply to all.\n\n"
                    f"'{self._MULTI_REMOVE}' clears a field.\n"
                    f"'{self._MULTI_KEEP}' leaves it unchanged."
                ),
                text_color=TEXT_ADAPTIVE)


    # ------------------------------------------------------------------
    # Populate All Files tab
    # ------------------------------------------------------------------
    def _populate_all_files_tab(self):
        self.active_trees = [t for t in self.active_trees
                             if t.winfo_exists()]


        if (hasattr(self, "_all_files_tree") and
                self._all_files_tree.winfo_exists()):
            tree         = self._all_files_tree
            existing_set = set(tree.get_children(""))
            new_set      = set(self.all_files_data.keys())
            if existing_set == new_set:
                for path, rec in self.all_files_data.items():
                    self._update_tree_row(path, rec)
                self._apply_search_filter()
                if hasattr(self, "_search_count_lbl"):
                    query = (
                        self._search_var.get().strip()
                        if hasattr(self, "_search_var")
                        else "")
                    total = len(self.all_files_data)
                    if not query:
                        self._search_count_lbl.configure(
                            text=f"{total} file(s)")
                if hasattr(self, "_all_files_tree"):
                    for cid in COL_IDS:
                        self._all_files_tree.heading(
                            cid,
                            text=COL_LABELS[cid])
                return


        self._clear_tab(self.tab_all_files)
        self._search_detached.clear()

        if not self.all_files_data:
            ctk.CTkLabel(
                self.tab_all_files,
                text="No supported audio files found.",
                text_color=TEXT_SECONDARY).pack(pady=20)
            return


        tab_toolbar = ctk.CTkFrame(
            self.tab_all_files, fg_color="transparent")
        tab_toolbar.pack(fill="x", padx=5, pady=(5, 0))


        ctk.CTkLabel(tab_toolbar, text="🔍 Search:",
                     font=("", 12)).pack(
            side="left", padx=(5, 4))
        self._search_var = ctk.StringVar()

        # Search entry + ✕ clear button in a shared frame
        search_frame = ctk.CTkFrame(
            tab_toolbar, fg_color="transparent")
        search_frame.pack(side="left", padx=(0, 6))

        ctk.CTkEntry(
            search_frame,
            textvariable=self._search_var,
            placeholder_text=(
                "Filter by filename, title, artist or album…"),
            width=320
        ).pack(side="left")

        self._search_clear_btn = ctk.CTkButton(
            search_frame,
            text="✕",
            width=28, height=28,
            font=("", 11),
            fg_color="transparent",
            hover_color=DANGER_RED,
            text_color=TEXT_ADAPTIVE,
            command=lambda: self._search_var.set(""))
        # Hidden by default — shown only when search has text
        # Do not pack yet; trace will show it when needed

        self._search_count_lbl = ctk.CTkLabel(
            tab_toolbar, text="",
            text_color=TEXT_MUTED, font=("", 11))
        self._search_count_lbl.pack(side="left", padx=10)


        # Right-side buttons (right to left)
        ctk.CTkButton(
            tab_toolbar, text="↺ Refresh", width=80,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._refresh_file_view
        ).pack(side="right", padx=(5, 5))
        ctk.CTkButton(
            tab_toolbar, text="⇄ Columns", width=90,
            command=self._open_column_reorder_dialog
        ).pack(side="right", padx=(0, 5))
        ctk.CTkButton(
            tab_toolbar, text="⬇ Export CSV", width=100,
            command=self._export_csv
        ).pack(side="right", padx=(0, 5))
        ctk.CTkButton(
            tab_toolbar, text="🔍 Duplicates", width=100,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._find_duplicates
        ).pack(side="right", padx=(0, 5))
        ctk.CTkButton(
            tab_toolbar, text="Fix Filenames", width=100,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._open_fix_filenames_dialog
        ).pack(side="right", padx=(0, 5))
        ctk.CTkButton(
            tab_toolbar, text="🗑 Delete", width=80,
            fg_color=DANGER_RED, hover_color=DANGER_RED_HOVER,
            command=self._delete_from_toolbar
        ).pack(side="right", padx=(0, 5))


        # Pinned banner
        self._pinned_banner = ctk.CTkFrame(
            self.tab_all_files, fg_color=PINNED_BG,
            corner_radius=0, height=30)
        self._pinned_banner.pack(fill="x", padx=0, pady=0)
        self._pinned_banner.pack_propagate(False)


        self._pinned_banner_lbl = ctk.CTkLabel(
            self._pinned_banner, text="",
            text_color=PINNED_FG, font=("", 11))
        self._pinned_banner_lbl.pack(
            side="left", padx=10, pady=5)


        ctk.CTkButton(
            self._pinned_banner, text="Exit",
            width=60, height=20, font=("", 11),
            fg_color="transparent", border_width=1,
            text_color=PINNED_FG,
            command=self._clear_pinned_filter
        ).pack(side="right", padx=8, pady=5)


        self._pinned_banner.pack_forget()


        tree = self._create_spreadsheet(self.tab_all_files)
        self._populate_spreadsheet(tree, self.all_files_data)
        self._bind_row_click(tree, self.all_files_data)
        self._all_files_tree       = tree
        self._all_files_tree_frame = tree.master


        def _on_search_trace(*_):
            self._on_search_var_changed()
            if self._search_var.get():
                self._search_clear_btn.pack(
                    side="left", padx=(2, 0))
            else:
                self._search_clear_btn.pack_forget()

        self._search_var.trace_add(
            "write", _on_search_trace)
        self._apply_search_filter()


    # ------------------------------------------------------------------
    # Column helpers
    # ------------------------------------------------------------------
    def _apply_column_order(self):
        if self._saved_column_order != list(COL_IDS):
            for t in self.active_trees:
                t.configure(
                    displaycolumns=self._saved_column_order)


    def _apply_search_filter(self):
        if not hasattr(self, "_all_files_tree"):
            return
        tree     = self._all_files_tree
        all_iids = list(self.all_files_data.keys())


        if self._search_pinned_paths is not None:
            visible = 0
            for idx, iid in enumerate(all_iids):
                in_set             = iid in self._search_pinned_paths
                currently_detached = iid in self._search_detached
                if in_set:
                    visible += 1
                    if currently_detached:
                        try:
                            tree.reattach(iid, "", idx)
                            self._search_detached.discard(iid)
                        except tk.TclError:
                            self._search_detached.discard(iid)
                else:
                    if (not currently_detached
                            and tree.exists(iid)):
                        tree.detach(iid)
                        self._search_detached.add(iid)
            self._refresh_pinned_banner(visible)
            total = len(self.all_files_data)
            if hasattr(self, "_search_count_lbl"):
                self._search_count_lbl.configure(
                    text=f"{visible} of {total} shown")
            return


        self._refresh_pinned_banner(0)
        query = self._search_var.get().strip().lower() \
            if hasattr(self, "_search_var") else ""


        if not query:
            for idx, iid in enumerate(all_iids):
                if iid in self._search_detached:
                    try:
                        tree.reattach(iid, "", idx)
                        self._search_detached.discard(iid)
                    except tk.TclError:
                        self._search_detached.discard(iid)
            visible = len(all_iids)
        else:
            visible = 0
            # Search across these column ids — resolve to
            # indices via COL_IDS so reordering COL_DEFS
            # cannot silently target the wrong columns.
            search_cols = (
                "filename", "title", "artist",
                "album", "location")
            search_idxs = tuple(
                COL_IDS.index(c)
                for c in search_cols
                if c in COL_IDS)
            for idx, iid in enumerate(all_iids):
                currently_detached = iid in self._search_detached
                try:
                    values = tree.item(iid, "values")
                except tk.TclError:
                    continue
                match = any(
                    query in str(values[i]).lower()
                    for i in search_idxs
                    if i < len(values)
                ) if values else False


                if match:
                    visible += 1
                    if currently_detached:
                        try:
                            tree.reattach(iid, "", idx)
                            self._search_detached.discard(iid)
                        except tk.TclError:
                            self._search_detached.discard(iid)
                else:
                    if (not currently_detached
                            and tree.exists(iid)):
                        tree.detach(iid)
                        self._search_detached.add(iid)


        total = len(self.all_files_data)
        if hasattr(self, "_search_count_lbl"):
            if query:
                self._search_count_lbl.configure(
                    text=f"{visible} of {total} shown")
            else:
                self._search_count_lbl.configure(
                    text=f"{total} file(s)")


    def _on_search_var_changed(self):
        if self._search_pinned_paths is not None:
            self._search_pinned_paths = None
        self._apply_search_filter()


    # ------------------------------------------------------------------
    # Pinned filter
    # ------------------------------------------------------------------
    def _fix_filename_cluster(self, cluster_paths: set,
                               origin: str = "Fuzzy Matches"):
        self._search_pinned_origin = origin
        self._switch_tab("All Files", clear_sidebar=False)
        self._search_pinned_paths = set(cluster_paths)
        self._apply_search_filter()
        if not (hasattr(self, "_all_files_tree") and
                self._all_files_tree.winfo_exists()):
            return
        matching = [
            path for path in self.all_files_data
            if path in self._search_pinned_paths and
            self._all_files_tree.exists(path)]
        if not matching:
            self._clear_sidebar()
            return
        first = matching[0]
        self._all_files_tree.selection_set((first,))
        self._all_files_tree.focus(first)
        try:
            self._all_files_tree.see(first)
        except Exception:
            pass
        self._on_all_files_selection_changed(
            self._all_files_tree,
            self.all_files_data)


    def _clear_pinned_filter(self):
        self._search_pinned_paths  = None
        self._search_pinned_origin = ""
        self._apply_search_filter()


    def _refresh_pinned_banner(self, count: int):
        if not hasattr(self, "_pinned_banner"):
            return
        if self._search_pinned_paths is not None:
            origin = getattr(
                self, "_search_pinned_origin",
                "Fuzzy Matches")
            self._pinned_banner_lbl.configure(
                text=(
                    f"📌  Showing {count} file(s) "
                    f"from {origin}."))
            self._pinned_banner.pack(
                fill="x", padx=0, pady=0,
                before=self._all_files_tree_frame)
        else:
            self._pinned_banner.pack_forget()

    # ------------------------------------------------------------------
    # Fix Filenames dialog
    # ------------------------------------------------------------------
    def _open_fix_filenames_dialog(
            self,
            mismatches: list | None = None):
        """
        Scans all files for filename mismatches and
        presents a dialog where the user can select
        which files to rename in bulk.
        All renames go through the review-before-commit
        workflow — nothing is written until the user
        confirms in the Review & Save Changes dialog.
        """
        if not self.all_files_data:
            self._show_info_dialog(
                "No Files Loaded",
                "Load a directory before scanning "
                "for filename mismatches.")
            return
        if self.is_loading:
            return

        if mismatches is None:
            mismatches = self._find_filename_mismatches()

        if not mismatches:
            self._show_info_dialog(
                "No Mismatches Found",
                "✔ All filenames match their tags.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title(
            f"Fix Filenames — "
            f"{len(mismatches)} mismatch(es) found")
        dialog.resizable(True, True)
        dialog.grab_set()
        self._center_dialog(dialog, 820, 580)

        # ── Header ──────────────────────────────────
        ctk.CTkLabel(
            dialog,
            text=(
                f"{len(mismatches)} file(s) whose "
                f"filename does not match their tags."),
            font=("", 13, "bold"),
        ).pack(pady=(16, 4), padx=20, anchor="w")

        ctk.CTkLabel(
            dialog,
            text=(
                "Click a row or use Shift/Ctrl+click "
                "to select. Space or click toggles "
                "the checkbox. Click column headers "
                "to sort."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=780,
        ).pack(pady=(0, 8), padx=20, anchor="w")

        # ── Treeview ─────────────────────────────────
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

        from tkinter import ttk
        cols = ("check", "current", "new")
        tree = ttk.Treeview(
            tree_frame, columns=cols,
            show="headings",
            selectmode="extended",
            yscrollcommand=y_bar.set,
            xscrollcommand=x_bar.set)
        y_bar.configure(command=tree.yview)
        x_bar.configure(command=tree.xview)

        _tv = self._get_tv_theme_colours()
        tree.tag_configure(
            "checked",
            background=_tv["row_even"],
            foreground=_tv["text"])
        tree.tag_configure(
            "unchecked",
            background=_tv["row_odd"],
            foreground=TEXT_MUTED)

        # Track checked state per path
        checked: dict = {
            path: True
            for path, _, _ in mismatches}

        rename_btn = None

        # Sort state per column
        sort_states: dict = {
            "check":   False,
            "current": False,
            "new":     False,
        }

        # Working list — sorted copy of mismatches
        rows: list = list(mismatches)

        def _refresh_row(path: str):
            if not tree.exists(path):
                return
            entry = next(
                (r for r in rows if r[0] == path),
                None)
            if not entry:
                return
            _, current, new = entry
            sym = "☑" if checked[path] else "☐"
            tag = (
                "checked"
                if checked[path]
                else "unchecked")
            tree.item(
                path,
                values=(sym, current, new),
                tags=(tag,))

        def _rebuild_tree():
            tree.delete(*tree.get_children())
            for path, current, new in rows:
                sym = "☑" if checked[path] else "☐"
                tag = (
                    "checked"
                    if checked[path]
                    else "unchecked")
                tree.insert(
                    "", "end", iid=path,
                    values=(sym, current, new),
                    tags=(tag,))
            _update_btn_label()

        def _sort_by(col: str):
            reverse = sort_states[col]
            if col == "check":
                rows.sort(
                    key=lambda r:
                    (0 if checked[r[0]] else 1),
                    reverse=reverse)
            elif col == "current":
                rows.sort(
                    key=lambda r: r[1].lower(),
                    reverse=reverse)
            elif col == "new":
                rows.sort(
                    key=lambda r: r[2].lower(),
                    reverse=reverse)
            sort_states[col] = not reverse
            indicator = " ▼" if reverse else " ▲"
            tree.heading(
                "check",
                text="☑" + (
                    indicator
                    if col == "check" else ""))
            tree.heading(
                "current",
                text="Current Filename" + (
                    indicator
                    if col == "current" else ""))
            tree.heading(
                "new",
                text="New Filename (from tags)" + (
                    indicator
                    if col == "new" else ""))
            _rebuild_tree()

        tree.heading(
            "check", text="☑", anchor="center",
            command=lambda: _sort_by("check"))
        tree.heading(
            "current",
            text="Current Filename", anchor="w",
            command=lambda: _sort_by("current"))
        tree.heading(
            "new",
            text="New Filename (from tags)",
            anchor="w",
            command=lambda: _sort_by("new"))

        tree.column(
            "check",   width=36,  minwidth=36,
            stretch=False, anchor="center")
        tree.column(
            "current", width=360, minwidth=200)
        tree.column(
            "new",     width=360, minwidth=200)

        tree.pack(fill="both", expand=True)

        def _toggle_path(path: str):
            if path not in checked:
                return
            checked[path] = not checked[path]
            _refresh_row(path)
            _update_btn_label()

        def _on_click(event):
            region = tree.identify_region(
                event.x, event.y)
            if region not in ("cell", "tree"):
                return
            path = tree.identify_row(event.y)
            if not path:
                return
            # Shift+click — set all selected rows to checked
            if event.state & 0x0001:
                for iid in tree.selection():
                    if iid in checked:
                        checked[iid] = True
                        _refresh_row(iid)
                _update_btn_label()
                return
            # Ctrl+click — toggle single
            if event.state & 0x0004:
                _toggle_path(path)
                return
            # Plain click — toggle single
            _toggle_path(path)

        def _on_space(event):
            for path in tree.selection():
                if path in checked:
                    _toggle_path(path)

        tree.bind("<ButtonRelease-1>", _on_click)
        tree.bind("<space>",           _on_space)

        def _select_all():
            for path in checked:
                checked[path] = True
                _refresh_row(path)
            _update_btn_label()

        def _deselect_all():
            for path in checked:
                checked[path] = False
                _refresh_row(path)
            _update_btn_label()

        def _update_btn_label():
            if rename_btn is None:
                return
            n = sum(
                1 for v in checked.values() if v)
            rename_btn.configure(
                text=f"Rename Selected ({n})",
                state="normal" if n > 0
                else "disabled")

        # ── Bottom row ───────────────────────────────
        bottom = ctk.CTkFrame(
            dialog, fg_color="transparent")
        bottom.pack(
            fill="x", padx=16, pady=(0, 16))

        sel_row = ctk.CTkFrame(
            bottom, fg_color="transparent")
        sel_row.pack(side="left")

        ctk.CTkButton(
            sel_row,
            text="☑ Select All",
            width=100, height=28,
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=_select_all,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            sel_row,
            text="☐ Deselect All",
            width=100, height=28,
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=_deselect_all,
        ).pack(side="left")

        rename_btn = ctk.CTkButton(
            bottom,
            text=f"Rename Selected ({len(mismatches)})",
            width=190,
            font=("", 12, "bold"),
            command=lambda: _on_rename(dialog),
        )
        rename_btn.pack(
            side="right", padx=(0, 6))

        ctk.CTkButton(
            bottom,
            text="Cancel",
            width=80,
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=dialog.destroy,
        ).pack(side="right", padx=(4, 6))

        def _on_rename(dlg):
            paths_to_rename = [
                path for path, checked_val
                in checked.items()
                if checked_val]
            if not paths_to_rename:
                return
            dlg.destroy()
            self._apply_fix_filenames(
                paths_to_rename, mismatches)

        # Initial population
        _rebuild_tree()

    def _apply_fix_filenames(
            self,
            paths: list,
            mismatches: list):
        """
        Applies the selected filename renames.
        Goes through _snapshot_original +
        _push_undo_snapshot + _dirty_paths so changes
        enter the review-before-commit workflow.
        """
        if not paths:
            return

        # Build lookup: path → expected_filename
        expected_map = {
            path: new_filename
            for path, _, new_filename in mismatches
        }

        self._push_undo_snapshot()
        changed = 0

        for path in paths:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            new_filename = expected_map.get(path)
            if not new_filename:
                continue
            if rec["filename"] == new_filename:
                continue

            self._snapshot_original(path)
            rec["filename"] = new_filename
            self._dirty_paths.add(path)
            self._update_tree_row(path, rec)
            changed += 1

        if changed:
            self._invalidate_unorg_cache()
            self._update_status_bar()
            self._update_unsaved_banner()
            self._set_sidebar_status(
                f"✔ {changed} filename(s) staged "
                f"for rename. Review & save to "
                f"apply to disk.",
                SUCCESS_GREEN)
            self._open_review_changes_dialog()


    # ------------------------------------------------------------------
    # Refresh file view
    # ------------------------------------------------------------------

    # Maximum frequency of progress bar updates during
    # refresh. Matches the scan throttle — 20 updates/sec.
    _REFRESH_PROGRESS_INTERVAL = 0.05  # seconds

    def _refresh_file_view(self):
        if not self.all_files_data or self.is_loading:
            return
        self.is_loading = True
        try:
            self.select_dir_btn.configure(state="disabled")
            self.add_dir_btn.configure(state="disabled")
        except Exception:
            pass
        self.dir_label.configure(
            text="Refreshing…",
            text_color=TEXT_WARNING)
        self.progress_bar.set(0)
        self.progress_bar.pack(
            side="right", padx=10, pady=10)

        paths_snapshot     = list(
            self.all_files_data.keys())
        root_dirs_snapshot = list(
            self.authorized_root_dirs)

        def _worker():
            # Filter to paths that still exist on disk.
            # Missing files are silently skipped —
            # they remain in all_files_data until the
            # user deletes them explicitly.
            existing = [
                p for p in paths_snapshot
                if os.path.exists(p)]

            if not existing:
                self.after(0, self._on_refresh_complete)
                return

            processed   = 0
            last_update = 0.0

            with ThreadPoolExecutor(
                    max_workers=self._SCAN_WORKERS
            ) as pool:
                futures = {
                    pool.submit(
                        self._parse_audio_file,
                        path,
                        root_dirs_snapshot): path
                    for path in existing
                }

                for future in as_completed(futures):
                    path = futures[future]
                    try:
                        fresh = future.result()
                        self.after(
                            0,
                            lambda p=path, f=fresh:
                            self._apply_refresh_record(
                                p, f))
                    except Exception as exc:
                        print(
                            f"[refresh] "
                            f"{os.path.basename(path)}"
                            f": {exc}")

                    processed += 1
                    now = time.monotonic()
                    if (processed == len(existing) or
                            now - last_update >=
                            self._REFRESH_PROGRESS_INTERVAL):
                        last_update = now
                        frac = processed / len(existing)
                        self.after(
                            0, lambda v=frac:
                            self.progress_bar.set(v))

            self.after(0, self._on_refresh_complete)

        threading.Thread(
            target=_worker, daemon=True).start()


    def _apply_refresh_record(self, path: str, fresh: dict):
        if path not in self.all_files_data:
            return
        if path not in self._dirty_paths:
            self.all_files_data[path].update({
                "bitrate":       fresh["bitrate"],
                "length":        fresh["length"],
                "date_modified": fresh["date_modified"],
                "title":         fresh["title"],
                "artist":        fresh["artist"],
                "album":         fresh["album"],
                "filename":      fresh["filename"],
                "extra_tags":    fresh["extra_tags"],
                "location":      fresh.get("location", ""),
            })
        else:
            self.all_files_data[path].update({
                "bitrate":       fresh["bitrate"],
                "length":        fresh["length"],
                "date_modified": fresh["date_modified"],
            })
        self._update_tree_row(path, self.all_files_data[path])


    def _on_refresh_complete(self):
        self.is_loading = False
        self.progress_bar.set(1.0)
        self.progress_bar.pack_forget()
        try:
            self.select_dir_btn.configure(state="normal")
            self.add_dir_btn.configure(state="normal")
        except Exception:
            pass
        self._invalidate_unorg_cache()
        self.distinct_artists = {
            rec["artist"]
            for rec in self.all_files_data.values()
            if rec["artist"] not in ("Unknown", "")
        }
        self._apply_search_filter()
        self._update_status_bar()
        self._restore_dir_label()


    # ------------------------------------------------------------------
    # O(1) tree row update
    # ------------------------------------------------------------------
    def _update_tree_row(self, path: str, rec: dict):
        values = self._record_to_row(rec)
        for tree in self.active_trees:
            try:
                if tree.exists(path):
                    tree.item(path, values=values)
                    current_tags = set(
                        tree.item(path, "tags"))
                    # Remove all dirty variants
                    current_tags.discard("dirty")
                    current_tags.discard("even_dirty")
                    current_tags.discard("odd_dirty")
                    if path in self._dirty_paths:
                        # Replace even/odd with
                        # combined dirty tag so
                        # Windows ttk renders the
                        # dirty colour correctly
                        if "even" in current_tags:
                            current_tags.discard("even")
                            current_tags.add(
                                "even_dirty")
                        elif "odd" in current_tags:
                            current_tags.discard("odd")
                            current_tags.add(
                                "odd_dirty")
                        else:
                            current_tags.add(
                                "even_dirty")
                    else:
                        # Path is clean — ensure a
                        # plain even or odd tag is
                        # present so the row always
                        # has a colour tag. Without
                        # this, rows that were dirty
                        # and are now reverted end up
                        # with no tag and invisible
                        # text on Windows until the
                        # row is selected.
                        if not any(
                                t in current_tags
                                for t in (
                                    "even", "odd")):
                            # Determine correct parity
                            # from the row's current
                            # position in the tree.
                            try:
                                all_iids = (
                                    tree.get_children(
                                        ""))
                                idx = list(
                                    all_iids).index(
                                        path)
                                current_tags.add(
                                    "even"
                                    if idx % 2 == 0
                                    else "odd")
                            except ValueError:
                                current_tags.add(
                                    "even")
                    tree.item(
                        path,
                        tags=tuple(current_tags))
            except Exception:
                pass

