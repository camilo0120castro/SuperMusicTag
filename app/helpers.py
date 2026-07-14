# app/helpers.py
"""
Pure module-level utility functions. No UI, no state, no CTk.
All functions are stateless and importable anywhere.
"""
import re
import os
import io
import tkinter as tk
import mutagen


from app.constants import _ILLEGAL_FILENAME_CHARS, _COLLAB_PATTERN




# ---------------------------------------------------------------------------
# Optional Pillow for cover art
# ---------------------------------------------------------------------------
try:
    from PIL import Image as _PILImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILImage = None
    _PILLOW_AVAILABLE = False




# ---------------------------------------------------------------------------
# Optional mutagen OGG cover art
# ---------------------------------------------------------------------------
try:
    import base64 as _base64
    from mutagen.flac import Picture as _MutagenPicture
    _MUTAGEN_PICTURE_AVAILABLE = True
except ImportError:
    _base64 = None
    _MutagenPicture = None
    _MUTAGEN_PICTURE_AVAILABLE = False




# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def _normalize_artist_for_matching(artist: str) -> str:
    base = _COLLAB_PATTERN.sub('', artist)
    base = base.strip().lower()
    base = re.sub(r'\s+', ' ', base)
    base = re.sub(r'^the\s+', '', base)
    return base




def _sanitize_filename_part(
        text: str,
        replacements: dict | None = None) -> str:
    """
    Sanitize a filename part by replacing illegal
    characters with configured replacements.

    If replacements is provided it must be a dict
    mapping each forbidden character to its
    replacement string. If not provided, falls back
    to the built-in defaults:
      '?' → '¿'
      all others → '_'
    """
    if replacements is None:
        # Built-in defaults — used when called from
        # paths that do not have access to app state
        result = text.replace('?', '¿')
        result = _ILLEGAL_FILENAME_CHARS.sub(
            '_', result)
        return result.strip()

    # Apply replacements in a defined order.
    # Longer replacements are applied first to avoid
    # partial matches (not a concern here since all
    # keys are single characters, but kept for safety).
    result = text
    for char, replacement in replacements.items():
        result = result.replace(char, replacement)
    return result.strip()




def _get_tag_str(val) -> str:
    if isinstance(val, list) and val:
        return str(val[0])
    return str(val) if val else "Unknown"




def _format_length(seconds) -> str:
    if not seconds:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"




def _sort_key(val: str):
    v = val.split()[0] if "kbps" in val else val
    if ":" in v:
        parts = v.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    try:
        return float(v)
    except ValueError:
        return v.lower()




def _extract_cover_art_bytes(file_path: str) -> bytes | None:
    """Extract raw cover art bytes from an audio file."""
    try:
        audio = mutagen.File(file_path)
        if audio is None:
            return None
        if hasattr(audio, "tags") and audio.tags:
            for key in audio.tags.keys():
                if str(key).startswith("APIC"):
                    return audio.tags[key].data
        if hasattr(audio, "pictures") and audio.pictures:
            return audio.pictures[0].data
        if (hasattr(audio, "tags") and audio.tags
                and "covr" in audio.tags):
            covr = audio.tags["covr"]
            if covr:
                return bytes(covr[0])
        if (_MUTAGEN_PICTURE_AVAILABLE and
                hasattr(audio, "tags") and audio.tags):
            mbp = audio.tags.get(
                "metadata_block_picture", [])
            if mbp:
                data = _base64.b64decode(mbp[0])
                pic  = _MutagenPicture(data)
                return pic.data
    except Exception:
        pass
    return None




def _validate_new_filename(
        new_name: str,
        original_name: str) -> tuple[bool, str | None]:
    """
    Returns (is_valid, warning_or_None).
    is_valid=False  → reject entirely.
    is_valid=True with message → warn but allow.
    """
    stripped = new_name.strip()
    if not stripped:
        return False, "Filename cannot be empty."
    stem, ext = os.path.splitext(stripped)
    if _ILLEGAL_FILENAME_CHARS.search(stem):
        return False, "Filename contains illegal characters."
    orig_ext = os.path.splitext(original_name)[1].lower()
    new_ext  = ext.lower()
    if orig_ext and orig_ext != new_ext:
        new_ext_display = new_ext if new_ext else "none"
        return True, (
            f"Extension changed from '{orig_ext}' to "
            f"'{new_ext_display}'.")
    return True, None




def _split_path_parts(path: str) -> list:
    """Split a path into all components including the root."""
    parts = []
    while True:
        head, tail = os.path.split(path)
        if tail:
            parts.append(tail)
        elif head:
            parts.append(head)
            break
        else:
            break
        path = head
    parts.reverse()
    return parts




def _truncate_path(full_path: str,
                   max_tail_components: int = 2) -> str:
    """
    Returns a shortened path string for the Location column.
    Always shows the drive/root and the last N components.
    Collapses the middle to "…".
    """
    parts = _split_path_parts(full_path)
    if len(parts) <= max_tail_components + 1:
        return full_path
    sep  = os.sep
    root = parts[0]
    tail = parts[-max_tail_components:]
    return root + "…" + sep + sep.join(tail)




# ---------------------------------------------------------------------------
# Treeview location-column tooltip
# ---------------------------------------------------------------------------


