# app/fuzzy_worker.py
"""
Background fuzzy clustering thread function.
Pure function — no UI access, safe to run on a daemon thread.


Four passes are performed:
  Pass A — Artist portion mismatches:
      Extract the artist substring from each filename stem (using the
      naming convention to know which side of the separator is artist).
      Fuzzy-cluster the artist substrings.


  Pass B — Title portion mismatches (scoped within artist clusters):
      Within each artist cluster from Pass A, compare title substrings.
      Only flagged when artist portions already match well enough to
      establish the files are "about the same artist".


  Pass C — Separator / format mismatches:
      Normalise each stem's separator to a canonical form and
      exact-compare. Any file whose separator is not " - " is flagged.
      Groups of files sharing the same stem (modulo separator) are
      returned as separator clusters.


  Pass D — Collaboration tag mismatches (subset of Pass A):
      Within artist clusters, detect files where the collaboration
      keyword differs (ft. vs feat. vs x vs & etc.) even though the
      base artist name is the same. These are tagged separately so the
      UI can offer targeted quick-fix buttons.


Return value — callback receives a dict:
    {
        "artist_title": [cluster, ...],   # Passes A + B combined
        "separator":    [cluster, ...],   # Pass C
        "collab":       [cluster, ...],   # Pass D
    }


Each cluster is a dict described in the docstrings below.
"""
import re
import os
from thefuzz import fuzz


from app.helpers import _normalize_artist_for_matching
from app.constants import _COLLAB_PATTERN




# ---------------------------------------------------------------------------
# Separator pattern — matches any separator that is not canonical " - "
# Canonical form: exactly one space, one hyphen, one space.
# ---------------------------------------------------------------------------
_SEP_VARIANTS = re.compile(
    r'\s*'           # optional leading spaces
    r'[-\u2013\u2014]+'   # one or more hyphens / en-dash / em-dash
    r'\s*',          # optional trailing spaces
)


# Collaboration keywords — used to detect collab tag mismatches
_COLLAB_KEYWORDS = re.compile(
    r'\b(feat(?:uring)?\.?|ft\.?|with|w/|(?<!\w)x(?!\w)|vs\.?|&|and)\b',
    re.IGNORECASE,
)




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_sep(stem: str) -> str:
    """Replace any separator variant with the canonical ' - '."""
    return _SEP_VARIANTS.sub(' - ', stem, count=1)




def _split_stem(stem: str, naming: str) -> tuple[str, str]:
    """
    Split a filename stem into (artist_part, title_part) using the
    canonical separator ' - ' after normalising the separator.


    Returns ("", stem) if no separator is found.
    """
    canonical = _canonical_sep(stem)
    if ' - ' not in canonical:
        return ("", stem)
    idx = canonical.index(' - ')
    if naming == "Artist - Title":
        return (canonical[:idx].strip(), canonical[idx + 3:].strip())
    else:
        return (canonical[idx + 3:].strip(), canonical[:idx].strip())




def _ignore_key(a: str, b: str) -> str:
    lo, hi = sorted([a.lower(), b.lower()])
    return f"{lo}|||{hi}"




def _is_ignored(a: str, b: str, ignore_pairs: set) -> bool:
    return _ignore_key(a, b) in ignore_pairs




def _base_artist(artist: str) -> str:
    """Strip collaboration suffix to get the base artist name."""
    return _COLLAB_PATTERN.sub('', artist).strip()




def _collab_keyword(artist: str) -> str:
    """
    Extract the collaboration keyword from an artist string.
    Returns "" if none found.
    e.g. "Gorillaz ft Bad Bunny" → "ft"
    """
    m = _COLLAB_KEYWORDS.search(artist)
    return m.group(1).lower() if m else ""




# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}


    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x


    def union(self, x, y):
        self.parent[self.find(x)] = self.find(y)


    def groups(self) -> list:
        result: dict = {}
        for item in self.parent:
            root = self.find(item)
            result.setdefault(root, []).append(item)
        return [g for g in result.values() if len(g) > 1]




# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _run_fuzzy_clustering_thread(
        stems: list,          # unique filename stems (no extension)
        naming: str,          # "Artist - Title" or "Title - Artist"
        threshold: int,       # fuzzy match threshold (50–100)
        ignore_pairs: set,    # persisted ignore pairs
        callback):
    """
    Pure function — no UI access. Called on a daemon thread.
    Calls callback(result_dict) when done.
    """


    # ------------------------------------------------------------------ #
    # Pass C — Separator mismatches (cheapest, run first)                 #
    # ------------------------------------------------------------------ #
    separator_clusters = _pass_separator(stems, ignore_pairs)


    # ------------------------------------------------------------------ #
    # Passes A + B + D — Artist/title/collab mismatches                  #
    # ------------------------------------------------------------------ #
    artist_title_clusters, collab_clusters = _pass_artist_title(
        stems, naming, threshold, ignore_pairs)


    callback({
        "artist_title": artist_title_clusters,
        "separator":    separator_clusters,
        "collab":       collab_clusters,
    })




# ---------------------------------------------------------------------------
# Pass C — Separator mismatches
# ---------------------------------------------------------------------------


def _pass_separator(stems: list, ignore_pairs: set) -> list:
    """
    Group stems that refer to the same song but use different separators.


    Strategy:
      1. For each stem, produce a normalised key by replacing its
         separator with the canonical ' - ' and lower-casing.
      2. Group stems by normalised key.
      3. Within each group, check whether any stem's separator differs
         from the canonical form.
      4. Return groups that contain at least one non-canonical stem.


    Each cluster dict:
        {
            "kind":       "separator",
            "stems":      [stem, ...],          # original stems
            "canonical":  "Artist - Title",     # normalised form
            "separators": {"stem": "found_sep"} # per-stem separator found
        }
    """
    # Map: normalised_key → list of original stems
    groups: dict = {}
    sep_found: dict = {}   # stem → the raw separator text found


    for stem in stems:
        # Find the raw separator in this stem
        m = _SEP_VARIANTS.search(stem)
        raw_sep = m.group(0) if m else None
        canonical_key = _canonical_sep(stem).lower()
        groups.setdefault(canonical_key, []).append(stem)
        if raw_sep is not None:
            sep_found[stem] = raw_sep


    result = []
    for canonical_key, group in groups.items():
        if len(group) < 2:
            continue
        # Check if any stem has a non-canonical separator
        non_canonical = [
            s for s in group
            if sep_found.get(s, " - ") != " - "
        ]
        if not non_canonical:
            continue
        # Check ignore
        skip = False
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if _is_ignored(a, b, ignore_pairs):
                    skip = True
                    break
            if skip:
                break
        if skip:
            continue
        result.append({
            "kind":       "separator",
            "stems":      group,
            "canonical":  _canonical_sep(group[0]),
            "separators": {s: sep_found.get(s, " - ") for s in group},
        })
    return result




# ---------------------------------------------------------------------------
# Passes A + B + D — Artist / title / collaboration mismatches
# ---------------------------------------------------------------------------


