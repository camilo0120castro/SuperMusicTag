# app/ui_cover_art.py
"""
CoverArtDialog — modal window for viewing, searching, and
replacing the cover art of a single audio file.

Opened by double-clicking the cover art label in the sidebar.

Features:
  - Displays current embedded cover art at 400×400px
  - Searches iTunes and Deezer simultaneously for matching
    artwork using artist + title (primary), artist + album
    (secondary), or title only (last resort)
  - Results shown as thumbnails in a scrollable horizontal
    strip with source badges (iTunes / Deezer)
  - Browse Files button loads a local image file
  - Resize option (default on) resizes to 600×600 JPEG
    before embedding
  - Save writes directly to disk, format-aware
    (MP3 / FLAC / M4A / OGG)
  - Updates has_cover_art in all_files_data and refreshes
    the sidebar cover display on save
"""
import io
import os
import json
import threading
import tkinter as tk
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError

import customtkinter as ctk

from app.constants import (
    SAVE_BLUE, SAVE_BLUE_HOVER,
    DANGER_RED, DANGER_RED_HOVER,
    CANCEL_BG, CANCEL_BG_HOVER,
    SUCCESS_GREEN, WARNING_YELLOW,
    TEXT_MUTED, TEXT_ADAPTIVE, TEXT_PRIMARY,
    ACCENT_BLUE,
)

try:
    from PIL import Image as _PILImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILImage = None
    _PILLOW_AVAILABLE = False

# Dialog dimensions
_MAIN_IMG_SIZE  = 400   # px — main image display
_THUMB_SIZE     = 80    # px — thumbnail size in grid
_RIGHT_W        = 220   # px — right panel width
_GRID_COLS      = 2     # columns in thumbnail grid

# User-Agent header for web requests — some APIs reject
# requests with no User-Agent
_UA = "SuperMusicTag/1.0 (music library manager)"


