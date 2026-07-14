# app/constants.py
"""
Every module-level constant, colour, regex pattern, and frozen set.
Zero logic, zero imports from other app modules.
"""
import re
import os




# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "supermusictagconfig.json")




# ---------------------------------------------------------------------------
# Audio extensions
# ---------------------------------------------------------------------------
AUDIO_EXTENSIONS = frozenset(
    {'.mp3', '.wav', '.flac', '.m4a', '.ogg'})
GEMINI_MODEL     = "gemini-2.5-flash"




# ---------------------------------------------------------------------------
# All Files treeview columns
# ---------------------------------------------------------------------------
COL_DEFS = [
    ("filename",      "File Name",     300, 200, False),
    ("title",         "Title",         250, 150, False),
    ("artist",        "Artist",        200, 150, False),
    ("album",         "Album",         200, 150, False),
    ("bitrate",       "Bitrate",       100,  80, False),
    ("length",        "Length",         80,  60, False),
    ("date_modified", "Date Modified", 160, 120, True),
    ("location",      "Location",      220, 120, False),
]
COL_IDS    = tuple(c[0] for c in COL_DEFS)
COL_LABELS = {c[0]: c[1] for c in COL_DEFS}




# ---------------------------------------------------------------------------
# Unorganized treeview columns
# ---------------------------------------------------------------------------
UNORG_COL_DEFS = [
    ("check",           "☑",                  48,  44, False),
    ("filename",        "File Name",          240, 160, False),
    ("reason",          "Reason",             140,  90, False),
    ("current_artist",  "Artist",             150, 100, False),
    ("suggest_artist",  "Artist (suggest)",   150, 100, False),
    ("current_title",   "Title",              180, 120, False),
    ("suggest_title",   "Title (suggest)",    180, 120, False),
    ("current_album",   "Album",              150, 100, False),
    ("suggest_album",   "Album (suggest)",    150, 100, False),
    ("confidence",      "Confidence",          90,  70, False),
]
UNORG_COL_IDS    = tuple(c[0] for c in UNORG_COL_DEFS)
UNORG_COL_LABELS = {c[0]: c[1] for c in UNORG_COL_DEFS}


UNORG_EDITABLE_COLS = {
    "suggest_artist": "artist",
    "suggest_title":  "title",
    "suggest_album":  "album",
}




# ---------------------------------------------------------------------------
# Tag key filtering
# ---------------------------------------------------------------------------
_STANDARD_TAG_PREFIXES = (
    'TPE1', 'TIT2', 'TALB', 'ARTIST', 'TITLE', 'ALBUM')
_IGNORED_TAG_KEYS      = frozenset({'APIC', 'COMM', 'USLT'})




# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BG_DARK           = "#2b2b2b"
BG_DARK_ALT       = "#333333"
HEADING_BG        = "#1a3a5c"
HEADING_BG_ACTIVE = "#2a5a8c"
WARNING_YELLOW    = "#FFA726"
WARNING_BG        = "#3d2600"
DIRTY_BG          = "#4a3800"
DIRTY_FG          = "#FFD54F"
# More visible amber for unorg suggestion rows.
# Brighter than DIRTY_BG so it is clearly visible
# against the dark treeview background.
SUGGESTION_BG     = "#6b4400"
TAB_BAR_BG        = ("#d0d0d0", "#1f1f1f")
ROW_COLOURS       = {"even": BG_DARK, "odd": BG_DARK_ALT}
ACCENT_BLUE       = "#1F6AA5"
ACCENT_BLUE_HOVER = "#144870"
ACCENT_BLUE_MID   = "#245d8b"
ORANGE_PRIMARY    = "#F57C00"
ORANGE_HOVER      = "#EF6C00"
DANGER_RED        = "#D32F2F"
DANGER_RED_HOVER  = "#B71C1C"
SAVE_BLUE         = "#1565C0"
SAVE_BLUE_HOVER   = "#0D47A1"
CANCEL_BG         = ("gray75", "gray25")
CANCEL_BG_HOVER   = ("gray65", "gray35")
SUCCESS_GREEN     = "#00C853"
PINNED_BG         = "#1a3a1a"
PINNED_FG         = "#69F0AE"
TEXT_PRIMARY      = "white"
TEXT_SECONDARY    = "gray"
TEXT_MUTED        = "gray60"
TEXT_DISABLED     = ("gray25", "gray80")
TEXT_WARNING      = "orange"
TEXT_ADAPTIVE     = ("gray10", "gray90")
TEXT_BLACK        = "#1a1a1a"
# WARNING_YELLOW    — bright amber for dark backgrounds (banners, overlays)
# WARNING_ON_LIGHT  — dark burnt-orange for use on light/transparent backgrounds
WARNING_ON_LIGHT  = "#B45309"


