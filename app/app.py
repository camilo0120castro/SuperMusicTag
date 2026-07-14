# app/app.py
"""
SuperMusicTagApp — assembles all mixins, owns all state, handles
construction, the unsaved-changes banner, tab system, CSV export,
and the disk-commit logic.

Mixins inherited:
  SidebarMixin             — sidebar display and metadata editing
  AllFilesMixin            — All Files treeview core
  AllFilesEditMixin        — All Files inline filename editor +
                              right-click revert menu
  AllFilesActionsMixin     — All Files deletion + duplicate detection
  UnorganizedMixin         — Unorganized treeview core
  UnorganizedEditMixin     — Unorganized inline edit + right-click +
                              edit-suggestions dialog
  UnorganizedActionsMixin  — Unorganized analyze/organize/save +
                              Gemini API
  FuzzyMixin               — Fuzzy Matches analysis and cards
  StateMixin               — undo/redo, snapshots, cache
  ScannerMixin             — file scanning, security, mutagen
  ToolbarMixin             — top toolbar widgets
  ConfigMixin              — configuration overlay
  SmartTabMixin            — Smart Instructions tab
  DialogsMixin             — all modal popup dialogs
"""
import os
import csv
import datetime
import threading
import tkinter as tk
import customtkinter as ctk

from app.constants import (
    COL_IDS,
    TAB_BAR_BG, WARNING_BG, WARNING_YELLOW,
    DANGER_RED, DANGER_RED_HOVER,
    SAVE_BLUE, SAVE_BLUE_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_DISABLED, TEXT_MUTED, TEXT_ADAPTIVE,
    SUCCESS_GREEN,
)
from app.config import _load_config
from app.helpers import _format_length, _truncate_path

from app.ui_sidebar import SidebarMixin
from app.ui_all_files import AllFilesMixin
from app.ui_all_files_edit import AllFilesEditMixin
from app.ui_all_files_actions import AllFilesActionsMixin
from app.ui_unorganized import UnorganizedMixin
from app.ui_unorganized_edit import UnorganizedEditMixin
from app.ui_unorganized_actions import UnorganizedActionsMixin
from app.ui_fuzzy import FuzzyMixin
from app.core_state import StateMixin
from app.core_scanner import ScannerMixin
from app.ui_toolbar import ToolbarMixin
from app.ui_config import ConfigMixin
from app.ui_smart import SmartTabMixin
from app.ui_dialogs import DialogsMixin