class _TreeviewTooltip:
    """
    Lightweight hover tooltip for a ttk.Treeview cell.
    Appears after DELAY ms, disappears on mouse leave.
    """


    DELAY = 600


    def __init__(self, tree, col_id: str, text_getter):
        self._tree        = tree
        self._col_id      = col_id
        self._text_getter = text_getter
        self._tip_window  = None
        self._after_id    = None
        self._last_iid    = None


        tree.bind("<Motion>",   self._on_motion, add="+")
        tree.bind("<Leave>",    self._on_leave,  add="+")
        tree.bind("<Button-1>", self._hide,      add="+")


    def _on_motion(self, event):
        iid = self._tree.identify_row(event.y)
        col = self._tree.identify_column(event.x)


        try:
            col_id = self._tree.column(col, "id")
        except Exception:
            col_id = None


        if not iid or col_id != self._col_id:
            self._hide()
            return


        if iid == self._last_iid:
            return


        self._hide()
        self._last_iid = iid
        self._after_id = self._tree.after(
            self.DELAY,
            lambda: self._show(
                event.x_root + 16,
                event.y_root + 8,
                iid))


    def _on_leave(self, _event):
        self._hide()


    def _show(self, x: int, y: int, iid: str):
        text = self._text_getter(iid)
        if not text:
            return
        self._tip_window = tw = tk.Toplevel(self._tree)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        tw.lift()


        lbl = tk.Label(
            tw, text=text,
            justify="left",
            background="#1c1c1c",
            foreground="white",
            relief="solid",
            borderwidth=1,
            font=("", 10),
            padx=6, pady=4)
        lbl.pack()


    def _hide(self, _event=None):
        self._last_iid = None
        if self._after_id is not None:
            try:
                self._tree.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


def _write_cover_art(
        path: str,
        image_bytes: bytes) -> str | None:
    """
    Embed image_bytes as cover art in the audio file
    at path. Format-aware: MP3, FLAC, M4A, OGG.

    Returns None on success, or an error string on
    failure.
    """
    import mutagen
    ext = os.path.splitext(path)[1].lower()

    try:
        # ── MP3 (ID3 APIC) ────────────────────────────
        if ext == ".mp3":
            from mutagen.id3 import (
                ID3, APIC, ID3NoHeaderError)
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(
                encoding=3,       # UTF-8
                mime="image/jpeg",
                type=3,           # Cover (front)
                desc="Cover",
                data=image_bytes,
            ))
            tags.save(path, v2_version=3)

        # ── FLAC ──────────────────────────────────────
        elif ext == ".flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(path)
            audio.clear_pictures()
            pic = Picture()
            pic.type        = 3   # Cover (front)
            pic.mime        = "image/jpeg"
            pic.desc        = "Cover"
            pic.data        = image_bytes
            audio.add_picture(pic)
            audio.save()

        # ── M4A / AAC ─────────────────────────────────
        elif ext in (".m4a", ".aac"):
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(path)
            audio.tags["covr"] = [
                MP4Cover(
                    image_bytes,
                    imageformat=MP4Cover.FORMAT_JPEG)
            ]
            audio.save()

        # ── OGG ───────────────────────────────────────
        elif ext == ".ogg":
            import base64
            from mutagen.oggvorbis import OggVorbis
            from mutagen.flac import Picture
            audio = OggVorbis(path)
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = image_bytes
            encoded = base64.b64encode(
                pic.write()).decode("ascii")
            audio["metadata_block_picture"] = [
                encoded]
            audio.save()

        else:
            return (
                f"Unsupported format: {ext}")

        return None

    except Exception as exc:
        return str(exc)


def _setup_treeview_keyboard_navigation(tree):
    """
    Adds advanced keyboard navigation to a ttk.Treeview widget:
    1. Home: Jumps to and selects the first item.
    2. End: Jumps to and selects the last item.
    3. Page Up (Prior): Jumps to the item one page up.
    4. Page Down (Next): Jumps to the item one page down.
    5. Letter/number keys: Jumps to the first item starting with that character (case-insensitive, matching "filename" column).
    """
    def _go_to_iid(iid):
        if not iid:
            return
        tree.selection_set(iid)
        tree.focus(iid)
        tree.see(iid)
        # Generate the select event to trigger sidebar sync
        tree.event_generate("<<TreeviewSelect>>")

    def _on_home(event):
        children = tree.get_children("")
        if children:
            _go_to_iid(children[0])
        return "break"

    def _on_end(event):
        children = tree.get_children("")
        if children:
            _go_to_iid(children[-1])
        return "break"

    def _on_page_up(event):
        children = tree.get_children("")
        if not children:
            return "break"
        focus = tree.focus()
        if not focus:
            _go_to_iid(children[0])
            return "break"
        try:
            idx = children.index(focus)
            new_idx = max(0, idx - 15)
            _go_to_iid(children[new_idx])
        except ValueError:
            _go_to_iid(children[0])
        return "break"

    def _on_page_down(event):
        children = tree.get_children("")
        if not children:
            return "break"
        focus = tree.focus()
        if not focus:
            _go_to_iid(children[0])
            return "break"
        try:
            idx = children.index(focus)
            new_idx = min(len(children) - 1, idx + 15)
            _go_to_iid(children[new_idx])
        except ValueError:
            _go_to_iid(children[0])
        return "break"

    def _on_key_press(event):
        # Ignore Control modifier combos (state & 4)
        if event.state & 0x0004:
            return
        char = event.char
        if not char or not char.isalnum():
            return
        char_lower = char.lower()
        children = tree.get_children("")
        if not children:
            return

        focus = tree.focus()
        start_idx = 0
        if focus:
            try:
                start_idx = children.index(focus) + 1
            except ValueError:
                pass

        for offset in range(len(children)):
            idx = (start_idx + offset) % len(children)
            iid = children[idx]
            try:
                val = str(tree.set(iid, "filename")).strip().lower()
                if val.startswith(char_lower):
                    _go_to_iid(iid)
                    break
            except Exception:
                pass
        return "break"

    tree.bind("<Home>", _on_home)
    tree.bind("<End>", _on_end)
    tree.bind("<Prior>", _on_page_up)
    tree.bind("<Next>", _on_page_down)
    tree.bind("<Key>", _on_key_press)


        