# app/ui_cover_art_bulk.py
"""
BulkCoverArtDialog — modal window for editing cover art
across multiple audio files in a single session.

Opened from the All Files treeview right-click menu when
one or more rows are selected via "🎨 Edit Cover Art".

Features:
  - Navigates through each selected file with Prev/Next
  - Per-file progress label showing index and metadata
  - Prefetches search results for adjacent files
  - Identical search, thumbnail grid, browse, resize, and
    save logic as CoverArtDialog
  - Save & Next advances to the next file automatically
  - Skip skips without saving
  - Close button exits at any point
"""
import io
import os
import json
import threading
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import tkinter as tk

import customtkinter as ctk

from app.constants import (
    DANGER_RED, DANGER_RED_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER,
    SUCCESS_GREEN, WARNING_YELLOW,
    TEXT_MUTED, TEXT_ADAPTIVE,
    ACCENT_BLUE,
)

try:
    from PIL import Image as _PILImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILImage = None
    _PILLOW_AVAILABLE = False

# Dialog dimensions — identical to CoverArtDialog
_MAIN_IMG_SIZE = 400
_THUMB_SIZE    = 80
_RIGHT_W       = 220
_GRID_COLS     = 2

_UA = "SuperMusicTag/1.0 (music library manager)"


