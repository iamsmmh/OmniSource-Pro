"""Tests for the source connectors added in Stage 10.

All external HTTP traffic is mocked with respx so tests run offline.
"""

import pytest

from omnisource.connectors.base import ConnectorError
from omnisource.connectors.codeberg import CodebergConnector
from omnisource.connectors.fdroid import FDroidConnector
from omnisource.connectors.flathub import FlathubConnector
from omnisource.connectors.fmhy import FMHYConnector
from omnisource.connectors.fmhy.connector import parse_fmhy_entries
from omnisource.connectors.forgejo import ForgejoConnector
from omnisource.connectors.homebrew import HomebrewConnector
from omnisource.connectors.registry import available_sources, create_connector
from omnisource.connectors.winget import WingetConnector

pytestmark = pytest.mark.asyncio

# --- Shared payloads -----------------------------------------------------------

GITEA_SEARCH = {
    "ok": True,
    "data": [
        {
            "id": 42,
            "owner": {"login": "acme"},
            "name": "widget",
            "full_name": "acme/widget",
            "description": "A widget app",
            "html_url": "https://codeberg.org/acme/widget",
            "website": "https://widget.example.com",
            "stars_count": 120,
            "forks_count": 12,
            "open_issues_count": 3,
            "default_branch": "main",
            "updated_at": "2026-01-15T10:00:00Z",
            "archived": False,
            "fork": False,
            "topics": ["tools"],
        }
    ],
}

GITEA_RELEASES = [
    {
        "id": 7,
        "tag_name": "v1.2.0",
        "name": "Widget 1.2.0",
        "body": "Bug fixes",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-01-10T00:00:00Z",
        "tarball_url": "https://codeberg.org/acme/widget/archive/v1.2.0.tar.gz",
        "assets": [
            {
                "id": 11,
                "name": "widget-linux-amd64",
                "size": 2048,
                "browser_download_url": "https://codeberg.org/acme/widget/releases/download/v1.2.0/widget-linux-amd64",
            }
        ],
    }
]


class TestRegistry:
    def test_all_sources_registered(self):
        sources = available_sources()
        for expected in (
            "github",
            "gitlab",
            "codeberg",
            "forgejo",
            "fdroid",
            "flathub",
            "winget",
            "homebrew",
            "fmhy",
        ):
            assert expected in sources

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="No connector registered"):
            create_connector("doesnotexist")


class TestGiteaFamily:
    async def test_codeberg_discover(self, respx_mock):
        respx_mock.get("https://codeberg.org/api/v1/repos/search").respond(json=GITEA_SEARCH)
        respx_mock.get("https://codeberg.org/api/v1/version").respond(json={"version": "1.23.0"})

        connector = CodebergConnector()
        await connector.initialize()
        try:
            repos, page_info = await connector.discover(limit=50)
            assert len(repos) == 1
            repo = repos[0]
            assert repo.external_id == "42"
            assert repo.full_name == "acme/widget"
            assert repo.stars == 120
            assert repo.source_type == "codeberg"
            assert page_info.has_next is False

            # releases
            respx_mock.get("https://codeberg.org/api/v1/repos/acme/widget/releases").respond(
                json=GITEA_RELEASES
            )
            releases = await connector.get_releases(repo)
            assert releases[0].version == "v1.2.0"
            assert releases[0].status == "released"

            # assets
            assets = await connector.get_assets(releases[0])
            assert assets[0].filename == "widget-linux-amd64"
            assert assets[0].detected_platform == "linux"

            # health
            health = await connector.health_check()
            assert health.healthy is True
        finally:
            await connector.close()

    async def test_forgejo_uses_configured_instance(self, respx_mock):
        respx_mock.get("https://forge.example.com/api/v1/repos/search").respond(
            json={"ok": True, "data": []}
        )
        connector = ForgejoConnector(
            base_url="https://forge.example.com", api_url="https://forge.example.com/api/v1"
        )
        await connector.initialize()
        try:
            repos, page_info = await connector.discover()
            assert repos == []
            assert page_info.has_next is False
        finally:
            await connector.close()

    async def test_get_repository_invalid_id(self):
        connector = CodebergConnector()
        await connector.initialize()
        try:
            with pytest.raises(ConnectorError, match="Invalid repository ID"):
                await connector.get_repository("not-a-slug")
        finally:
            await connector.close()