def _pass_artist_title(
        stems: list,
        naming: str,
        threshold: int,
        ignore_pairs: set) -> tuple[list, list]:
    """
    Pass A: cluster stems by artist portion (fuzzy match).
    Pass B: within each artist cluster, find title portion mismatches.
    Pass D: within each artist cluster, find collaboration tag mismatches.


    Returns (artist_title_clusters, collab_clusters).


    artist_title_clusters — list of cluster dicts:
        {
            "kind":           "artist_title",
            "stems":          [stem, ...],
            "artist_parts":   {stem: artist_str},
            "title_parts":    {stem: title_str},
            "artist_mismatch": bool,
            "title_mismatch":  bool,
        }


    collab_clusters — list of cluster dicts:
        {
            "kind":           "collab",
            "stems":          [stem, ...],
            "artist_parts":   {stem: artist_str},
            "base_artist":    str,    # base artist without collab suffix
            "keywords":       {stem: keyword_str},  # ft / feat / x etc.
        }
    """
    # Split every stem into (artist_part, title_part)
    split: dict = {}   # stem → (artist_part, title_part)
    for stem in stems:
        split[stem] = _split_stem(stem, naming)


    # Only process stems that have a recognisable separator
    valid_stems = [s for s in stems if split[s][0] != ""]


    if len(valid_stems) < 2:
        return [], []


    # ---- Pass A: artist portion clustering ----------------------------
    artist_parts = {s: split[s][0] for s in valid_stems}
    normalised   = {s: _normalize_artist_for_matching(artist_parts[s])
                    for s in valid_stems}


    uf = _UnionFind(valid_stems)
    for i, s1 in enumerate(valid_stems):
        for s2 in valid_stems[i + 1:]:
            if _is_ignored(s1, s2, ignore_pairs):
                continue
            n1, n2 = normalised[s1], normalised[s2]
            score  = fuzz.ratio(n1, n2)
            if score < threshold:
                score = fuzz.token_sort_ratio(n1, n2)
            if score >= threshold:
                uf.union(s1, s2)


    artist_clusters = uf.groups()


    # ---- Pass B + D: within each artist cluster ----------------------
    artist_title_clusters = []
    collab_clusters       = []


    for cluster in artist_clusters:
        a_parts = {s: artist_parts[s] for s in cluster}
        t_parts = {s: split[s][1]     for s in cluster}


        # Artist mismatch: are all artist portions identical (case-insensitive)?
        unique_artists  = {v.lower() for v in a_parts.values()}
        artist_mismatch = len(unique_artists) > 1


        # Title mismatch: fuzzy-compare title portions within the cluster
        title_mismatch = False
        title_stems    = list(cluster)
        if len(title_stems) >= 2:
            for i, s1 in enumerate(title_stems):
                for s2 in title_stems[i + 1:]:
                    t1 = t_parts[s1].lower()
                    t2 = t_parts[s2].lower()
                    if t1 == t2:
                        continue
                    score = fuzz.ratio(t1, t2)
                    if score < threshold:
                        score = fuzz.token_sort_ratio(t1, t2)
                    if score >= threshold:
                        title_mismatch = True
                        break
                if title_mismatch:
                    break


        if artist_mismatch or title_mismatch:
            artist_title_clusters.append({
                "kind":            "artist_title",
                "stems":           cluster,
                "artist_parts":    a_parts,
                "title_parts":     t_parts,
                "artist_mismatch": artist_mismatch,
                "title_mismatch":  title_mismatch,
            })


        # Pass D: collaboration tag mismatches
        # Only applies when all stems share the same BASE artist
        base_artists = {_base_artist(v).lower() for v in a_parts.values()}
        if len(base_artists) == 1:
            keywords = {s: _collab_keyword(a_parts[s]) for s in cluster}
            unique_kw = {v for v in keywords.values() if v}
            if len(unique_kw) > 1:
                collab_clusters.append({
                    "kind":        "collab",
                    "stems":       cluster,
                    "artist_parts": a_parts,
                    "base_artist": _base_artist(
                        next(iter(a_parts.values()))),
                    "keywords":    keywords,
                })


    return artist_title_clusters, collab_clusters


# ---------------------------------------------------------------------------
# Collaboration keyword normalization (global scan)
# ---------------------------------------------------------------------------

# Keywords to detect — & and "and" excluded intentionally
# as they appear too often in band names to be reliable.

# Pattern 1: bracketed collaboration — matches the entire
# (keyword artist) group including the closing ).
# Only matches ( — never [ so [Radio Edit] is never touched.
_COLLAB_BRACKETED_PATTERN = re.compile(
    r'\(\s*'
    r'(?:feat(?:uring)?\.?|(?<!\w)ft\.?|with|w/|(?<!\w)x(?!\w)|vs\.?)'
    r'\s+'
    r'[^)]*'    # collab artist — everything up to closing )
    r'\)',
    re.IGNORECASE
)

# Pattern 2: plain collaboration — matches keyword followed
# by space and artist, no surrounding brackets.
# Uses a negative lookbehind for ( to avoid double-matching
# when the bracketed pattern has already been applied.
_COLLAB_PLAIN_PATTERN = re.compile(
    r'(?<!\()'
    r'(?:feat(?:uring)?\.?|(?<!\w)ft\.?|with|w/|(?<!\w)x(?!\w)|vs\.?)'
    r'\s+'
    r'((?:[^\s\(\[]+(?:\s+(?![(\[]))?)+)',
    re.IGNORECASE
)

# Helper to detect either bracketed or plain collab keyword
_COLLAB_DETECT_PATTERN = re.compile(
    r'(\(?\s*)'
    r'(feat(?:uring)?\.?|(?<!\w)ft\.?|with|w/|(?<!\w)x(?!\w)|vs\.?)'
    r'\s+',
    re.IGNORECASE
)

