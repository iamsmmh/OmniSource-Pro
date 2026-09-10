"""Duplicate detection engine for applications and repositories."""

import re
from collections.abc import Iterable
from urllib.parse import urlparse

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Normalize a name into a URL-safe slug."""
    return _SLUG_RE.sub("-", value.strip().lower()).strip("-")


def normalize_repo_name(value: str) -> str:
    """Normalize a repository full name (owner/repo) for comparison."""
    value = value.strip().lower().rstrip("/")
    if value.startswith(("http://", "https://", "git@", "ssh://")):
        parsed = urlparse(value.replace("git@", "ssh://"))
        value = parsed.path.strip("/")
        if value.endswith(".git"):
            value = value[:-4]
    return value


def tokenize(value: str | None) -> set:
    """Tokenize text into a set of lowercased words."""
    if not value:
        return set()
    return set(_SLUG_RE.split(value.lower()))


def jaccard(a: set, b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def name_similarity(name_a: str, name_b: str) -> float:
    """Compute a normalized similarity between two application names."""
    a, b = name_a.strip().lower(), name_b.strip().lower()
    if a == b:
        return 1.0
    # Token overlap (handles reordering and minor differences)
    token_score = jaccard(tokenize(a), tokenize(b))
    # Character bigram similarity (handles typos)
    char_score = _bigram_similarity(a, b)
    return max(token_score, char_score)


def _bigram_similarity(a: str, b: str) -> float:
    def bigrams(s: str) -> set:
        s = "".join(c for c in s if c.isalnum())
        return {s[i : i + 2] for i in range(len(s) - 1)}

    ba, bb = bigrams(a), bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def find_duplicate(
    candidate: str,
    existing: Iterable[str],
    threshold: float = 0.9,
) -> str | None:
    """Return the first existing name that duplicates the candidate.

    Two names are considered duplicates when either the slug matches or
    the name similarity exceeds the threshold.
    """
    candidate_slug = slugify(candidate)
    best_match: tuple[str, float] | None = None

    for name in existing:
        if slugify(name) == candidate_slug:
            return name
        similarity = name_similarity(candidate, name)
        if similarity >= threshold:
            if best_match is None or similarity > best_match[1]:
                best_match = (name, similarity)

    if best_match is not None:
        return best_match[0]
    return None


def group_duplicates(
    names: Iterable[str],
    threshold: float = 0.9,
) -> list[list[str]]:
    """Group a list of names into duplicate clusters."""
    clusters: list[list[str]] = []
    for name in names:
        placed = False
        for cluster in clusters:
            if find_duplicate(name, cluster, threshold=threshold) is not None:
                cluster.append(name)
                placed = True
                break
        if not placed:
            clusters.append([name])
    return clusters


__all__ = [
    "find_duplicate",
    "group_duplicates",
    "jaccard",
    "name_similarity",
    "normalize_repo_name",
    "slugify",
]