class TestFDroid:
    async def test_discover_pages_package_list(self, respx_mock):
        respx_mock.get("https://f-droid.org/api/v1/packages").respond(
            json=["org.a.a", "org.b.b", "org.c.c"]
        )
        connector = FDroidConnector(api_url="https://f-droid.org/api/v1")
        await connector.initialize()
        try:
            repos, page_info = await connector.discover(limit=2)
            assert [r.external_id for r in repos] == ["org.a.a", "org.b.b"]
            assert page_info.has_next is True
            assert page_info.next_cursor == "2"

            repos2, _ = await connector.discover(cursor="2", limit=2)
            assert [r.external_id for r in repos2] == ["org.c.c"]
        finally:
            await connector.close()

    async def test_releases_and_assets(self, respx_mock):
        respx_mock.get("https://f-droid.org/api/v1/packages/org.b.b").respond(
            json={
                "packageName": "org.b.b",
                "packages": [
                    {
                        "versionName": "1.0",
                        "versionCode": 100,
                        "minSdkVersion": 21,
                        "lastUpdated": 1735689600000,
                    },
                    {
                        "versionName": "1.1",
                        "versionCode": 101,
                        "minSdkVersion": 21,
                        "lastUpdated": 1736208000000,
                    },
                ],
            }
        )
        connector = FDroidConnector(api_url="https://f-droid.org/api/v1")
        await connector.initialize()
        try:
            repo = await connector.get_repository("org.b.b")
            assert repo.external_id == "org.b.b"

            releases = await connector.get_releases(repo)
            assert len(releases) == 2
            assert releases[-1].version == "1.0"  # reversed: newest first
            assert releases[0].version == "1.1"

            assets = await connector.get_assets(releases[0])
            assert assets[0].filename == "org.b.b_101.apk"
            assert assets[0].detected_platform == "android"
            assert assets[0].download_url == "https://f-droid.org/repo/org.b.b_101.apk"
        finally:
            await connector.close()


class TestFlathub:
    async def test_discover_and_detail(self, respx_mock):
        respx_mock.get("https://flathub.org/api/v1/apps").respond(
            json=[
                {
                    "flatpakAppId": "org.example.App",
                    "name": "Example App",
                    "summary": "An example flatpak",
                    "favorites": 42,
                },
                {
                    "flatpakAppId": "org.other.Thing",
                    "name": "Thing",
                    "summary": "Another",
                },
            ]
        )
        respx_mock.get("https://flathub.org/api/v1/apps/org.example.App").respond(
            json={
                "flatpakAppId": "org.example.App",
                "name": "Example App",
                "summary": "An example flatpak",
                "projectLicense": "GPL-3.0-or-later",
                "homepage": "https://example.com",
                "inStore": True,
            }
        )

        connector = FlathubConnector(api_url="https://flathub.org/api/v1")
        await connector.initialize()
        try:
            repos, page_info = await connector.discover()
            assert page_info.total == 2
            assert repos[0].external_id == "org.example.App"

            filtered, _ = await connector.discover(query="example")
            assert len(filtered) == 1

            repo = await connector.get_repository("org.example.App")
            assert repo.license_spdx == "GPL-3.0-or-later"
            assert repo.homepage == "https://example.com"

            # appstream releases
            respx_mock.get("https://flathub.org/api/v2/appstream/org.example.App").respond(
                json={
                    "releases": [
                        {"version": "2.0.0", "description": "Major release"},
                        {"version": "1.9.1", "description": "Patch"},
                    ]
                }
            )
            releases = await connector.get_releases(repo)
            assert [r.version for r in releases] == ["2.0.0", "1.9.1"]

            assets = await connector.get_assets(releases[0])
            assert assets[0].package_type == "flatpakref"
            assert assets[0].detected_platform == "linux"
        finally:
            await connector.close()


