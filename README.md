# SuperMusicTag

---

## What is SuperMusicTag?

SuperMusicTag is a desktop music library management tool that helps you clean up, organize, and correct the metadata tags and filenames of your local audio files — without manual editing.

It scans your music directories, identifies files with missing or incorrect tags, suggests corrections using AI (Google Gemini), and lets you review and approve every change before anything is written to disk.

Thanks for using it.

---

## Features

### All Files
- Sortable spreadsheet view of your entire music library
- Search and filter by filename, title, artist, album, or location
- Inline filename and tag editing (double-click or F2)
- Multi-file tag editing with keep / remove / custom value options
- Reorder columns and export to CSV
- Duplicate file detection by filename and by metadata
- Fix Filenames — bulk rename files to match their current tags
- Delete files to Recycle Bin
- Full Undo / Redo
- Right-click menu: Play files, Edit Cover Art, Revert changes

### Unorganized Files
- Automatically detects files with missing tags, filename mismatches, or missing cover art
- Configurable detection conditions — enable or disable each condition independently
- AI-powered tag suggestions using Google Gemini with Google Search grounding
- Tags-only mode for offline organization using existing metadata
- Per-field suggestion editing via inline double-click, right-click menu, or sidebar
- Multi-file batch editing for shared fields across suggestions
- Fix Filenames button scoped to checked rows only
- Separate operation feedback and persistent count display
- Review and approve changes before anything is written to disk

### Fuzzy Matches
- Filename-based mismatch detection:
  - Artist portion mismatches (e.g. `Beatles` vs `beatles`)
  - Title portion mismatches (e.g. `Bohemian Rapsody` vs `Bohemian Rhapsody`)
  - Separator format mismatches (e.g. ` -- ` vs ` - `)
  - Collaboration tag mismatches (e.g. `ft.` vs `feat.` vs `x`)
- Normalize artist names, titles, separators, and collaboration keywords
- Choose whether to update audio tags, filenames, or both when applying fixes
- Dismiss clusters for the current session or permanently
- Collaboration section can be hidden via Settings

### Cover Art
- View embedded cover art for any selected file
- Search iTunes and Deezer simultaneously for matching artwork
- Fallback search chain: artist + title → artist + album → title only → filename
- Browse and embed local image files
- Optional resize to 600×600 JPEG before embedding
- **Bulk cover art editing** — select multiple files in All Files, right-click, and edit cover art for each file in sequence with automatic search prefetching per file

### Duplicate Detection
- Detects duplicates by filename stem and by matching artist + title tags
- Groups results into cards for easy review
- Navigate directly to duplicate files in the All Files tab
- Results cached — reopening the window does not require a rescan

### Sidebar
- Displays cover art, filename, title, artist, and album for the selected file
- Double-click cover art to open the cover art editor
- Multi-file editing with keep / remove / custom value options
- One-click Gemini analysis for individual tracks
- Analyze button respects the active organize strategy

### Configuration
- Naming convention: `Artist - Title` or `Title - Artist`
- Fuzzy match threshold (50–100%)
- Show or hide the collaboration keyword section in Fuzzy Matches
- Organize strategy: Use Gemini AI or tags only
- Gemini field selection: choose which fields (title, artist, album) Gemini searches for
- Unorganized conditions: configure which problems are flagged
- Table theme: dark mode or light mode row colours
- Filename character replacements: configure how illegal characters are substituted
- Custom Gemini prompt: override the default instruction text
- Developer Tools: terminal logging for Gemini requests and responses

---

## Supported Formats

| Format | Read Tags | Write Tags | Rename | Cover Art |
|--------|-----------|------------|--------|-----------|
| MP3    | ✅        | ✅         | ✅     | ✅        |
| FLAC   | ✅        | ✅         | ✅     | ✅        |
| M4A    | ✅        | ✅         | ✅     | ✅        |
| OGG    | ✅        | ✅         | ✅     | ✅        |
| WAV    | ✅        | ✅         | ✅     | ❌        |

---

## Requirements

- Python 3.10–3.13 (Python 3.14 is supported with an automatic workaround)
- A Google Gemini API key (for AI features)

Install dependencies:

```bash
pip install -r requirements.txt
```

Set your Gemini API key:

```bash
# Windows
setx GEMINI_API_KEY "your-key-here"

# macOS / Linux
export GEMINI_API_KEY="your-key-here"
```

---

## Running the App

```bash
python main.py
```

---

## How It Works

### Review before commit
No file is ever modified until you explicitly confirm in the Review & Save Changes dialog. All edits — tag changes, filename renames, cover art — are staged first and shown to you for approval.

### Undo / Redo
Every edit to tags or filenames is undoable. Undo and Redo are available via the toolbar buttons or Ctrl+Z / Ctrl+Y.

### Security
All file operations are restricted to the directories you explicitly load into the app. No file outside those directories can be read, renamed, or deleted.

---

## Notes

- Cover art display and editing requires Pillow — install with `pip install pillow`
- Sending files to the Recycle Bin requires send2trash — install with `pip install send2trash`
- Cover art writes use ID3v2.3 for MP3 files, ensuring compatibility with Windows Explorer and Windows Media Player

---

*Written by Claude · Powered by Gemini · Designed by Digital Imagination*