class BulkCoverArtDialog:
    """
    Bulk cover art editor — cycles through a list of files.

    Parameters
    ----------
    parent   : ctk.CTk — the main app window
    paths    : list    — ordered list of absolute file paths
    records  : dict    — reference to all_files_data
    on_save  : callable(path, image_bytes) — called after
               each successful disk write
    """

    def __init__(self, parent, paths: list,
                 records: dict, on_save):
        self._parent  = parent
        self._paths   = paths
        self._records = records
        self._on_save = on_save
        self._index   = 0

        # Cache: path → None (in flight) | [] (no results)
        #              | [result, ...]
        self._cache: dict = {}

        self._thumb_refs:   list = []
        self._thumb_frames: list = []
        self._selected_idx: int  = -1
        self._search_thread_id: int = 0

        self._staged_bytes:  bytes | None = None
        self._current_bytes: bytes | None = None

        self._build_window()
        self._load_file()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------
    def _build_window(self):
        self._win = ctk.CTkToplevel(self._parent)
        self._win.title("Edit Cover Art — Bulk")
        self._win.resizable(True, True)
        self._win.grab_set()

        # Center on parent
        self._win.update_idletasks()
        pw = self._parent.winfo_width()
        ph = self._parent.winfo_height()
        px = self._parent.winfo_x()
        py = self._parent.winfo_y()
        w  = _MAIN_IMG_SIZE + _RIGHT_W + 60
        h  = _MAIN_IMG_SIZE + 80
        x  = px + (pw - w) // 2
        y  = py + (ph - h) // 2
        self._win.geometry(f"{w}x{h}+{x}+{y}")
        self._win.minsize(
            _MAIN_IMG_SIZE + _RIGHT_W + 40, h)

        # ── Outer layout ───────────────────────────────
        # Row 0: navigation bar
        # Row 1: main content (image + right panel)
        # Row 2: bottom bar
        self._win.grid_columnconfigure(0, weight=1)
        self._win.grid_rowconfigure(0, weight=0)
        self._win.grid_rowconfigure(1, weight=1)
        self._win.grid_rowconfigure(2, weight=0)

        # ── Navigation bar (row 0) ─────────────────────
        nav = ctk.CTkFrame(
            self._win, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew",
                 padx=12, pady=(8, 0))
        nav.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            nav,
            text="← Previous",
            width=90,
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._go_previous)
        self._prev_btn.grid(
            row=0, column=0, padx=(0, 8))

        self._progress_lbl = ctk.CTkLabel(
            nav,
            text="",
            font=("", 12, "bold"),
            anchor="center")
        self._progress_lbl.grid(
            row=0, column=1, sticky="ew")

        self._next_btn = ctk.CTkButton(
            nav,
            text="Next →",
            width=90,
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._go_next)
        self._next_btn.grid(
            row=0, column=2, padx=(8, 0))

        # ── Middle row: image + right panel (row 1) ────
        mid = ctk.CTkFrame(
            self._win, fg_color="transparent")
        mid.grid(row=1, column=0, sticky="nsew",
                 padx=12, pady=4)
        mid.grid_columnconfigure(0, weight=0)
        mid.grid_columnconfigure(1, weight=1)
        mid.grid_rowconfigure(0, weight=1)

        # Left: image display
        img_frame = ctk.CTkFrame(
            mid, width=_MAIN_IMG_SIZE,
            height=_MAIN_IMG_SIZE,
            fg_color="gray20",
            corner_radius=6)
        img_frame.grid(
            row=0, column=0, sticky="nsew",
            padx=(0, 10))
        img_frame.grid_propagate(False)

        self._img_lbl = ctk.CTkLabel(
            img_frame,
            text="[No Cover Art]",
            width=_MAIN_IMG_SIZE,
            height=_MAIN_IMG_SIZE,
            fg_color="transparent",
            text_color=TEXT_MUTED,
            font=("", 14))
        self._img_lbl.place(x=0, y=0)

        # Right: controls + thumbnail grid
        right = ctk.CTkFrame(
            mid, width=_RIGHT_W,
            fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._search_btn = ctk.CTkButton(
            right,
            text="🔍  Search cover art",
            width=180, height=36,
            fg_color=ACCENT_BLUE,
            font=("", 12),
            command=self._on_search)
        self._search_btn.grid(
            row=0, column=0,
            sticky="w",
            pady=(16, 4), padx=8)

        self._search_status = ctk.CTkLabel(
            right, text="",
            text_color=TEXT_MUTED,
            font=("", 11),
            wraplength=200,
            justify="left",
            anchor="w")
        self._search_status.grid(
            row=1, column=0,
            sticky="ew",
            pady=(0, 4), padx=8)

        self._resize_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            right,
            text="Resize to 600×600px",
            variable=self._resize_var,
            font=("", 11),
        ).grid(row=2, column=0,
               sticky="w",
               pady=(0, 8), padx=8)

        self._grid_frame = ctk.CTkScrollableFrame(
            right,
            fg_color="gray15",
            corner_radius=6)
        self._grid_frame.grid(
            row=3, column=0,
            sticky="nsew",
            padx=8, pady=(0, 4))

        self._grid_frame.grid_columnconfigure(
            0, weight=1)
        self._grid_frame.grid_columnconfigure(
            1, weight=1)

        self._grid_placeholder = ctk.CTkLabel(
            self._grid_frame,
            text=(
                "Search or browse\n"
                "to add images"),
            text_color=TEXT_MUTED,
            font=("", 11))
        self._grid_placeholder.grid(
            row=0, column=0,
            columnspan=2,
            padx=8, pady=20)

        # ── Bottom bar (row 2) ─────────────────────────
        bottom = ctk.CTkFrame(
            self._win, fg_color="transparent")
        bottom.grid(
            row=2, column=0, sticky="ew",
            padx=12, pady=(0, 12))
        bottom.grid_columnconfigure(
            0, weight=0,
            minsize=_MAIN_IMG_SIZE + 10)
        bottom.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bottom,
            text="📁  Browse…",
            width=90, height=28,
            font=("", 11),
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_ADAPTIVE,
            command=self._on_browse,
        ).grid(row=0, column=0,
               sticky="w",
               padx=(0, 8))

        btn_right = ctk.CTkFrame(
            bottom, fg_color="transparent")
        btn_right.grid(
            row=0, column=1, sticky="ew")
        btn_right.grid_columnconfigure(0, weight=1)
        btn_right.grid_columnconfigure(1, weight=1)
        btn_right.grid_columnconfigure(2, weight=1)

        self._save_btn = ctk.CTkButton(
            btn_right,
            text="💾  Save & Next",
            height=28,
            font=("", 11, "bold"),
            state="disabled",
            command=self._on_save_clicked)
        self._save_btn.grid(
            row=0, column=0,
            sticky="ew",
            padx=(0, 4))

        self._skip_btn = ctk.CTkButton(
            btn_right,
            text="Skip",
            height=28,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=self._on_skip)
        self._skip_btn.grid(
            row=0, column=1,
            sticky="ew",
            padx=(4, 4))

        ctk.CTkButton(
            btn_right,
            text="✕  Close",
            height=28,
            fg_color=DANGER_RED,
            hover_color=DANGER_RED_HOVER,
            command=self._win.destroy,
        ).grid(row=0, column=2,
               sticky="ew",
               padx=(4, 0))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _update_nav_state(self):
        path   = self._paths[self._index]
        rec    = self._records.get(path, {})
        artist = rec.get("artist", "Unknown")
        title  = rec.get("title",  "Unknown")
        total  = len(self._paths)

        self._progress_lbl.configure(
            text=(
                f"File {self._index + 1} of {total}"
                f"  —  {artist}  —  {title}"))

        self._prev_btn.configure(
            state=(
                "disabled"
                if self._index == 0
                else "normal"))
        self._next_btn.configure(
            state=(
                "disabled"
                if self._index >= total - 1
                else "normal"))

        is_last = (self._index >= total - 1)
        self._save_btn.configure(
            text=(
                "💾  Save & Close"
                if is_last
                else "💾  Save & Next"))
        self._skip_btn.configure(
            text="Skip & Close" if is_last else "Skip")
        self._win.title(
            f"Cover Art  |  "
            f"{artist}  —  {title}  "
            f"({self._index + 1} of {total})")

    def _go_previous(self):
        if self._index == 0:
            return
        self._index -= 1
        self._load_file()

    def _go_next(self):
        if self._index >= len(self._paths) - 1:
            return
        self._index += 1
        self._load_file()

    def _advance_or_close(self):
        if self._index >= len(self._paths) - 1:
            self._win.destroy()
        else:
            self._go_next()

    # ------------------------------------------------------------------
    # Per-file load
    # ------------------------------------------------------------------
    def _load_file(self):
        self._update_nav_state()

        self._staged_bytes  = None
        self._current_bytes = None
        self._save_btn.configure(state="disabled")
        self._set_cover_text("[Loading…]")

        current_path = self._paths[self._index]

        # Load current embedded cover art
        self._load_current_cover(current_path)

        # Clear previous file's thumbnails immediately
        # regardless of cache state so stale results
        # from the previous file never remain visible
        # while the new file's results are loading.
        self._clear_strip()

        # Populate from cache or fetch
        cached = self._cache.get(current_path,
                                  "MISSING")
        if cached == "MISSING":
            # Not in cache at all — start fetch
            self._cache[current_path] = None
            self._search_status.configure(
                text="⏳ Searching…",
                text_color=TEXT_MUTED)
            threading.Thread(
                target=self._fetch_for_path,
                args=(current_path,),
                daemon=True).start()
        elif cached is None:
            # Fetch in flight (from prefetch)
            self._search_status.configure(
                text="⏳ Searching…",
                text_color=TEXT_MUTED)
        else:
            # Results ready
            self._display_cached_results(
                current_path)

        # Prefetch adjacent files
        for delta in (-1, 1):
            adj = self._index + delta
            if 0 <= adj < len(self._paths):
                adj_path = self._paths[adj]
                if adj_path not in self._cache:
                    self._prefetch(adj_path)

    # ------------------------------------------------------------------
    # Current cover load
    # ------------------------------------------------------------------
    def _load_current_cover(self, path: str):
        from app.helpers import _extract_cover_art_bytes
        if not _PILLOW_AVAILABLE:
            return

        def _worker():
            raw = _extract_cover_art_bytes(path)
            # Only deliver if still on this file
            if (self._index < len(self._paths) and
                    self._paths[self._index] == path):
                self._win.after(
                    0, lambda: self._set_main_image(
                        raw, stage=False))

        threading.Thread(
            target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Cache and fetch
    # ------------------------------------------------------------------
    def _build_queries(self, path: str) -> list:
        rec    = self._records.get(path, {})
        artist = rec.get("artist", "Unknown")
        title  = rec.get("title",  "Unknown")
        album  = rec.get("album",  "Unknown")

        queries: list = []
        if artist != "Unknown" and title != "Unknown":
            queries.append(
                (artist, title, "artist+title"))
        if artist != "Unknown" and album != "Unknown":
            queries.append(
                (artist, album, "artist+album"))
        if title != "Unknown":
            queries.append(
                (None, title, "title only"))
        filename_stem = os.path.splitext(
            rec.get("filename", ""))[0].strip()
        if filename_stem:
            queries.append(
                (None, filename_stem, "filename"))
        return queries

    def _fetch_for_path(self, path: str):
        queries = self._build_queries(path)
        if not queries:
            self._cache[path] = []
            self._win.after(
                0,
                lambda p=path:
                self._on_fetch_complete(p))
            return

        for query in queries:
            *_, label = query
            itunes_results = []
            deezer_results = []

            t1 = threading.Thread(
                target=lambda q=query:
                itunes_results.extend(
                    self._search_itunes(q)),
                daemon=True)
            t2 = threading.Thread(
                target=lambda q=query:
                deezer_results.extend(
                    self._search_deezer(q)),
                daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            seen_urls: set = set()
            results:   list = []
            for item in (
                    itunes_results + deezer_results):
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)

            if results:
                self._cache[path] = results
                self._win.after(
                    0,
                    lambda p=path:
                    self._on_fetch_complete(p))
                return

        self._cache[path] = []
        self._win.after(
            0,
            lambda p=path:
            self._on_fetch_complete(p))

    def _on_fetch_complete(self, path: str):
        if path != self._paths[self._index]:
            return  # for a non-active file, cache is populated
        self._display_cached_results(path)

    def _display_cached_results(self, path: str):
        results = self._cache.get(path) or []

        if not results:
            self._search_status.configure(
                text="No results found.",
                text_color=WARNING_YELLOW)
            self._populate_strip([], [])
            return

        self._search_status.configure(
            text=f"✔ {len(results)} result(s)",
            text_color=SUCCESS_GREEN)
        self._clear_strip()

        self._search_thread_id += 1
        my_id = self._search_thread_id

        def _download_all():
            thumb_data: list = [None] * len(results)
            threads = []

            def _fetch(idx, item):
                try:
                    req = Request(
                        item["url"],
                        headers={"User-Agent": _UA})
                    with urlopen(
                            req, timeout=8) as r:
                        thumb_data[idx] = r.read()
                except Exception as exc:
                    print(
                        f"[bulk thumb] ✗ "
                        f"{item['label']}: {exc}")

            for idx, item in enumerate(results):
                t = threading.Thread(
                    target=_fetch,
                    args=(idx, item),
                    daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join(timeout=10)

            if my_id == self._search_thread_id:
                self._win.after(
                    0, lambda:
                    self._populate_strip(
                        results, thumb_data))

        threading.Thread(
            target=_download_all,
            daemon=True).start()

    def _prefetch(self, path: str):
        if path in self._cache:
            return
        self._cache[path] = None
        threading.Thread(
            target=self._fetch_for_path,
            args=(path,),
            daemon=True).start()

    # ------------------------------------------------------------------
    # Search (manual re-fetch, bypasses cache)
    # ------------------------------------------------------------------
    def _on_search(self):
        current_path = self._paths[self._index]
        # Force fresh fetch by removing from cache
        self._cache.pop(current_path, None)
        self._cache[current_path] = None

        self._search_status.configure(
            text="⏳ Searching…",
            text_color=TEXT_MUTED)
        self._clear_strip()

        threading.Thread(
            target=self._fetch_for_path,
            args=(current_path,),
            daemon=True).start()

    # ------------------------------------------------------------------
    # iTunes / Deezer search (identical to CoverArtDialog)
    # ------------------------------------------------------------------
    def _search_itunes(self, primary) -> list:
        artist_q, term_q, kind = primary
        query = (
            f"{artist_q} {term_q}"
            if artist_q else term_q)
        try:
            params = urlencode({
                "term":   query,
                "entity": "album",
                "limit":  "10",
                "media":  "music",
            })
            url = (
                f"https://itunes.apple.com/search"
                f"?{params}")
            req = Request(
                url, headers={"User-Agent": _UA})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(
                    resp.read().decode("utf-8"))

            results = []
            for item in data.get("results", []):
                art_url = item.get(
                    "artworkUrl100", "")
                if not art_url:
                    continue
                art_url = art_url.replace(
                    "100x100bb", "600x600bb")
                label = (
                    f"{item.get('artistName', '')} — "
                    f"{item.get('collectionName', '')}")
                results.append({
                    "url":    art_url,
                    "label":  label,
                    "source": "iTunes",
                })
            return results
        except Exception as exc:
            print(f"[bulk iTunes] ✗ {exc}")
            return []

    def _search_deezer(self, primary) -> list:
        artist_q, term_q, kind = primary
        query = (
            f"{artist_q} {term_q}"
            if artist_q else term_q)
        try:
            params = urlencode({
                "q":     query,
                "limit": "10",
            })
            url = (
                f"https://api.deezer.com/search/album"
                f"?{params}")
            req = Request(
                url, headers={"User-Agent": _UA})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(
                    resp.read().decode("utf-8"))

            results = []
            for item in data.get("data", []):
                art_url = item.get(
                    "cover_big",
                    item.get("cover_medium", ""))
                if not art_url:
                    continue
                artist_name = item.get(
                    "artist", {}).get("name", "")
                album_title = item.get("title", "")
                results.append({
                    "url":    art_url,
                    "label":  (
                        f"{artist_name} — "
                        f"{album_title}"),
                    "source": "Deezer",
                })
            return results
        except Exception as exc:
            print(f"[bulk Deezer] ✗ {exc}")
            return []

    # ------------------------------------------------------------------
    # Thumbnail strip (identical to CoverArtDialog)
    # ------------------------------------------------------------------
    def _clear_strip(self):
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self._thumb_frames.clear()
        self._selected_idx = -1
        self._grid_placeholder = ctk.CTkLabel(
            self._grid_frame,
            text="Searching…",
            text_color=TEXT_MUTED,
            font=("", 11))
        self._grid_placeholder.grid(
            row=0, column=0,
            columnspan=2,
            padx=8, pady=20)

    def _populate_strip(self, results: list,
                         thumb_data: list):
        if not _PILLOW_AVAILABLE:
            return

        if self._current_bytes is not None:
            results    = [
                {"url":    "__current__",
                 "label":  "Current",
                 "source": "Current"}
            ] + list(results)
            thumb_data = (
                [self._current_bytes]
                + list(thumb_data))

        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self._thumb_frames.clear()
        self._selected_idx = -1

        for idx, (item, raw) in enumerate(
                zip(results, thumb_data)):

            row = idx // _GRID_COLS
            col = idx  % _GRID_COLS

            frame = ctk.CTkFrame(
                self._grid_frame,
                fg_color="gray25",
                corner_radius=4,
                cursor="hand2")
            frame.grid(
                row=row, column=col,
                padx=4, pady=4,
                sticky="nsew")
            self._thumb_frames.append(frame)

            if raw and _PILLOW_AVAILABLE:
                try:
                    img = _PILImage.open(
                        io.BytesIO(raw)
                    ).convert("RGB")
                    img = img.resize(
                        (_THUMB_SIZE, _THUMB_SIZE),
                        _PILImage.LANCZOS)
                    from PIL import ImageTk
                    tk_img = ImageTk.PhotoImage(img)
                    self._thumb_refs.append(tk_img)
                    lbl = tk.Label(
                        frame,
                        image=tk_img,
                        bg="#404040",
                        cursor="hand2")
                    lbl.pack()
                except Exception:
                    lbl = tk.Label(
                        frame,
                        text="?",
                        bg="#404040",
                        fg="white",
                        width=_THUMB_SIZE,
                        height=_THUMB_SIZE,
                        cursor="hand2")
                    lbl.pack()
                    self._thumb_refs.append(None)
            else:
                lbl = tk.Label(
                    frame,
                    text="✗",
                    bg="#404040",
                    fg="#666",
                    width=_THUMB_SIZE,
                    height=_THUMB_SIZE,
                    cursor="hand2")
                lbl.pack()
                self._thumb_refs.append(None)

            badge_colour = {
                "Current": "#2E7D32",
                "iTunes":  "#1565C0",
                "Deezer":  "#6A1B9A",
            }.get(item["source"], "#555555")

            tk.Label(
                frame,
                text=item["source"],
                bg=badge_colour,
                fg="white",
                font=("", 7),
                padx=2,
            ).pack(fill="x")

            _raw = raw
            _idx = idx
            for w in (frame, lbl):
                w.bind(
                    "<Button-1>",
                    lambda e,
                    r=_raw, i=_idx:
                    self._on_thumb_click(r, i))

    def _on_thumb_click(self, raw: bytes | None,
                         idx: int):
        for frame in self._thumb_frames:
            frame.configure(fg_color="gray25")
        if idx < len(self._thumb_frames):
            self._thumb_frames[idx].configure(
                fg_color=ACCENT_BLUE)
        self._selected_idx = idx
        if raw:
            self._set_main_image(raw, stage=True)

    def _get_blank_cover_image(self):
        if not hasattr(self, "_blank_cover_image"):
            self._blank_cover_image = None
        if self._blank_cover_image is None:
            if _PILLOW_AVAILABLE:
                blank = _PILImage.new(
                    "RGBA", (1, 1), (0, 0, 0, 0))
                self._blank_cover_image = ctk.CTkImage(
                    light_image=blank,
                    dark_image=blank,
                    size=(1, 1))
        return self._blank_cover_image

    def _set_cover_text(self, text: str):
        blank = self._get_blank_cover_image()
        try:
            if blank is not None:
                self._img_lbl.configure(
                    image=blank, text=text)
            else:
                self._img_lbl.configure(
                    image=None, text=text)
        except Exception:
            try:
                self._img_lbl.configure(text=text)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Main image display
    # ------------------------------------------------------------------
    def _set_main_image(self, image_bytes: bytes | None,
                         stage: bool = True):
        if not _PILLOW_AVAILABLE:
            return

        if image_bytes is None:
            self._set_cover_text("[No Cover Art]")
            if stage:
                self._staged_bytes = None
                self._save_btn.configure(
                    state="disabled")
            return

        try:
            img = _PILImage.open(
                io.BytesIO(image_bytes)
            ).convert("RGB")
            img = img.resize(
                (_MAIN_IMG_SIZE, _MAIN_IMG_SIZE),
                _PILImage.LANCZOS)
            ctk_img = ctk.CTkImage(
                light_image=img,
                dark_image=img,
                size=(_MAIN_IMG_SIZE, _MAIN_IMG_SIZE))
            self._img_lbl.configure(
                image=ctk_img, text="")
            self._img_lbl._cover_ref = ctk_img

            if stage:
                self._staged_bytes = image_bytes
                self._save_btn.configure(
                    state="normal")
            else:
                self._current_bytes = image_bytes
        except Exception as exc:
            print(f"[bulk cover art] display error: {exc}")

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------
    def _on_browse(self):
        path = ctk.filedialog.askopenfilename(
            parent=self._win,
            title="Select Cover Art Image",
            filetypes=[
                ("Image files",
                 "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All files", "*.*"),
            ])
        if not path:
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
            for frame in self._thumb_frames:
                frame.configure(fg_color="gray25")
            self._selected_idx = -1
            self._set_main_image(raw, stage=True)
        except Exception as exc:
            print(f"[bulk browse] {exc}")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _on_save_clicked(self):
        if not self._staged_bytes:
            return

        image_bytes = self._staged_bytes

        if self._resize_var.get() and _PILLOW_AVAILABLE:
            try:
                img = _PILImage.open(
                    io.BytesIO(image_bytes)
                ).convert("RGB")
                img = img.resize(
                    (600, 600), _PILImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG",
                         quality=85)
                image_bytes = buf.getvalue()
            except Exception as exc:
                print(
                    f"[bulk cover art] "
                    f"resize failed: {exc}")

        current_path = self._paths[self._index]
        self._save_btn.configure(
            state="disabled", text="Saving…")

        def _worker():
            from app.helpers import _write_cover_art
            err = _write_cover_art(
                current_path, image_bytes)
            self._win.after(
                0, lambda:
                self._on_save_done_bulk(
                    image_bytes, err))

        threading.Thread(
            target=_worker, daemon=True).start()

    def _on_save_done_bulk(self,
                            image_bytes: bytes,
                            err: str | None):
        if err:
            self._search_status.configure(
                text=f"⚠ Save failed: {err}",
                text_color=DANGER_RED)
            # Restore correct save button label
            is_last = (
                self._index >= len(self._paths) - 1)
            self._save_btn.configure(
                state="normal",
                text=(
                    "💾  Save & Close"
                    if is_last
                    else "💾  Save & Next"))
            return

        current_path = self._paths[self._index]
        self._on_save(current_path, image_bytes)
        self._advance_or_close()

    # ------------------------------------------------------------------
    # Skip
    # ------------------------------------------------------------------
    def _on_skip(self):
        self._advance_or_close()