class TestWinget:
    async def test_manifest_flow(self, respx_mock):
        letter_listing = [
            {"type": "dir", "name": "Acme", "path": "manifests/a/Acme"},
            {"type": "file", "name": "README.md", "path": "manifests/a/README.md"},
        ]
        respx_mock.get(
            "https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/a"
        ).respond(json=letter_listing)
        respx_mock.get(
            "https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/a/Acme"
        ).respond(json=[{"type": "dir", "name": "Widget", "path": "manifests/a/Acme/Widget"}])

        connector = WingetConnector()
        await connector.initialize()
        try:
            repos, page_info = await connector.discover(limit=10)
            assert len(repos) == 1
            assert repos[0].external_id == "Widget"
            assert page_info.has_next is True
            assert page_info.next_cursor == "b:0"  # advanced to next letter

            # latest version listing + raw manifest
            respx_mock.get(
                "https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/Widget"
            ).respond(json=[{"type": "dir", "name": "1.0.0", "path": "manifests/w/Widget/1.0.0"}])
            respx_mock.get(
                "https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/w/Widget/1.0.0/Widget.yaml"
            ).respond(
                text=(
                    "PackageIdentifier: Widget\n"
                    "PackageName: Widget\n"
                    "PackageVersion: 1.0.0\n"
                    "Publisher: Acme\n"
                    "ShortDescription: A widget\n"
                    "License: MIT\n"
                    "PackageUrl: https://widget.example.com\n"
                    "Installers:\n"
                    "  - InstallerUrl: https://example.com/widget-1.0.0-x64.msi\n"
                    "    InstallerSha256: ABCDEF123456\n"
                )
            )
            repo = await connector.get_repository("Widget")
            assert repo.name == "Widget"
            assert repo.license_spdx == "MIT"
            assert repo.description == "A widget"

            releases = await connector.get_releases(repo)
            assert releases[0].version == "1.0.0"

            assets = await connector.get_assets(releases[0])
            assert assets[0].filename == "widget-1.0.0-x64.msi"
            assert assets[0].detected_platform == "windows"
            assert assets[0].sha256 == "ABCDEF123456"
        finally:
            await connector.close()


class TestHomebrew:
    async def test_formula_flow(self, respx_mock):
        respx_mock.get("https://formulae.brew.sh/api/formula.json").respond(
            json=[
                {
                    "name": "wget",
                    "desc": "Internet file retriever",
                    "homepage": "https://www.gnu.org/software/wget/",
                    "license": "GPL-3.0-or-later",
                }
            ]
        )
        respx_mock.get("https://formulae.brew.sh/api/cask.json").respond(
            json=[{"token": "firefox", "name": "Firefox", "desc": "Web browser"}]
        )
        respx_mock.get("https://formulae.brew.sh/api/formula/wget.json").respond(
            json={
                "name": "wget",
                "desc": "Internet file retriever",
                "homepage": "https://www.gnu.org/software/wget/",
                "license": "GPL-3.0-or-later",
                "versions": {"stable": "1.21.4"},
                "urls": {"stable": {"url": "https://ftp.gnu.org/wget-1.21.4.tar.gz"}},
                "bottle": {
                    "stable": {
                        "files": {
                            "arm64_sequoia": {
                                "url": "https://ghcr.io/wget-1.21.4.arm64_sequoia.bottle.tar.gz",
                                "sha256": "deadbeef",
                            }
                        }
                    }
                },
            }
        )

        connector = HomebrewConnector()
        await connector.initialize()
        try:
            repos, page_info = await connector.discover()
            assert page_info.total == 2
            assert repos[0].external_id == "wget"

            repo = await connector.get_repository("wget")
            assert repo.license_spdx == "GPL-3.0-or-later"

            releases = await connector.get_releases(repo)
            assert releases[0].version == "1.21.4"

            assets = await connector.get_assets(releases[0])
            kinds = {a.filename for a in assets}
            assert any("bottle.tar.gz" in f for f in kinds)
            assert any("wget-1.21.4.tar.gz" in f for f in kinds)
        finally:
            await connector.close()

    async def test_cask_license_clause_list(self):
        connector = HomebrewConnector()
        spdx = connector._license_to_spdx([{"all_of": ["MIT", "Apache-2.0"]}])
        assert spdx == "MIT OR Apache-2.0"
        assert connector._license_to_spdx("MIT") == "MIT"
        assert connector._license_to_spdx(None) is None