# ---------------------------------------------------------------------------
# Treeview theme — dark (default) and light mode colour sets
# ---------------------------------------------------------------------------
# Dark mode (current defaults)
TV_DARK_ROW_EVEN      = "#2b2b2b"
TV_DARK_ROW_ODD       = "#333333"
TV_DARK_TEXT          = "white"
TV_DARK_DIRTY_BG      = "#4a3800"
TV_DARK_DIRTY_FG      = "#FFD54F"
TV_DARK_SUGGESTION_BG = "#6b4400"
TV_DARK_SUGGESTION_FG = "#FFD54F"

# Light mode
TV_LIGHT_ROW_EVEN      = "#FFFFFF"
TV_LIGHT_ROW_ODD       = "#F0F0F0"
TV_LIGHT_TEXT          = "#1a1a1a"
TV_LIGHT_DIRTY_BG      = "#FFCA28"
TV_LIGHT_DIRTY_FG      = "#3E2000"
TV_LIGHT_SUGGESTION_BG = "#FFE082"
TV_LIGHT_SUGGESTION_FG = "#5D3A00"




# ---------------------------------------------------------------------------
# Combo button appearance
# ---------------------------------------------------------------------------
_COMBO_BTN_HIDDEN  = ("gray20", "gray20")
_COMBO_BTN_VISIBLE = (ORANGE_PRIMARY, ORANGE_HOVER)




# ---------------------------------------------------------------------------
# Filename / regex
# ---------------------------------------------------------------------------
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')
_MAX_UNDO_STEPS         = 20
_COLLAB_PATTERN         = re.compile(
    r'\s*(?:feat(?:uring)?\.?|ft\.?|with|w/|x|vs\.?|&|and)'
    r'\s+.*$',
    re.IGNORECASE
)
_COVER_SIZE = (150, 150)


# ---------------------------------------------------------------------------
# Default filename character replacements.
# Keys are the forbidden characters, values are their replacements.
# Used by _sanitize_filename_part and the configuration overlay.
# ---------------------------------------------------------------------------
FILENAME_REPLACEMENTS_DEFAULT = {
    "?":  "¿",
    "\\": "_",
    "/":  "_",
    ":":  "_",
    "*":  "_",
    "\"": "_",
    "<":  "_",
    ">":  "_",
    "|":  "_",
}


# ---------------------------------------------------------------------------
# Default Gemini prompt (static instruction portion only).
# The dynamic parts — fields_str, naming, preserve_block, and the
# file batch JSON — are always appended in code and are not part of
# this constant.
# ---------------------------------------------------------------------------
GEMINI_DEFAULT_PROMPT = """You are a music metadata expert. I will give you a JSON array of
audio files. Each entry has a filename and its current metadata tags
(some may be "Unknown").

For each file:
1. Use the filename and existing tags to identify the correct
   {fields_str}.
2. If the tags are incomplete or wrong, use your knowledge and
   browse the web if needed to find the correct information.
3. Suggest a clean filename following this convention:
   "{naming}" with the original file extension preserved.
   When constructing the filename, replace the character '?'
   with '¿' and any other characters that are illegal in
   filenames (such as / \\ : * " < > |) with '_'.
4. Rate your confidence as "high", "medium", or "low".
5. If you genuinely cannot identify a file, still return an entry
   with your best guess and confidence "low".{preserve_block}

Return ONLY a valid JSON array with no markdown, no code fences,
and no explanation. Each element must have exactly these keys:
  index, suggested_title, suggested_artist, suggested_album,
  suggested_filename, confidence"""