class CoverArtDialog:
    """
    Modal cover art editor dialog.

    Parameters
    ----------
    parent      : ctk.CTk — the main app window
    path        : str — absolute path to the audio file
    rec         : dict — the all_files_data record for path
    on_save     : callable(path, image_bytes) — called after
                  successful disk write so the caller can
                  update its own state
    """

    def __init__(self, parent, path: str,
                 rec: dict, on_save):
        self._parent   = parent
        self._path     = path
        self._rec      = rec
        self._on_save  = on_save

        # Currently displayed image bytes (None = placeholder)
        self._current_bytes: bytes | None = None
        # Bytes staged for saving (set when user picks
        # a thumbnail or browses a file)
        self._staged_bytes:  bytes | None = None

        self._thumb_refs:  list = []   # keep CTkImage refs alive
        self._thumb_frames: list = []  # thumbnail frame widgets
        self._selected_idx: int  = -1  # selected thumbnail index

        self._search_thread_id: int = 0  # cancel stale results

        self._build_window()
        self._load_current_cover()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------
    def _build_window(self):
        artist = self._rec.get("artist", "Unknown")
        title  = self._rec.get("title",  "Unknown")

        self._win = ctk.CTkToplevel(self._parent)
        self._win.title(
            f"Cover Art | {artist} - {title}")
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
        # Row 0: title label
        # Row 1: main content (image + right panel)
        self._win.grid_columnconfigure(0, weight=1)
        self._win.grid_rowconfigure(0, weight=0)
        self._win.grid_rowconfigure(1, weight=1)
        self._win.grid_rowconfigure(2, weight=0)

        # ── Title label ────────────────────────────────
        ctk.CTkLabel(
            self._win,
            text=f"{artist}  —  {title}",
            font=("", 13, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew",
               padx=16, pady=(12, 4))

        # ── Middle row: image + right panel ────────────
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

        # Search button
        ctk.CTkButton(
            right,
            text="🔍  Search cover art",
            width=180, height=36,
            fg_color=ACCENT_BLUE,
            font=("", 12),
            command=self._on_search,
        ).grid(row=0, column=0,
               sticky="w",
               pady=(16, 4), padx=8)

        # Search status label
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

        # Resize checkbox
        self._resize_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            right,
            text="Resize to 600×600px",
            variable=self._resize_var,
            font=("", 11),
        ).grid(row=2, column=0,
               sticky="w",
               pady=(0, 8), padx=8)

        # ── Thumbnail grid ─────────────────────────────
        # CTkScrollableFrame handles vertical scrolling
        # natively — no manual canvas/scrollbar needed.
        self._grid_frame = ctk.CTkScrollableFrame(
            right,
            fg_color="gray15",
            corner_radius=6)
        self._grid_frame.grid(
            row=3, column=0,
            sticky="nsew",
            padx=8, pady=(0, 4))

        # Two equal-width columns
        self._grid_frame.grid_columnconfigure(
            0, weight=1)
        self._grid_frame.grid_columnconfigure(
            1, weight=1)

        # Placeholder shown before any search
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

        # ── Bottom bar — window level row 2 ───────────
        # Split at the image/panel boundary:
        #   column 0 — fixed width = _MAIN_IMG_SIZE
        #              contains Browse button
        #   column 1 — fills remainder (right panel)
        #              contains Save + Cancel evenly
        bottom = ctk.CTkFrame(
            self._win, fg_color="transparent")
        bottom.grid(
            row=2, column=0, sticky="ew",
            padx=12, pady=(0, 12))

        # Column 0 fixed at image width + padding
        # to align Browse with image boundary.
        # Column 1 fills the right panel area.
        bottom.grid_columnconfigure(
            0, weight=0,
            minsize=_MAIN_IMG_SIZE + 10)
        bottom.grid_columnconfigure(
            1, weight=1)

        # Browse button — left side, below image
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

        # Right side frame — Save + Cancel evenly spread
        btn_right = ctk.CTkFrame(
            bottom, fg_color="transparent")
        btn_right.grid(
            row=0, column=1,
            sticky="ew")
        btn_right.grid_columnconfigure(
            0, weight=1)
        btn_right.grid_columnconfigure(
            1, weight=1)

        # Save button — default CTk color
        self._save_btn = ctk.CTkButton(
            btn_right,
            text="💾  Save",
            height=28,
            font=("", 11, "bold"),
            state="disabled",
            command=self._on_save_clicked,
        )
        self._save_btn.grid(
            row=0, column=0,
            sticky="ew",
            padx=(0, 4))

        # Cancel button
        ctk.CTkButton(
            btn_right,
            text="Cancel",
            height=28,
            fg_color=CANCEL_BG,
            hover_color=CANCEL_BG_HOVER,
            text_color=TEXT_ADAPTIVE,
            command=self._win.destroy,
        ).grid(row=0, column=1,
               sticky="ew",
               padx=(4, 0))

    # ------------------------------------------------------------------
    # Load current cover art into main display
    # ------------------------------------------------------------------
    def _load_current_cover(self):
        from app.helpers import _extract_cover_art_bytes
        if not _PILLOW_AVAILABLE:
            return

        def _worker():
            raw = _extract_cover_art_bytes(self._path)
            self._win.after(
                0, lambda: self._set_main_image(
                    raw, stage=False))

        threading.Thread(
            target=_worker, daemon=True).start()

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
        """
        Display image_bytes in the main 600×600 label.
        If stage=True, also set _staged_bytes and enable
        the Save button.
        If stage=False, only update the display (used for
        loading the current cover on open).
        """
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
            # Keep reference alive
            self._img_lbl._cover_ref = ctk_img

            if stage:
                self._staged_bytes = image_bytes
                self._save_btn.configure(
                    state="normal")
            else:
                self._current_bytes = image_bytes
        except Exception as exc:
            print(f"[cover art] display error: {exc}")

    # ------------------------------------------------------------------
    # Search Web
    # ------------------------------------------------------------------
    def _on_search(self):
        artist = self._rec.get("artist", "Unknown")
        title  = self._rec.get("title",  "Unknown")
        album  = self._rec.get("album",  "Unknown")

        # Build fallback chain — try each variant in
        # order, stop as soon as results are found.
        # Priority:
        #   1. artist + title  (most specific)
        #   2. artist + album  (if title fails)
        #   3. title only      (last resort)
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

        # Filename stem as last resort — always present
        # and often contains artist + title information
        # even when tags are missing or wrong.
        filename_stem = os.path.splitext(
            self._rec.get("filename", ""))[0].strip()
        if filename_stem:
            queries.append(
                (None, filename_stem, "filename"))

        if not queries:
            self._search_status.configure(
                text=(
                    "⚠ No metadata available "
                    "to search with."),
                text_color=WARNING_YELLOW)
            return

        print(
            f"[cover art search] "
            f"{len(queries)} fallback variant(s) "
            f"available:")
        for a, t, label in queries:
            if a:
                print(f"  {label}: {a!r} + {t!r}")
            else:
                print(f"  {label}: {t!r}")

        self._search_status.configure(
            text="⏳ Searching…",
            text_color=TEXT_MUTED)
        self._clear_strip()

        self._search_thread_id += 1
        my_id = self._search_thread_id

        def _worker():
            for query in queries:
                *_, label = query
                print(
                    f"[cover art search] "
                    f"trying: {label}")

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

                # Deduplicate by URL
                seen_urls: set = set()
                results:   list = []
                for item in (
                        itunes_results +
                        deezer_results):
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        results.append(item)

                if results:
                    print(
                        f"[cover art search] "
                        f"✔ {len(results)} result(s) "
                        f"from {label} — "
                        f"stopping fallback chain")
                    self._win.after(
                        0,
                        lambda r=results, gid=my_id:
                        self._on_search_done(
                            r, gid))
                    return

                print(
                    f"[cover art search] "
                    f"✗ no results for {label} "
                    f"— trying next variant")

            # All variants exhausted
            print(
                "[cover art search] "
                "✗ all variants exhausted")
            self._win.after(
                0,
                lambda gid=my_id:
                self._on_search_done([], gid))

        threading.Thread(
            target=_worker, daemon=True).start()

    def _search_itunes(self, primary) -> list:
        """
        Query the iTunes Search API.
        Returns list of dicts:
          {url, label, source}
        """
        artist_q, term_q, kind = primary
        if artist_q:
            query = f"{artist_q} {term_q}"
        else:
            query = term_q

        print(
            f"[iTunes] searching: "
            f"query={query!r} kind={kind}")

        try:
            params = urlencode({
                "term":    query,
                "entity":  "album",
                "limit":   "10",
                "media":   "music",
            })
            url = (
                f"https://itunes.apple.com/search"
                f"?{params}")
            req  = Request(
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
                # Upgrade to 600×600
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

            print(
                f"[iTunes] ✔ {len(results)} result(s)"
                f" for {query!r}")
            return results

        except Exception as exc:
            print(f"[iTunes] ✗ {exc}")
            return []

    def _search_deezer(self, primary) -> list:
        """
        Query the Deezer API.
        Returns list of dicts:
          {url, label, source}
        """
        artist_q, term_q, kind = primary
        if artist_q:
            query = f"{artist_q} {term_q}"
        else:
            query = term_q

        print(
            f"[Deezer] searching: "
            f"query={query!r} kind={kind}")

        try:
            params = urlencode({
                "q":     query,
                "limit": "10",
            })
            url = (
                f"https://api.deezer.com/search/album"
                f"?{params}")
            req  = Request(
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
                label = (
                    f"{artist_name} — {album_title}")
                results.append({
                    "url":    art_url,
                    "label":  label,
                    "source": "Deezer",
                })

            print(
                f"[Deezer] ✔ {len(results)} result(s)"
                f" for {query!r}")
            return results

        except Exception as exc:
            print(f"[Deezer] ✗ {exc}")
            return []

    def _on_search_done(self, results: list,
                         thread_id: int):
        # Discard results from a superseded search
        if thread_id != self._search_thread_id:
            return

        if not results:
            self._search_status.configure(
                text="No results found.",
                text_color=WARNING_YELLOW)
            # Clear "Searching…" and show current
            # cover if available, or a no-results
            # message if not.
            for w in self._grid_frame.winfo_children():
                w.destroy()
            if self._current_bytes is not None:
                # Show current cover as sole thumbnail
                self._populate_strip([], [])
            else:
                ctk.CTkLabel(
                    self._grid_frame,
                    text=(
                        "No results found.\n"
                        "Try Browse to add\n"
                        "an image manually."),
                    text_color=TEXT_MUTED,
                    font=("", 11),
                    justify="center",
                ).grid(
                    row=0, column=0,
                    columnspan=2,
                    padx=8, pady=20)
            return

        self._search_status.configure(
            text=f"✔ {len(results)} result(s)",
            text_color=SUCCESS_GREEN)
        self._clear_strip()

        # Download thumbnails in parallel
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
                    print(
                        f"[thumb] ✔ "
                        f"[{item['source']}] "
                        f"{item['label']}")
                except Exception as exc:
                    print(
                        f"[thumb] ✗ "
                        f"[{item['source']}] "
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

            self._win.after(
                0, lambda:
                self._populate_strip(
                    results, thumb_data))

        threading.Thread(
            target=_download_all,
            daemon=True).start()

    # ------------------------------------------------------------------
    # Preview strip
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

        # Prepend current cover art if available.
        # _current_bytes is set by _set_main_image
        # (stage=False) when the dialog opens.
        # Both this method and _set_main_image run
        # on the main thread via after(0, ...) so
        # there is no race condition — if
        # _current_bytes is None here it simply
        # means the file has no cover art.
        if self._current_bytes is not None:
            results   = [
                {"url":    "__current__",
                 "label":  "Current",
                 "source": "Current"}
            ] + list(results)
            thumb_data = (
                [self._current_bytes]
                + list(thumb_data))

        # Clear placeholder
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

            # Source badge — green for current,
            # blue for iTunes, purple for Deezer
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

            # Bind click on both frame and label
            _raw = raw
            _idx = idx
            for w in (frame, lbl):
                w.bind(
                    "<Button-1>",
                    lambda e,
                    r=_raw, i=_idx:
                    self._on_thumb_click(r, i))

        print(
            f"[cover art] grid populated: "
            f"{len(results)} thumbnail(s) "
            f"({_GRID_COLS} columns)")

    def _on_thumb_click(self, raw: bytes | None,
                         idx: int):
        # Highlight selected thumbnail.
        # CTkFrame uses fg_color not bg/relief.
        for frame in self._thumb_frames:
            frame.configure(fg_color="gray25")
        if idx < len(self._thumb_frames):
            self._thumb_frames[idx].configure(
                fg_color=ACCENT_BLUE)
        self._selected_idx = idx

        if raw:
            self._set_main_image(raw, stage=True)

    # ------------------------------------------------------------------
    # Browse Files
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
            # Clear thumbnail selection — browsed
            # image is not from the strip
            for frame in self._thumb_frames:
                frame.configure(fg_color="gray25")
            self._selected_idx = -1
            self._set_main_image(raw, stage=True)
        except Exception as exc:
            print(f"[browse] {exc}")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _on_save_clicked(self):
        if not self._staged_bytes:
            return

        image_bytes = self._staged_bytes

        # Resize if requested
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
                    f"[cover art] resize failed: "
                    f"{exc}")

        self._save_btn.configure(
            state="disabled", text="Saving…")

        def _worker():
            from app.helpers import _write_cover_art
            err = _write_cover_art(
                self._path, image_bytes)
            self._win.after(
                0, lambda:
                self._on_save_done(
                    image_bytes, err))

        threading.Thread(
            target=_worker, daemon=True).start()

    def _on_save_done(self, image_bytes: bytes,
                       err: str | None):
        if err:
            self._save_btn.configure(
                state="normal", text="💾  Save")
            self._search_status.configure(
                text=f"⚠ Save failed: {err}",
                text_color=DANGER_RED)
            return

        # Success — notify caller and close
        self._on_save(self._path, image_bytes)
        self._win.destroy()