# --- FMHY (freemediaheckyeah) ---------------------------------------------------
#
# VitePress-rendered slice of https://fmhy.net/mobile covering both platform
# parts. Markup mirrors the live site build: a plain-HTML document-title
# <h1> ("Android / iOS"), platform sections rendered as <h2> (the wiki's h1
# sections are shifted one level down by VitePress), subsections as <h3>,
# icon-only reference anchors (Telegram/Discord links render without text),
# a page-outline aside with fragment links, header nav, emoji bullets, and a
# zero-width word joiner (U+2060) in one label.

FMHY_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Android / iOS • freemediaheckyeah</title></head>
<body>
<header><nav><ul>
  <li><a href="https://fmhy.net/streaming">Streaming</a></li>
  <li><a href="https://fmhy.net/music">Music</a></li>
</ul></nav></header>
<main class="main">
<div class="vp-doc _mobile">
<div class="space-y-2 not-prose">
  <h1 class="text-4xl font-extrabold tracking-tight text-primary">Android / iOS</h1>
  <p class="text-black dark:text-text-2">Apps, Jailbreaking, Android Emulators</p>
</div>
<hr />
<h2 id="android-apks" tabindex="-1">
  <a class="header-anchor" href="#android-apks" aria-label="Permalink to &quot;Android APKs&quot;">#</a>
  &#9658; Android APKs
</h2>
<h3 id="modded-apks" tabindex="-1">
  <a class="header-anchor" href="#modded-apks">#</a>
  &#9658; Modded APKs
</h3>
<ul>
  <li><a href="https://play.google.com/store/apps/details?id=brave">Brave</a> - Adblock Browser / <a target="_blank" href="https://discord.gg/abc"><span class="i-carbon:logo-discord"></span></a></li>
  <li><strong><a href="https://github.com/mihonapp/mihon">Mihon</a></strong> - Manga Reader</li>
  <li>Prose tip with no links at all</li>
</ul>
<h2 id="emulators" tabindex="-1">
  <a class="header-anchor" href="#emulators">#</a>
  &#9658; Emulators
</h2>
<ul>
  <li class="starred">\u2b50 <strong><a href="https://termux.dev/">Termux</a></strong> - Terminal Emulator</li>
</ul>
<h2 id="ios-tools" tabindex="-1">
  <a class="header-anchor" href="#ios-tools">#</a>
  &#9658; iOS Tools
</h2>
<ul>
  <li><a href="https://apps.apple.com/app/id1234">Brave</a> - Adblock Browser</li>
  <li><a href="https://play.google.com/store/apps/details?id=weird">WeirdOne</a> - Store Link In iOS Zone</li>
  <li><a href="#ios-ipas">Outline Entry</a> - Page Outline Link</li>
</ul>
<h2 id="ios-ipas" tabindex="-1">
  <a class="header-anchor" href="#ios-ipas">#</a>
  &#9658; iOS iPAs
</h2>
<ul>
  <li>\U0001f310 <strong><a href="https://ipa.cypwn.xyz/">CyPwn</a></strong> - Tweaked App Library / <a href="https://ipa.cypwn.xyz/cypwn.json">AltStore</a></li>
  <li>\u2b50 <strong>PDALife</strong> - <a href="https://pdalife.com/ios/games">Games</a> / <a href="https://pdalife.com/ios/programmy/">Apps</a> / <a target="_blank" href="https://t.me/pdalife_official"><span class="i-mdi:telegram"></span></a></li>
  <li><a href="https://ipalibrary.me/">IPALibrary</a> - Tweaked Apps / Use Safari to Translate</li>
  <li><a href="https://fastsign.dev/">\u2060Alan's Gigantic Repo</a> - Tweaked App Library / <a target="_blank" href="https://discord.gg/UAYA4ZuKXD"><span class="i-carbon:logo-discord"></span></a></li>