def _scan_collab_normalizations(
        stems: list,
        naming: str) -> list:
    """
    Scans all filename stems for collaboration keyword
    variants and returns a list of match dicts.

    Each match dict:
    {
        "stem":         original stem,
        "position":     "artist" or "title",
        "keyword":      the raw keyword found (e.g. "featuring"),
        "had_brackets": bool — True if wrapped in (),
        "collab_artist": the collaborating artist string,
    }

    Returns all stems containing a detectable collaboration
    keyword regardless of which canonical form the user
    will choose. Filtering by canonical form happens at
    apply time in _apply_collab_normalization.
    """
    results = []
    for stem in stems:
        artist_part, title_part = _split_stem(stem, naming)
        if not artist_part and not title_part:
            continue

        def _check(part: str, position: str) -> bool:
            m = _COLLAB_DETECT_PATTERN.search(part)
            if not m:
                return False
            had_brackets = "(" in m.group(1)
            collab_rest  = part[m.end():].strip()
            if had_brackets:
                # Strip only trailing ) from collab artist
                collab_rest = collab_rest.rstrip(")")
            results.append({
                "stem":         stem,
                "position":     position,
                "keyword":      m.group(2),
                "had_brackets": had_brackets,
                "collab_artist": collab_rest,
            })
            return True

        if not _check(artist_part, "artist"):
            _check(title_part, "title")

    results.sort(key=lambda m: m["stem"].lower())
    return results


def _apply_collab_normalization(
        stem: str,
        naming: str,
        canonical_kw: str) -> str | None:
    """
    Applies collaboration keyword normalization to a
    single stem. Returns the new stem, or None if no
    change was needed.

    Two-pass approach:
    Pass 1 — bracketed: replaces (keyword artist) as a
             complete unit. Closing ) is consumed by the
             match so no global removal is needed.
    Pass 2 — plain: replaces keyword artist without
             brackets. Only runs if pass 1 made no change
             on that part, preventing double-substitution.
    """
    artist_part, title_part = _split_stem(stem, naming)
    if not artist_part and not title_part:
        return None

    def _normalize_part(part: str) -> str:
        """
        Normalize a single artist or title part.
        Returns the normalized string — unchanged if
        no collaboration keyword is found.
        """
        # Pass 1 — bracketed: (keyword artist)
        # The entire (keyword artist) group including
        # closing ) is replaced with canonical_kw artist.
        def _replace_bracketed(m: re.Match) -> str:
            # m.group(0) is e.g. "(feat. Artist2)"
            # Extract the artist portion by stripping
            # the keyword and brackets from the match.
            inner = m.group(0)
            # Remove opening ( and closing )
            inner = inner.lstrip("(").rstrip(")")
            # Remove the keyword from the start
            kw_m = re.match(
                r'\s*(?:feat(?:uring)?\.?|ft\.?'
                r'|with|w/|(?<!\w)x(?!\w)|vs\.?)\s+',
                inner,
                re.IGNORECASE)
            if kw_m:
                collab_artist = inner[
                    kw_m.end():].strip()
            else:
                collab_artist = inner.strip()
            return f" {canonical_kw} {collab_artist}"

        result = _COLLAB_BRACKETED_PATTERN.sub(
            _replace_bracketed, part)

        if result != part:
            # Bracketed match found and replaced —
            # skip plain pass to avoid double-match
            return re.sub(r'  +', ' ', result).strip()

        # Pass 2 — plain: keyword artist (no brackets)
        def _replace_plain(m: re.Match) -> str:
            # m.group(1) is the captured collab artist
            collab_artist = m.group(1).strip()
            return f" {canonical_kw} {collab_artist}"

        result = _COLLAB_PLAIN_PATTERN.sub(
            _replace_plain, part)
        return re.sub(r'  +', ' ', result).strip()

    new_artist = _normalize_part(artist_part)
    new_title  = _normalize_part(title_part)

    if new_artist == artist_part and \
            new_title == title_part:
        return None

    if naming == "Artist - Title":
        return f"{new_artist} - {new_title}"
    else:
        return f"{new_title} - {new_artist}"

