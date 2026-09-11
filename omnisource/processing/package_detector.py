"""Detect package ecosystems and dependency manifests from repository content."""

from collections.abc import Iterable

_MANIFEST_ECOSYSTEMS = {
    "package.json": "npm",
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "npm",
    "yarn.lock": "npm",
    "pyproject.toml": "pypi",
    "requirements.txt": "pypi",
    "poetry.lock": "pypi",
    "pipfile": "pypi",
    "go.mod": "go",
    "cargo.toml": "crates.io",
    "gemfile": "rubygems",
    "composer.json": "packagist",
    "pom.xml": "maven",
    "build.gradle": "maven",
    "build.gradle.kts": "maven",
    "*.csproj": "nuget",
    "pubspec.yaml": "pub",
    "mix.exs": "hex",
    "flatpak.json": "flatpak",
    "flatpak.yaml": "flatpak",
}


def detect_package_ecosystems(filenames: Iterable[str], readme: str | None = None) -> list[str]:
    """Return deterministic package ecosystems inferred from manifest filenames."""
    detected: set[str] = set()
    for filename in filenames:
        normalized = filename.rsplit("/", 1)[-1].lower()
        if normalized.endswith(".csproj"):
            detected.add("nuget")
        elif ecosystem := _MANIFEST_ECOSYSTEMS.get(normalized):
            detected.add(ecosystem)
    text = (readme or "").lower()
    hints = {
        "flatpak": "flatpak",
        "f-droid": "fdroid",
        "homebrew": "homebrew",
        "winget": "winget",
        "docker": "docker",
    }
    detected.update(ecosystem for hint, ecosystem in hints.items() if hint in text)
    return sorted(detected)


__all__ = ["detect_package_ecosystems"]