</ul>
<h3 id="telegram-channels-1" tabindex="-1">
  <a class="header-anchor" href="#telegram-channels-1">#</a>
  &#9658; Telegram Channels
</h3>
<ul>
  <li class="starred">\u2b50 <strong><a href="https://blatants.fyi/">Blatant's IPA Library</a></strong>, <a href="https://t.me/blatants">2</a> - Tweaked Apps / <a target="_blank" href="https://t.me/blatantbruh"><span class="i-mdi:telegram"></span></a></li>
  <li><a href="https://github.com/Lessica/TrollRecorder">TrollRecorder</a> - Call Recorder / <strong>Check Local Call Recording Laws</strong></li>
</ul>
</div>
</main>
<aside class="aside"><nav class="table-of-styles"><ul>
  <li><a href="#android-apks">Android APKs</a></li>
  <li><a href="#ios-ipas">iOS iPAs</a></li>
</ul></nav></aside>
</body>
</html>
"""

# (name, url, platform, description) in document order.
FMHY_PAGE_EXPECTED = [
    ("Brave", "https://play.google.com/store/apps/details?id=brave", "android", "Adblock Browser"),
    ("Mihon", "https://github.com/mihonapp/mihon", "android", "Manga Reader"),
    ("Termux", "https://termux.dev/", "android", "Terminal Emulator"),
    ("Brave", "https://apps.apple.com/app/id1234", "ios", "Adblock Browser"),
    # Play Store link inside the iOS zone: the store URL wins.
    (
        "WeirdOne",
        "https://play.google.com/store/apps/details?id=weird",
        "android",
        "Store Link In iOS Zone",
    ),
    ("CyPwn", "https://ipa.cypwn.xyz/", "ios", "Tweaked App Library"),
    ("PDALife", "https://pdalife.com/ios/games", "ios", ""),
    ("IPALibrary", "https://ipalibrary.me/", "ios", "Tweaked Apps / Use Safari to Translate"),
    ("Alan's Gigantic Repo", "https://fastsign.dev/", "ios", "Tweaked App Library"),
    ("Blatant's IPA Library", "https://blatants.fyi/", "ios", "Tweaked Apps"),
    # A trailing bold note is part of the description, never the label.
    (
        "TrollRecorder",
        "https://github.com/Lessica/TrollRecorder",
        "ios",
        "Call Recorder / Check Local Call Recording Laws",
    ),
]


class TestFMHY:
    def test_parser_tracks_platform_zones(self):
        entries = parse_fmhy_entries(FMHY_PAGE_HTML)
        actual = [(e["name"], e["url"], e["platform"], e["description"]) for e in entries]
        assert actual == FMHY_PAGE_EXPECTED

    def test_parser_ignores_chrome_and_unresolvable_entries(self):
        names = {e["name"] for e in parse_fmhy_entries(FMHY_PAGE_HTML)}
        # Header nav (before any zone), page outline (fragment links), and
        # prose lines are not applications.
        assert "Streaming" not in names
        assert "Music" not in names
        assert "Outline Entry" not in names
        # Emphasized label without a link falls back to the first real link.
        pdalife = next(e for e in parse_fmhy_entries(FMHY_PAGE_HTML) if e["name"] == "PDALife")
        assert pdalife["url"] == "https://pdalife.com/ios/games"
        # Zero-width word joiner is stripped from the name.
        assert "Alan's Gigantic Repo" in names
        # Icon-only reference anchors (Telegram/Discord) never hijack the
        # primary link or the description.
        brave = next(e for e in parse_fmhy_entries(FMHY_PAGE_HTML) if e["name"] == "Brave")
        assert brave["description"] == "Adblock Browser"

    def test_parser_empty_page(self):
        assert parse_fmhy_entries("") == []
        assert parse_fmhy_entries("<html><body><p>no sections</p></body></html>") == []

    async def test_discover(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_PAGE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            repos, page_info = await connector.discover(limit=100)
            assert page_info.total == len(FMHY_PAGE_EXPECTED)
            assert page_info.has_next is False
            assert page_info.next_cursor is None

            by_id = {r.external_id: r for r in repos}
            # Same name on both platforms -> platform-suffixed external ids.
            assert by_id["brave-android"].name == "Brave"
            assert (
                by_id["brave-android"].html_url
                == "https://play.google.com/store/apps/details?id=brave"
            )
            assert by_id["brave-android"].topics == ["android"]
            assert by_id["brave-ios"].html_url == "https://apps.apple.com/app/id1234"
            assert by_id["brave-ios"].topics == ["ios"]
            # Store URL in the iOS zone is tagged android.
            assert by_id["weirdone"].topics == ["android"]
            # Unique names keep plain slugs.
            cypwn = by_id["cypwn"]
            assert cypwn.full_name == "fmhy/cypwn"
            assert cypwn.homepage == "https://ipa.cypwn.xyz/"
            assert cypwn.description == "Tweaked App Library"
            assert cypwn.source_type == "fmhy"
            pdalife = by_id["pdalife"]
            assert pdalife.description is None
        finally:
            await connector.close()

    async def test_discover_pagination(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_PAGE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            first, page1 = await connector.discover(limit=4)
            assert len(first) == 4
            assert page1.has_next is True
            assert page1.next_cursor == "4"

            second, page2 = await connector.discover(limit=4, cursor="4")
            assert len(second) == 4
            assert page2.next_cursor == "8"
            assert page2.has_previous is True

            last, page_last = await connector.discover(limit=4, cursor="8")
            assert len(last) == 3
            assert page_last.has_next is False
            assert page_last.next_cursor is None

            # No entry appears on two pages.
            seen = (
                [r.external_id for r in first]
                + [r.external_id for r in second]
                + [r.external_id for r in last]
            )
            assert len(seen) == len(set(seen)) == len(FMHY_PAGE_EXPECTED)
        finally:
            await connector.close()

    async def test_discover_query_filter(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_PAGE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            repos, _ = await connector.discover(limit=100, query="manga")
            assert [r.name for r in repos] == ["Mihon"]
            tweaked, _ = await connector.discover(limit=100, query="tweaked")
            assert {r.name for r in tweaked} == {
                "CyPwn",
                "IPALibrary",
                "Alan's Gigantic Repo",
                "Blatant's IPA Library",
            }
        finally:
            await connector.close()

    async def test_get_repository(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_PAGE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            by_external = await connector.get_repository("cypwn")
            assert by_external.name == "CyPwn"
            by_full_name = await connector.get_repository("fmhy/brave-ios")
            assert by_full_name.external_id == "brave-ios"
            by_name = await connector.get_repository("PDALife")
            assert by_name.html_url == "https://pdalife.com/ios/games"

            with pytest.raises(ConnectorError, match="not found"):
                await connector.get_repository("does-not-exist")
        finally:
            await connector.close()

    async def test_releases_assets_and_metadata(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_PAGE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            repo = await connector.get_repository("cypwn")
            assert await connector.get_releases(repo) == []
            assert await connector.get_assets(repo) == []
            metadata = await connector.get_metadata(repo)
            assert metadata["source"] == "fmhy"
            assert metadata["platforms"] == ["ios"]
            assert metadata["topics"] == ["ios"]

            android_repo = await connector.get_repository("brave-android")
            android_meta = await connector.get_metadata(android_repo)
            assert android_meta["platforms"] == ["android"]
        finally:
            await connector.close()

    async def test_health_check(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_PAGE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            health = await connector.health_check()
            assert health.healthy is True
            assert health.latency_ms is not None

            respx_mock.get("https://fmhy.net/mobile").respond(status_code=500)
            health = await connector.health_check()
            assert health.healthy is False
        finally:
            await connector.close()

    async def test_discover_raises_when_page_unavailable(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(status_code=404)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            with pytest.raises(ConnectorError, match="unavailable"):
                await connector.discover()
        finally:
            await connector.close()