class SuperMusicTagApp(
        SidebarMixin,
        AllFilesMixin, AllFilesEditMixin, AllFilesActionsMixin,
        UnorganizedMixin, UnorganizedEditMixin,
        UnorganizedActionsMixin,
        FuzzyMixin,
        StateMixin, ScannerMixin,
        ToolbarMixin, ConfigMixin,
        SmartTabMixin, DialogsMixin,
        ctk.CTk):

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.title("SuperMusicTag")
        self.geometry("1200x800")
        self.minsize(900, 600)
        self.authorized_root_dirs: list[str]  = []
        self.all_files_data: dict             = {}
        self.distinct_artists: set            = set()
        self.is_loading: bool                 = False
        self.active_trees: list               = []
        self._proposed_changes: dict          = {}
        self._scanned_unorganized: dict       = {}
        self._dirty_paths: set                = set()
        self._original_values: dict           = {}
        self._sidebar_active_path: str | None = None
        self._sidebar_selected_paths: list    = []
        self._sidebar_context: str            = "all_files"
        self._all_files_sidebar_active_path: str | None = None
        self._all_files_sidebar_selected_paths: list = []
        self._unorg_sidebar_active_path: str | None = None
        self._unorg_sidebar_selected_paths: list = []
        self._config_origin_tab: str = "All Files"

        self._unorg_check_vars: dict    = {}
        self._staged_from_unorg: dict   = {}

        self._undo_stack: list = []
        self._redo_stack: list = []
        self._load_snapshot: dict | None = None

        self._duplicate_results: dict | None         = None
        self._duplicate_window:  ctk.CTkToplevel | None = None

        self._fuzzy_thread_running: bool = False
        self._fuzzy_rerun_pending:  bool = False
        self._fuzzy_stale:          bool = False
        self._fuzzy_generation:     int  = 0

        self._unorg_cache: dict | None = None
        self._unorg_cache_key: tuple   = ()

        self._field_combos: dict = {}
        self._cover_load_generation: int = 0
        self._search_detached: set = set()

        self._search_pinned_paths:  set | None = None
        self._search_pinned_origin: str        = ""
        self._select_debounce_id: str | None = None
        self._blank_cover_image: ctk.CTkImage | None = None

        cfg = _load_config()
        self.naming_convention_var = ctk.StringVar(
            value=cfg.get(
                "naming_convention", "Artist - Title"))
        self.fuzzy_threshold_var = ctk.DoubleVar(
            value=cfg.get("fuzzy_threshold", 85.0))
        self.fuzzy_show_collaboration_var = ctk.BooleanVar(
            value=cfg.get("fuzzy_show_collaboration", True))
        self.organize_strategy_var = ctk.StringVar(
            value=cfg.get(
                "organize_strategy", "gemini"))
        self.gemini_logging_var = ctk.BooleanVar(
            value=cfg.get("gemini_logging", False))
        self.gemini_search_title_var = ctk.BooleanVar(
            value=cfg.get("gemini_search_title", True))
        self.gemini_search_artist_var = ctk.BooleanVar(
            value=cfg.get("gemini_search_artist", True))
        self.gemini_search_album_var = ctk.BooleanVar(
            value=cfg.get("gemini_search_album", True))
        self.unorg_check_artist_var = ctk.BooleanVar(
            value=cfg.get("unorg_check_artist", True))
        self.unorg_check_title_var = ctk.BooleanVar(
            value=cfg.get("unorg_check_title", True))
        self.unorg_check_album_var = ctk.BooleanVar(
            value=cfg.get("unorg_check_album", True))
        self.unorg_check_filename_var = ctk.BooleanVar(
            value=cfg.get("unorg_check_filename", True))
        self.unorg_check_cover_art_var = ctk.BooleanVar(
            value=cfg.get("unorg_check_cover_art", False))
        self.gemini_prompt_var = ctk.StringVar(
            value=cfg.get(
                "gemini_prompt", ""))
        self.table_theme_var = ctk.StringVar(
            value=cfg.get(
                "table_theme", "dark"))

        # Load saved replacements, falling back to
        # defaults for any missing keys
        from app.constants import FILENAME_REPLACEMENTS_DEFAULT
        _saved_replacements = cfg.get(
            "filename_replacements", {})
        self.filename_replacements_vars: dict = {}
        for char, default_val in \
                FILENAME_REPLACEMENTS_DEFAULT.items():
            self.filename_replacements_vars[char] = \
                ctk.StringVar(
                    value=_saved_replacements.get(
                        char, default_val))

        saved_order = cfg.get(
            "column_order", list(COL_IDS))
        if "location" not in saved_order:
            saved_order.append("location")
        self._saved_column_order = saved_order

        self._saved_naming_convention: str = \
            self.naming_convention_var.get()
        self._saved_fuzzy_threshold: float = \
            self.fuzzy_threshold_var.get()
        cfg_ignore = cfg.get("fuzzy_ignore_pairs", [])
        self._fuzzy_ignore_pairs: set = set(cfg_ignore)

        self._setup_treeview_style()
        self._build_layout()
        self._apply_table_theme()

        # Warn before closing if pending changes exist
        self.protocol(
            "WM_DELETE_WINDOW",
            self._on_close_requested)

        # Global keyboard shortcuts
        self.bind("<Control-s>",
                  lambda e: self._commit_dirty_paths())
        self.bind("<Control-z>",
                  self._on_global_undo)
        self.bind("<Control-y>",
                  lambda e: self._on_redo())
        self.bind("<Control-Z>",
                  lambda e: self._on_redo())

        if not os.environ.get("GEMINI_API_KEY"):
            print("Warning: GEMINI_API_KEY not set.")

    # ------------------------------------------------------------------
    # Unsaved-changes banner
    # ------------------------------------------------------------------
    def _update_unsaved_banner(self):
        # Self-healing: clean up any falsely marked dirty paths
        # (e.g. from inline edits that didn't change the actual string)
        to_clean = set()
        for p in self._dirty_paths:
            rec = self.all_files_data.get(p)
            orig = self._original_values.get(p)
            if not rec or not orig:
                continue
            is_dirty = False
            for key in ("title", "artist", "album", "filename"):
                if rec.get(key) != orig.get(key):
                    is_dirty = True
                    break
            if not is_dirty:
                to_clean.add(p)

        for p in to_clean:
            self._dirty_paths.discard(p)
            self._original_values.pop(p, None)
            rec = self.all_files_data.get(p)
            if rec:
                self._update_tree_row(p, rec)

        count = len(self._dirty_paths)
        if count == 0:
            self.unsaved_banner.grid_remove()
        else:
            self.unsaved_banner_lbl.configure(
                text=(
                    f"⚠  {count} file(s) have pending "
                    f"changes (tags and/or filenames) "
                    f"— not yet written to disk."))
            self.unsaved_banner.grid()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self._build_toolbar()
        self._build_unsaved_banner()
        self._build_sidebar()
        self._build_main_area()

    # ------------------------------------------------------------------
    # Unsaved banner — single "Review & Save Changes"
    # button replaces the old separate Review / Save pair.
    # ------------------------------------------------------------------
    def _build_unsaved_banner(self):
        self.unsaved_banner = ctk.CTkFrame(
            self, fg_color=WARNING_BG,
            corner_radius=0, height=32)
        self.unsaved_banner.grid(
            row=1, column=0, columnspan=2,
            sticky="ew")
        self.unsaved_banner.grid_propagate(False)

        self.unsaved_banner_lbl = ctk.CTkLabel(
            self.unsaved_banner, text="",
            text_color=WARNING_YELLOW, font=("", 11))
        self.unsaved_banner_lbl.pack(
            side="left", padx=12, pady=6)

        ctk.CTkButton(
            self.unsaved_banner,
            text="Discard All",
            width=90, height=22,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            font=("", 11),
            command=self._discard_all_changes,
        ).pack(side="right", padx=(0, 8), pady=5)

        ctk.CTkButton(
            self.unsaved_banner,
            text="Review & Save Changes",
            width=160, height=22, font=("", 11),
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=self._review_changes,
        ).pack(side="right", padx=(0, 16), pady=5)

        self.unsaved_banner.grid_remove()

    # ------------------------------------------------------------------
    # _commit_dirty_paths — opens the unified review dialog.
    # Ctrl+S also lands here.
    # ------------------------------------------------------------------
    def _commit_dirty_paths(self):
        if not self._dirty_paths:
            return
        self._open_review_changes_dialog()

    # ------------------------------------------------------------------
    # Execute commit — locks UI and starts the write thread.
    # ------------------------------------------------------------------
    def _execute_commit(self):
        if not self._dirty_paths:
            return

        paths_to_write = list(self._dirty_paths)

        # Lock UI for the duration of the commit so the
        # user cannot trigger a directory load, undo, or
        # redo while files are being written to disk.
        # Safe because the worker thread only mutates
        # all_files_data record fields and _dirty_paths —
        # no other code path touches those while locked.
        self.is_loading = True
        self.select_dir_btn.configure(state="disabled")
        self.add_dir_btn.configure(state="disabled")
        self.undo_btn.configure(state="disabled")
        self.redo_btn.configure(state="disabled")

        self.progress_bar.set(0)
        self.progress_bar.pack(
            side="right", padx=10, pady=10)

        threading.Thread(
            target=self._commit_worker,
            args=(paths_to_write,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Commit worker — runs on a background thread.
    # No UI access. Posts progress and completion back
    # to the main thread via after(0, ...).
    # ------------------------------------------------------------------
    def _commit_worker(self, paths_to_write: list):
        import mutagen
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total        = len(paths_to_write)
        saved        = 0
        failed       = 0
        tag_failed   = 0
        renamed_pairs:    list = []
        tag_only_written: list = []

        # ── Tag Writing Task ──────────────────────────────────────────
        def _write_tags(path, title, artist, album):
            try:
                self.security_check(path)
                ext = os.path.splitext(path)[1].lower()
                if ext == ".mp3":
                    from mutagen.id3 import (
                        ID3, TIT2, TPE1, TALB,
                        ID3NoHeaderError)
                    try:
                        tags = ID3(path)
                    except ID3NoHeaderError:
                        tags = ID3()
                    tags["TIT2"] = TIT2(encoding=3, text=title)
                    tags["TPE1"] = TPE1(encoding=3, text=artist)
                    tags["TALB"] = TALB(encoding=3, text=album)
                    tags.save(path, v2_version=3)
                else:
                    audio = mutagen.File(path, easy=True)
                    if audio is not None:
                        audio["title"]  = [title]
                        audio["artist"] = [artist]
                        audio["album"]  = [album]
                        audio.save()
                return None
            except Exception as exc:
                return str(exc)

        # ── Submit Tag Writing in Parallel ───────────────────────────
        tasks = []
        for path in paths_to_write:
            rec = self.all_files_data.get(path)
            if not rec:
                continue
            tasks.append((
                path,
                rec.get("title", ""),
                rec.get("artist", ""),
                rec.get("album", "")
            ))

        tag_errors = {}
        max_workers = min(8, len(tasks)) if tasks else 1

        if tasks:
            total_tasks = len(tasks)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_write_tags, path, title, artist, album): path
                    for path, title, artist, album in tasks
                }
                for completed_count, future in enumerate(as_completed(futures), start=1):
                    path = futures[future]
                    try:
                        tag_errors[path] = future.result()
                    except Exception as e:
                        tag_errors[path] = str(e)
                    
                    # Update progress bar (up to 70% of total progress)
                    frac = (completed_count / total_tasks) * 0.7
                    self.after(0, lambda v=frac: self.progress_bar.set(v))

        # ── Sequential Renames and Metadata updates ──────────────────
        for i, path in enumerate(paths_to_write, start=1):
            original_path = path
            rec = self.all_files_data.get(path)
            if not rec:
                failed += 1
                frac = 0.7 + (i / total) * 0.3
                self.after(0, lambda v=frac: self.progress_bar.set(v))
                continue

            tag_error = tag_errors.get(path)
            if tag_error:
                print(f"[commit] tag write failed for {os.path.basename(path)}: {tag_error}")

            try:
                if tag_error and "permission" in tag_error.lower():
                    raise PermissionError(tag_error)

                # --- Rename if filename changed ---
                was_renamed  = False
                new_filename = rec["filename"]
                if new_filename != os.path.basename(path):
                    new_path = os.path.join(
                        os.path.dirname(path),
                        new_filename)
                    self.security_check(new_path)
                    base, ext = os.path.splitext(new_path)
                    counter = 1
                    while (os.path.exists(new_path)
                           and new_path.lower() != path.lower()):
                        new_path = f"{base} ({counter}){ext}"
                        counter += 1
                    os.rename(path, new_path)
                    root = self._find_root_for_path(new_path) or ""
                    rec["filename"] = os.path.basename(new_path)
                    rec["path"]     = new_path
                    rec["rel_path"] = (
                        os.path.relpath(new_path, root)
                        if root
                        else os.path.basename(new_path))
                    rec["location"] = _truncate_path(root) if root else ""
                    
                    del self.all_files_data[path]
                    self.all_files_data[new_path] = rec
                    self._dirty_paths.discard(path)
                    self._original_values.pop(path, None)
                    renamed_pairs.append((original_path, new_path))
                    was_renamed = True
                    path = new_path

                # --- Clear dirty state ---
                self._dirty_paths.discard(path)
                self._original_values.pop(path, None)

                try:
                    rec["date_modified"] = (
                        datetime.datetime
                        .fromtimestamp(os.path.getmtime(path))
                        .strftime("%Y-%m-%d %H:%M"))
                except Exception:
                    pass

                if tag_error:
                    tag_failed += 1
                else:
                    saved += 1

                if not was_renamed:
                    tag_only_written.append(original_path)

            except PermissionError as exc:
                print(f"[commit] security: {exc}")
                failed += 1
            except Exception as exc:
                print(f"[commit] {os.path.basename(path)}: {exc}")
                failed += 1

            frac = 0.7 + (i / total) * 0.3
            self.after(0, lambda v=frac: self.progress_bar.set(v))

        # All files processed — hand results back to
        # the main thread for UI updates.
        results = {
            "saved":          saved,
            "failed":         failed,
            "tag_failed":     tag_failed,
            "renamed_pairs":  renamed_pairs,
            "tag_only_written": tag_only_written,
        }
        self.after(
            0, lambda:
            self._on_commit_complete(results))

    # ------------------------------------------------------------------
    # Commit complete — runs on the main thread via after(0).
    # Unlocks UI, updates all views, shows summary.
    # ------------------------------------------------------------------
    def _on_commit_complete(self, results: dict):
        saved        = results["saved"]
        failed       = results["failed"]
        tag_failed   = results["tag_failed"]
        renamed_pairs     = results["renamed_pairs"]
        tag_only_written  = results["tag_only_written"]

        self.progress_bar.pack_forget()
        self.progress_bar.set(0)

        # Unlock UI — restore undo/redo to their correct
        # enabled/disabled state via
        # _update_undo_redo_buttons rather than
        # unconditionally re-enabling them.
        self.is_loading = False
        self.select_dir_btn.configure(state="normal")
        self.add_dir_btn.configure(state="normal")
        self._update_undo_redo_buttons()

        self._update_unsaved_banner()
        self._update_status_bar()
        self._invalidate_duplicate_results()

        # Targeted UI update — no full rebuild
        self._apply_commit_ui_updates(
            renamed_pairs, tag_only_written)
        self._set_load_snapshot_from_current()

        msg = f"✔ {saved} file(s) written to disk."
        if tag_failed:
            msg += (
                f"  ⚠ {tag_failed} file(s) renamed"
                f" but tags could not be written "
                f"(unsupported format).")
        if failed:
            msg += f"  ⚠ {failed} could not be saved."
        self._set_sidebar_status(
            msg,
            SUCCESS_GREEN if not failed
            else WARNING_YELLOW)

    def _apply_commit_ui_updates(
            self,
            renamed_pairs: list,
            tag_only_written: list):
        """
        Update the All Files treeview after a commit
        without triggering a full rebuild.
        Renamed files: delete the old iid and insert a
        new row at the same position with the new iid.
        Tag-only changes: O(1) value update via
        _update_tree_row.
        Detached files (hidden by search filter):
        delete the old iid from the treeview's internal
        state, insert the new iid in a detached state,
        and update _search_detached so _apply_search_filter
        can reattach it correctly when the filter clears.
        """
        if not hasattr(self, "_all_files_tree") or \
                not self._all_files_tree.winfo_exists():
            return

        tree = self._all_files_tree

        # Clean up old paths of renames from Unorganized tab cache and treeview
        for old_path, _ in renamed_pairs:
            self._scanned_unorganized.pop(old_path, None)
            self._proposed_changes.pop(old_path, None)
            self._unorg_check_vars.pop(old_path, None)
            if (hasattr(self, "unorg_tree") and
                    self.unorg_tree.exists(old_path)):
                try:
                    self.unorg_tree.delete(old_path)
                except Exception:
                    pass

        # --- Handle renames ---
        for old_path, new_path in renamed_pairs:
            rec = self.all_files_data.get(new_path)
            if not rec:
                continue

            if tree.exists(old_path):
                # Item is visible in the treeview.
                # Record its position and tags, then
                # delete and reinsert under the new iid.
                parent   = tree.parent(old_path)
                index    = tree.index(old_path)
                old_tags = set(
                    tree.item(old_path, "tags"))
                old_tags.discard("dirty")
                old_tags.discard("even_dirty")
                old_tags.discard("odd_dirty")
                # Restore plain even/odd tag
                if not any(
                        t in old_tags
                        for t in ("even", "odd")):
                    old_tags.add("even")
                tree.delete(old_path)
                tree.insert(
                    parent, index,
                    iid=new_path,
                    values=self._record_to_row(rec),
                    tags=tuple(old_tags))

            elif old_path in self._search_detached:
                # Item was hidden by the search filter.
                # ttk.Treeview keeps detached items in
                # its internal model under the old iid.
                # Capture the old tags first, then delete
                # the old iid, insert the new one carrying
                # the same even/odd tag, then immediately
                # detach it so it stays hidden.
                # _apply_search_filter will reattach it
                # when appropriate.
                try:
                    old_tags = set(
                        tree.item(old_path, "tags"))
                    old_tags.discard("dirty")
                    old_tags.discard("even_dirty")
                    old_tags.discard("odd_dirty")
                    if not any(
                            t in old_tags
                            for t in ("even", "odd")):
                        old_tags.add("even")
                    tree.delete(old_path)
                except Exception:
                    old_tags = {"even"}
                self._search_detached.discard(old_path)
                self._search_detached.add(new_path)
                try:
                    tree.insert(
                        "", "end",
                        iid=new_path,
                        values=self._record_to_row(rec),
                        tags=tuple(old_tags))
                    tree.detach(new_path)
                except Exception:
                    pass

        # --- Handle tag-only changes ---
        for path in tag_only_written:
            rec = self.all_files_data.get(path)
            if rec:
                self._update_tree_row(path, rec)

        self._apply_search_filter()

        # Re-synchronize the Unorganized tab tracking and UI for all affected paths
        affected_paths = [new_path for _, new_path in renamed_pairs] + tag_only_written
        if affected_paths and hasattr(self, "_sync_unorganized_after_record_changes"):
            self._sync_unorganized_after_record_changes(affected_paths)

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------
    def _export_csv(self):
        if not self.all_files_data:
            self._show_info_dialog(
                "Nothing to Export",
                "Load a directory before exporting.")
            return
        path = ctk.filedialog.asksaveasfilename(
            title="Export library as CSV",
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")])
        if not path:
            return
        fieldnames = [
            "modified", "filename", "title", "artist",
            "album", "bitrate", "length",
            "date_modified", "location", "path"]
        try:
            with open(path, "w", newline="",
                      encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=fieldnames)
                writer.writeheader()
                for rec_path, rec in \
                        self.all_files_data.items():
                    writer.writerow({
                        "modified": (
                            "yes"
                            if rec_path in
                            self._dirty_paths
                            else "no"),
                        "filename":
                            rec.get("filename",  ""),
                        "title":
                            rec.get("title",     ""),
                        "artist":
                            rec.get("artist",    ""),
                        "album":
                            rec.get("album",     ""),
                        "bitrate":
                            f"{rec.get('bitrate', 0)}"
                            f" kbps",
                        "length":
                            _format_length(
                                rec.get("length", 0)),
                        "date_modified":
                            rec.get(
                                "date_modified", ""),
                        "location":
                            rec.get("location",  ""),
                        "path": rec_path,
                    })
            self.dir_label.configure(
                text=(
                    f"✔ Exported "
                    f"{len(self.all_files_data)}"
                    f" rows → "
                    f"{os.path.basename(path)}"),
                text_color=SUCCESS_GREEN)
            self.after(4000, self._restore_dir_label)
        except Exception as exc:
            self._show_info_dialog(
                "Export Failed", str(exc))

    def _restore_dir_label(self):
        if self.authorized_root_dirs:
            roots = ", ".join(
                os.path.basename(r)
                for r in self.authorized_root_dirs)
            count = len(self.all_files_data)
            self.dir_label.configure(
                text=(
                    f"Loaded: {roots} ✔  "
                    f"({count} files)"),
                text_color=SUCCESS_GREEN)
        else:
            self.dir_label.configure(
                text="No directory selected.",
                text_color=TEXT_SECONDARY)

    # ------------------------------------------------------------------
    # Main area / tab system
    # ------------------------------------------------------------------
    def _build_main_area(self):
        tab_bar = ctk.CTkFrame(
            self, corner_radius=0,
            fg_color=TAB_BAR_BG)
        tab_bar.grid(
            row=2, column=0, columnspan=2,
            sticky="ew")

        self._tab_content = ctk.CTkFrame(
            self, corner_radius=0,
            fg_color="transparent")
        self._tab_content.grid(
            row=3, column=1, sticky="nsew")
        self._tab_content.grid_columnconfigure(
            0, weight=1)
        self._tab_content.grid_rowconfigure(
            0, weight=1)

        self.tab_all_files   = ctk.CTkFrame(
            self._tab_content, corner_radius=0,
            fg_color="transparent")
        self.tab_unorganized = ctk.CTkFrame(
            self._tab_content, corner_radius=0,
            fg_color="transparent")
        self.tab_fuzzy       = ctk.CTkFrame(
            self._tab_content, corner_radius=0,
            fg_color="transparent")
        # self.tab_smart = ctk.CTkFrame(
        #     self._tab_content, corner_radius=0,
        #     fg_color="transparent")
        # disabled — Smart Instructions tab not yet implemented

        for frame in (
                self.tab_all_files,
                self.tab_unorganized,
                self.tab_fuzzy,
                # self.tab_smart,  # disabled — not yet implemented
                ):
            frame.grid(row=0, column=0, sticky="nsew")

        tab_specs = [
            ("All Files",          self.tab_all_files),
            ("Unorganized",        self.tab_unorganized),
            ("Fuzzy Matches",      self.tab_fuzzy),
            # ("Smart Instructions", self.tab_smart),  # disabled — not yet implemented
        ]
        self._tab_buttons: dict = {}
        self._tab_frames:  dict = {}

        btn_centre = ctk.CTkFrame(
            tab_bar, fg_color="transparent")
        btn_centre.pack(expand=True)

        for label, frame in tab_specs:
            self._tab_frames[label] = frame
            btn = ctk.CTkButton(
                btn_centre, text=label,
                width=160, height=34,
                corner_radius=4,
                fg_color="transparent",
                text_color=TEXT_DISABLED,
                font=("", 12),
                command=lambda lbl=label:
                self._switch_tab(lbl))
            btn.pack(side="left", padx=4, pady=5)
            self._tab_buttons[label] = btn

        # Arrow-key navigation between tabs
        tab_labels = [label for label, _ in tab_specs]
        for i, label in enumerate(tab_labels):
            btn       = self._tab_buttons[label]
            prev_lbl  = tab_labels[(i - 1) % len(tab_labels)]
            next_lbl  = tab_labels[(i + 1) % len(tab_labels)]
            btn.bind(
                "<Left>",
                lambda e, lbl=prev_lbl: (
                    self._switch_tab(lbl),
                    self._tab_buttons[lbl].focus_set()))
            btn.bind(
                "<Right>",
                lambda e, lbl=next_lbl: (
                    self._switch_tab(lbl),
                    self._tab_buttons[lbl].focus_set()))

        self._active_tab: str = ""
        self._switch_tab("All Files")

        ctk.CTkLabel(
            self.tab_all_files,
            text="Load a directory to populate.",
            text_color=TEXT_SECONDARY,
        ).pack(pady=20)
        ctk.CTkLabel(
            self.tab_unorganized,
            text="Unorganized files will appear here.",
            text_color=TEXT_SECONDARY,
        ).pack(pady=20)

        # NOTE: _setup_fuzzy_tab() must run before any
        # call to _populate_fuzzy_tab() because it
        # creates self.fuzzy_scroll.
        self._setup_fuzzy_tab()
        # self._setup_smart_tab()  # disabled — not yet implemented
        self._build_config_overlay()

    def _switch_tab(self, label: str,
                     clear_sidebar: bool = True):
        if label not in self._tab_frames:
            return
        self._tab_frames[label].tkraise()
        self._active_tab = label
        if label == "Fuzzy Matches" and self._fuzzy_stale:
            if hasattr(self, "fuzzy_loading_lbl"):
                self.fuzzy_loading_lbl.configure(
                    text="⚠ Changes made. Please refresh the view.",
                    text_color=WARNING_YELLOW)
        if label == "Unorganized":
            if hasattr(self, "_update_unorg_strategy_label"):
                self._update_unorg_strategy_label()
        if clear_sidebar:
            self._restore_or_clear_sidebar(label)
        default_blue = ["#3B8ED0", "#1F6AA5"]
        for lbl, btn in self._tab_buttons.items():
            if lbl == label:
                btn.configure(
                    fg_color=default_blue,
                    text_color=TEXT_PRIMARY)
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=TEXT_DISABLED)

    def _restore_or_clear_sidebar(self, label: str):
        """
        Called by _switch_tab instead of _clear_sidebar.
        Restores the sidebar from the last active path
        when switching back to All Files or Unorganized,
        so the user does not lose their context.
        Falls back to _clear_sidebar if no valid path
        is remembered or the tab has no selection state.
        Fuzzy Matches always clears — no row selection.
        """
        # ── All Files ─────────────────────────────────
        if label == "All Files":
            if self._restore_all_files_tab_context():
                return
            self._clear_sidebar()
            return

        # ── Unorganized ──────────────────────────────
        if label == "Unorganized":
            if self._restore_unorganized_tab_context():
                return
            self._clear_sidebar()
            return

        # ── Fuzzy Matches and any other tab ───────────
        # No row-level selection — always clear.
        self._clear_sidebar()

    def _restore_all_files_tab_context(self) -> bool:
        if not (hasattr(self, "_all_files_tree") and
                self._all_files_tree.winfo_exists()):
            return False
        tree = self._all_files_tree
        valid_paths = [
            path for path in self._all_files_sidebar_selected_paths
            if path in self.all_files_data and tree.exists(path)]
        active_path = self._all_files_sidebar_active_path
        if (not valid_paths and active_path and
                active_path in self.all_files_data and
                tree.exists(active_path)):
            valid_paths = [active_path]
        if not valid_paths:
            return False
        tree.selection_set(valid_paths)
        focus_path = (
            active_path
            if active_path in valid_paths
            else valid_paths[0])
        tree.focus(focus_path)
        try:
            tree.see(focus_path)
        except Exception:
            pass
        self._on_all_files_selection_changed(
            tree, self.all_files_data)
        return True

    def _restore_unorganized_tab_context(self) -> bool:
        if not (hasattr(self, "unorg_tree") and
                self.unorg_tree.winfo_exists()):
            return False
        valid_paths = [
            path for path in self._unorg_sidebar_selected_paths
            if path in self._scanned_unorganized and
            self.unorg_tree.exists(path)]
        active_path = self._unorg_sidebar_active_path
        if (not valid_paths and active_path and
                active_path in self._scanned_unorganized and
                self.unorg_tree.exists(active_path)):
            valid_paths = [active_path]
        if not valid_paths:
            return False
        self.unorg_tree.selection_set(valid_paths)
        focus_path = (
            active_path
            if active_path in valid_paths
            else valid_paths[0])
        self.unorg_tree.focus(focus_path)
        try:
            self.unorg_tree.see(focus_path)
        except Exception:
            pass
        self._sync_unorg_sidebar_from_tree_selection()
        self._update_unorg_checked_actions()
        return True

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clear_tab(tab_frame):
        for w in tab_frame.winfo_children():
            w.destroy()

    def _on_global_undo(self, event=None):
        """
        Global Ctrl+Z handler. Fires the record-level
        undo only when focus is NOT in a text entry or
        text widget — those handle their own native
        Ctrl+Z (undo last typed character) and should
        not be intercepted.
        """
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, tk.Text)):
            return
        self._on_undo()

    def _on_close_requested(self):
        """
        Called when the user tries to close the window.
        If there are pending changes or staged proposals,
        warn the user before closing.
        """
        has_dirty    = bool(self._dirty_paths)
        has_proposed = bool(self._proposed_changes)

        if not has_dirty and not has_proposed:
            self.destroy()
            return

        parts = []
        if has_dirty:
            parts.append(
                f"{len(self._dirty_paths)} "
                f"unsaved change(s)")
        if has_proposed:
            parts.append(
                f"{len(self._proposed_changes)} "
                f"pending suggestion(s)")
        detail = " and ".join(parts)

        dialog = ctk.CTkToplevel(self)
        dialog.title("Unsaved Changes")
        dialog.resizable(False, False)
        dialog.grab_set()
        self._center_dialog(dialog, 420, 180)

        ctk.CTkLabel(
            dialog,
            text="You have unsaved changes.",
            font=("", 14, "bold"),
        ).pack(pady=(20, 6), padx=20)
        ctk.CTkLabel(
            dialog,
            text=(
                f"You have {detail}. "
                f"If you close now, these will "
                f"be lost."),
            font=("", 11),
            text_color=TEXT_MUTED,
            wraplength=380, justify="left",
        ).pack(pady=(0, 16), padx=20)

        btn_row = ctk.CTkFrame(
            dialog, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row,
            text="Close anyway",
            width=120,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=lambda: (
                dialog.destroy(), self.destroy()),
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color=SAVE_BLUE,
            hover_color=SAVE_BLUE_HOVER,
            command=dialog.destroy,
        ).pack(side="left", padx=8)

