"""Application categorization engine."""

from typing import Dict, List, Optional, Set

from omnisource.core.models.category import CategoryType, TAXONOMY

# Keyword -> category type mapping for topic/description classification.
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    CategoryType.AUDIO.value: ["audio", "music", "sound", "podcast", "mp3", "audio-player", "equalizer"],
    CategoryType.VIDEO.value: ["video", "movie", "player", "streaming", "video-editor", "transcode"],
    CategoryType.PHOTOGRAPHY.value: ["photo", "image", "camera", "picture", "raw", "gallery"],
    CategoryType.GRAPHICS.value: ["graphics", "design", "draw", "vector", "illustration", "3d", "cad", "render"],
    CategoryType.PRODUCTIVITY.value: ["productivity", "todo", "notes", "office", "calendar", "spreadsheet", "task"],
    CategoryType.DEVELOPER_TOOLS.value: ["developer", "programming", "code", "ide", "compiler", "debugger", "linter", "cli", "sdk", "api", "git"],
    CategoryType.EDUCATION.value: ["education", "learning", "course", "tutorial", "flashcard", "language-learning"],
    CategoryType.COMMUNICATION.value: ["communication", "chat", "messaging", "email", "im", "voip", "telegram", "matrix"],
    CategoryType.SOCIAL.value: ["social", "network", "fediverse", "mastodon", "community", "forum"],
    CategoryType.INTERNET.value: ["internet", "web", "http", "download", "rss", "sync"],
    CategoryType.BROWSERS.value: ["browser", "chromium", "firefox", "webview"],
    CategoryType.SECURITY.value: ["security", "privacy", "encryption", "password", "vpn", "firewall", "antivirus", "2fa"],
    CategoryType.NETWORKING.value: ["network", "networking", "proxy", "dns", "ssh", "ftp", "monitor", "traffic"],
    CategoryType.UTILITIES.value: ["utility", "tool", "launcher", "clipboard", "file-manager", "backup", "automation"],
    CategoryType.GAMING.value: ["game", "gaming", "emulator", "retro", "godot", "chess"],
    CategoryType.BOOKS.value: ["book", "ebook", "reader", "library", "epub", "pdf", "literature"],
    CategoryType.FINANCE.value: ["finance", "budget", "banking", "crypto", "bitcoin", "accounting", "invoice"],
    CategoryType.SCIENCE.value: ["science", "math", "physics", "chemistry", "statistics", "calculator", "research"],
    CategoryType.SYSTEM_TOOLS.value: ["system", "kernel", "driver", "terminal", "shell", "process", "monitor", "package-manager"],
    CategoryType.AI.value: ["ai", "machine-learning", "llm", "gpt", "neural", "ml", "artificial-intelligence", "chatbot", "diffusion"],
}


def categorize(
    topics: Optional[List[str]] = None,
    description: Optional[str] = None,
    languages: Optional[List[str]] = None,
    max_categories: int = 3,
) -> List[str]:
    """Classify an application into one or more category types.

    Scores candidate categories by keyword matches across topics,
    description, and languages. Returns category type strings.
    """
    text_parts: List[str] = []
    text_parts.extend(t.strip().lower() for t in (topics or []))
    if description:
        text_parts.append(description.lower())
    text_parts.extend(str(l).lower() for l in (languages or []))

    haystack = " ".join(text_parts)
    scores: Dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in haystack:
                score += 1
        if score:
            scores[category] = score

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    result = [category for category, _ in ranked[:max_categories]]

    if not result:
        result = [CategoryType.OTHER.value]

    return result


def category_name(category_type: str) -> str:
    """Return a human-readable name for a category type."""
    try:
        return TAXONOMY[CategoryType(category_type)]["name"]
    except (KeyError, ValueError):
        return category_type


__all__ = ["categorize", "category_name"]
