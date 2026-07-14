# app/core_scanner.py
"""
ScannerMixin — handles security checks, root-path resolution,
and file scanning / directory loading using mutagen.
"""
import os
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import mutagen
import mutagen.mp3
from mutagen.id3 import TPE1, TIT2, TALB
import customtkinter as ctk

from app.constants import (
    AUDIO_EXTENSIONS, _STANDARD_TAG_PREFIXES, _IGNORED_TAG_KEYS,
    TEXT_WARNING, SUCCESS_GREEN,
    SAVE_BLUE, SAVE_BLUE_HOVER, DANGER_RED, DANGER_RED_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER, TEXT_ADAPTIVE,
)
from app.helpers import _get_tag_str, _truncate_path


class ScannerMixin:
    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    def security_check(self, target_filepath: str):
        if not self.authorized_root_dirs:
            raise PermissionError(
                "Security: no authorized root "
                "directory set.")
        target_abs = os.path.abspath(target_filepath)
        for root in self.authorized_root_dirs:
            auth_abs = os.path.abspath(root)
            try:
                common = os.path.commonpath(
                    [auth_abs, target_abs])
                if common == auth_abs:
                    return
            except ValueError:
                continue
        raise PermissionError(
            f"Security: outside all authorized "
            f"directories. Target: {target_abs}")

    def _find_root_for_path(
            self, file_path: str,
            root_dirs: list | None = None
    ) -> str | None:
        dirs = (
            root_dirs
            if root_dirs is not None
            else self.authorized_root_dirs)
        target_abs = os.path.abspath(file_path)
        for root in dirs:
            auth_abs = os.path.abspath(root)
            try:
                common = os.path.commonpath(
                    [auth_abs, target_abs])
                if common == auth_abs:
                    return root
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # Directory loading
    # ------------------------------------------------------------------
    def select_directory(self):
        if self.is_loading:
            return
        folder = ctk.filedialog.askdirectory(
            title="Select Music Library Directory")
        if not folder:
            return
        self.authorized_root_dirs = [
            os.path.abspath(folder)]
        self.is_loading = True
        self.select_dir_btn.configure(state="disabled")
        self.add_dir_btn.configure(state="disabled")
        self.dir_label.configure(
            text=(
                f"Loading: "
                f"{self.authorized_root_dirs[0]}…"),
            text_color=TEXT_WARNING)
        self.progress_bar.set(0)
        self.progress_bar.pack(
            side="right", padx=10, pady=10)

        self.all_files_data.clear()
        self.distinct_artists.clear()
        self._dirty_paths.clear()
        self._clear_original_values()
        self._proposed_changes.clear()
        self._scanned_unorganized.clear()
        self._unorg_check_vars.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._search_pinned_paths = None
        self._invalidate_unorg_cache()
        self._update_undo_redo_buttons()
        self._duplicate_results = None

        threading.Thread(
            target=self._load_files_thread,
            args=(self.authorized_root_dirs[0],),
            daemon=True,
        ).start()

    def add_directory(self):
        if self.is_loading:
            return
        folder = ctk.filedialog.askdirectory(
            title="Add Music Directory")
        if not folder:
            return
        new_root = os.path.abspath(folder)
        if new_root in self.authorized_root_dirs:
            self._show_info_dialog(
                "Already Loaded",
                f"'{os.path.basename(new_root)}' is "
                f"already in the library.")
            return

        if self._proposed_changes:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Add Directory")
            dialog.resizable(False, False)
            dialog.grab_set()
            self._center_dialog(dialog, 400, 175)

            ctk.CTkLabel(
                dialog,
                text=(
                    "Adding a directory will discard "
                    "your current\nin-progress "
                    "suggestions in the Unorganized "
                    "tab."),
                font=("", 13), wraplength=360,
            ).pack(pady=(24, 6), padx=20)
            ctk.CTkLabel(
                dialog,
                text="Do you want to continue?",
                text_color=TEXT_WARNING, font=("", 11),
            ).pack(pady=(0, 14), padx=20)

            btn_row = ctk.CTkFrame(
                dialog, fg_color="transparent")
            btn_row.pack()

            def _proceed():
                dialog.destroy()
                self._do_add_directory(new_root)

            ctk.CTkButton(
                btn_row, text="Continue", width=100,
                fg_color=SAVE_BLUE,
                hover_color=SAVE_BLUE_HOVER,
                command=_proceed,
            ).pack(side="left", padx=8)
            ctk.CTkButton(
                btn_row, text="Cancel", width=100,
                fg_color=CANCEL_BG,
                hover_color=CANCEL_BG_HOVER,
                text_color=TEXT_ADAPTIVE,
                command=dialog.destroy,
            ).pack(side="left", padx=8)
        else:
            self._do_add_directory(new_root)

    def _do_add_directory(self, new_root: str):
        self.authorized_root_dirs.append(new_root)
        self._duplicate_results = None
        self.is_loading = True
        self.select_dir_btn.configure(state="disabled")
        self.add_dir_btn.configure(state="disabled")
        self.dir_label.configure(
            text=f"Adding: {new_root}…",
            text_color=TEXT_WARNING)
        self.progress_bar.set(0)
        self.progress_bar.pack(
            side="right", padx=10, pady=10)

        threading.Thread(
            target=self._load_files_thread,
            args=(new_root,),
            daemon=True,
        ).start()

    # Maximum frequency of progress bar updates during
    # directory scan. Capped at 20 updates/sec to avoid
    # flooding the Tkinter event queue on large libraries.
    _SCAN_PROGRESS_INTERVAL = 0.05  # seconds

    # Number of worker threads for parallel file parsing.
    # I/O-bound work scales well with threads even under
    # the GIL. 8 workers is a good balance for both SSD
    # and HDD — more workers help SSDs, fewer help HDDs
    # by avoiding seek contention. Kept as a class
    # attribute so it can be tuned without changing logic.
    _SCAN_WORKERS = 8

    # ID3 frames needed for tag reading during scan.
    # Passed as known_frames to mutagen.mp3.MP3 so only
    # these frames are fully parsed. All other frames —
    # including APIC (cover art) — are stored as
    # BinaryFrame with the body skipped entirely.
    # APIC keys still appear in tags.keys() so cover
    # detection works without loading any image data.
    _MP3_KNOWN_FRAMES = {
        "TPE1": TPE1,   # Artist
        "TIT2": TIT2,   # Title
        "TALB": TALB,   # Album
    }

    def _load_files_thread(self, root_dir: str):
        # Collect all paths first, then filter to audio
        # files that pass the security check.
        all_paths = [
            os.path.join(root, f)
            for root, _, files in os.walk(root_dir)
            for f in files
        ]

        audio_paths = []
        for file_path in all_paths:
            if (os.path.splitext(
                    file_path)[1].lower()
                    not in AUDIO_EXTENSIONS):
                continue
            try:
                self.security_check(file_path)
            except PermissionError:
                continue
            audio_paths.append(file_path)

        total       = len(audio_paths)
        processed   = 0
        last_update = 0.0

        if total == 0:
            self.after(0, self._on_load_complete)
            return

        # Parse files in parallel. _parse_audio_file is
        # a pure function — each call is independent and
        # only returns a dict, so no locking is needed
        # for the parse step itself.
        # Results are collected via as_completed so the
        # progress bar advances as each file finishes
        # rather than waiting for the whole batch.
        with ThreadPoolExecutor(
                max_workers=self._SCAN_WORKERS) as pool:
            futures = {
                pool.submit(
                    self._parse_audio_file,
                    file_path): file_path
                for file_path in audio_paths
            }

            for future in as_completed(futures):
                try:
                    record = future.result()
                except Exception as exc:
                    print(
                        f"[scan] parse error "
                        f"{futures[future]}: {exc}")
                    processed += 1
                    continue

                # Merge result into shared state.
                # This runs on the scanner thread —
                # safe because is_loading is True and
                # the main thread does not mutate
                # all_files_data while loading.
                self.all_files_data[
                    record["path"]] = record
                if record["artist"] not in (
                        "Unknown", ""):
                    self.distinct_artists.add(
                        record["artist"])

                processed += 1

                # Throttle progress updates to at most
                # 20 per second regardless of library
                # size. Always post the final update so
                # the bar reaches 100%.
                now = time.monotonic()
                if (processed == total or
                        now - last_update >=
                        self._SCAN_PROGRESS_INTERVAL):
                    last_update = now
                    frac  = processed / total
                    label = (
                        f"Loading: "
                        f"{processed:,} / "
                        f"{total:,} files…")
                    self.after(
                        0, lambda v=frac, t=label:
                        self._update_scan_progress(
                            v, t))

        self.after(0, self._on_load_complete)

    def _update_scan_progress(
            self, frac: float, label: str):
        """
        Posts a progress update to the main thread.
        Called via after(0) from _load_files_thread.
        Updates both the progress bar and the dir label
        so the user sees a live file count.
        """
        self.progress_bar.set(frac)
        self.dir_label.configure(
            text=label,
            text_color=TEXT_WARNING)

    def _parse_audio_file(
            self, file_path: str,
            root_dirs: list | None = None) -> dict:
        artist, title, album = (
            "Unknown", "Unknown", "Unknown")
        bitrate, length = 0, 0.0
        extra_tags: list = []
        has_cover: bool  = False

        ext    = os.path.splitext(
            file_path)[1].lower()
        is_mp3 = ext == ".mp3"

        try:
            # --- Open file ----------------------------------------
            # MP3: use mutagen.mp3.MP3 with known_frames so
            # the ID3 parser fully parses only the tag frames
            # we need (TPE1, TIT2, TALB) and stores all other
            # frames — including APIC — as BinaryFrame with
            # the body skipped. audio.info is populated from
            # MPEG sync bytes independently of ID3, so bitrate
            # and length are still available. This is a single
            # file open with no APIC data loaded into memory.
            #
            # All other formats: use mutagen.File() as before.
            if is_mp3:
                try:
                    audio = mutagen.mp3.MP3(
                        file_path,
                        known_frames=self._MP3_KNOWN_FRAMES)
                except Exception:
                    # Some MP3s have non-standard headers
                    # that mutagen.mp3.MP3 cannot sync to.
                    # Fall back to mutagen.File() which is
                    # more tolerant. A fresh open is used
                    # to avoid any state left by the failed
                    # MP3 parse (important for network drives
                    # where file handles may linger).
                    try:
                        audio = mutagen.File(file_path)
                    except Exception:
                        audio = None
            else:
                audio = mutagen.File(file_path)

            if audio is not None:
                info = getattr(audio, "info", None)
                if info:
                    bitrate = (
                        getattr(
                            info, "bitrate", None)
                        or 0) // 1000
                    length  = (
                        getattr(
                            info, "length",  None)
                        or 0.0)
                if (hasattr(audio, "tags") and
                        audio.tags):
                    tags = audio.tags
                    keys = [
                        str(k).upper()
                        for k in tags.keys()]
                    extra_tags = [
                        k for k in keys
                        if not any(
                            k.startswith(p)
                            for p in
                            _STANDARD_TAG_PREFIXES)
                        and k not in
                        _IGNORED_TAG_KEYS
                    ]
                    artist = _get_tag_str(tags.get(
                        "artist",
                        tags.get(
                            "TPE1", ["Unknown"])))
                    title  = _get_tag_str(tags.get(
                        "title",
                        tags.get(
                            "TIT2", ["Unknown"])))
                    album  = _get_tag_str(tags.get(
                        "album",
                        tags.get(
                            "TALB", ["Unknown"])))

                    # WAV RIFF INFO chunk fallback
                    if artist == "Unknown":
                        artist = _get_tag_str(
                            tags.get(
                                "IART", ["Unknown"]))
                    if title == "Unknown":
                        title = _get_tag_str(
                            tags.get(
                                "INAM", ["Unknown"]))
                    if album == "Unknown":
                        album = _get_tag_str(
                            tags.get(
                                "IPRD", ["Unknown"]))

            # --- Cover art detection ----------------------------
            # MP3: APIC key is present in tags.keys() even
            # with known_frames — the frame ID was read from
            # the 10-byte header. The body (image data) was
            # never loaded. No .data access needed.
            #
            # Non-MP3: use the already-open audio object.
            # FLAC — .pictures attribute
            # M4A  — covr atom in tags
            # OGG  — metadata_block_picture in tags
            if is_mp3:
                if (audio is not None and
                        hasattr(audio, "tags") and
                        audio.tags):
                    has_cover = any(
                        str(k).startswith("APIC")
                        for k in audio.tags.keys())
            else:
                if audio is not None:
                    if hasattr(audio, "pictures"):
                        has_cover = bool(
                            audio.pictures)
                    if (not has_cover and
                            hasattr(audio, "tags") and
                            audio.tags and
                            "covr" in audio.tags):
                        has_cover = bool(
                            audio.tags["covr"])
                    if (not has_cover and
                            hasattr(audio, "tags") and
                            audio.tags):
                        mbp = audio.tags.get(
                            "metadata_block_picture",
                            [])
                        has_cover = bool(mbp)

        except Exception as exc:
            print(f"Error reading {file_path}: {exc}")

        root = (
            self._find_root_for_path(
                file_path,
                root_dirs=root_dirs) or "")
        rel_path = (
            os.path.relpath(file_path, root)
            if root
            else os.path.basename(file_path))
        date_mod = datetime.datetime.fromtimestamp(
            os.path.getmtime(file_path)
        ).strftime("%Y-%m-%d %H:%M")
        return {
            "path":          file_path,
            "rel_path":      rel_path,
            "filename":      os.path.basename(
                file_path),
            "artist":        artist,
            "title":         title,
            "album":         album,
            "bitrate":       bitrate,
            "length":        length,
            "date_modified": date_mod,
            "extra_tags":    extra_tags,
            "has_cover_art": has_cover,
            "location":      (
                _truncate_path(root)
                if root else ""),
        }

    def _on_load_complete(self):
        self.is_loading = False
        self.progress_bar.set(1.0)
        self.progress_bar.pack_forget()
        self.select_dir_btn.configure(state="normal")
        self.add_dir_btn.configure(state="normal")

        self._scanned_unorganized.clear()
        self._proposed_changes.clear()
        self._unorg_check_vars.clear()
        self._search_pinned_paths = None
        self._invalidate_unorg_cache()
        self._clear_sidebar()

        # Snapshot of load state — used by Discard All
        # to restore beyond the bounded undo stack.
        # Only the four user-editable fields are
        # snapshotted — consistent with _push_undo_snapshot.
        # Read-only fields (bitrate, length, path, etc.)
        # never change via user edits and do not need
        # to be included.
        self._load_snapshot = {
            path: {
                "filename": rec["filename"],
                "title":    rec["title"],
                "artist":   rec["artist"],
                "album":    rec["album"],
            }
            for path, rec in
            self.all_files_data.items()
        }

        roots = ", ".join(
            os.path.basename(r)
            for r in self.authorized_root_dirs)
        count = len(self.all_files_data)
        self.dir_label.configure(
            text=f"Loaded: {roots} ✔  ({count} files)",
            text_color=SUCCESS_GREEN)

        self.active_trees.clear()
        self._populate_all_files_tab()
        self._populate_unorganized_tab()
        self._populate_fuzzy_tab()
        self._apply_column_order()
        self._update_status_bar()

