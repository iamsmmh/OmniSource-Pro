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
# VitePress-rendered slice of https://fmhy.net/mobile around the "iOS iPAs"
# section. Markup mirrors the live site: perma-link anchors inside headings,
# emoji bullets, ``<strong>``-emphasized primary links, and a zero-width word
# joiner (U+2060) in one label.

FMHY_MOBILE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Android / iOS</title></head>
<body>
<main class="main">
<div class="vp-doc _mobile">
<h1 id="ios-privacy" tabindex="-1">
  <a class="header-anchor" href="#ios-privacy" aria-label="Permalink to &quot;iOS Privacy&quot;">#</a>
  &#9658; iOS Privacy
</h1>
<ul>
  <li><a href="https://onionbrowser.com/">Onion Browser</a> - Tor-Based Browser</li>
</ul>
<hr />
<h1 id="ios-ipas" tabindex="-1">
  <a class="header-anchor" href="#ios-ipas" aria-label="Permalink to &quot;iOS iPAs&quot;">#</a>
  &#9658; iOS iPAs
</h1>
<ul>
  <li>\U0001f310 <strong><a href="https://ipa.cypwn.xyz/">CyPwn</a></strong> - Tweaked App Library / <a href="https://ipa.cypwn.xyz/cypwn.json">AltStore</a> / <a href="https://telegram.me/cypwngroup">Telegram</a> / <a href="https://discord.com/invite/UvHZz3HfN9">Discord</a></li>
  <li>\U0001f310 <strong><a href="https://github.com/dkhamsing/open-source-ios-apps">Open-Source iOS Apps</a></strong> - Open-Source Apps</li>
  <li>\U0001f310 <strong><a href="https://github.com/pluwen/awesome-testflight-link">Awesome TestFlight</a></strong>, <a href="https://departures.to/">Departures</a> or <a href="https://docs.google.com/spreadsheets/d/1Uej3AQPxRcLRXnmthUXR-7oGkNV_GsMFgCoNnuPtSwI/">TestFlight Spreadsheet</a> - TestFlight App Indexes</li>
  <li>\U0001f310 <strong><a href="https://appstoretracker.com/">App Store Tracker</a></strong> - App Store Analytics / Tracker </li>
  <li>\U0001f310 <strong><a href="https://www.reddit.com/r/EmulationOniOS/wiki/emulators">iOS Console Emulators</a></strong> - Gaming Emulator Index</li>
  <li>\u2b50 <strong>PDALife</strong> - <a href="https://pdalife.com/ios/games">Games</a> / <a href="https://pdalife.com/ios/programmy/">Apps</a> / <a href="https://t.me/pdalife_official">Telegram</a></li>
  <li><a href="https://ipalibrary.me/">IPALibrary</a> - Tweaked Apps / Use Safari to Translate</li>
  <li><a href="https://4pda.to/forum/">4PDA</a> - Tweaked Apps / Use Safari to Translate / <a href="https://github.com/fmhy/edit/blob/main/docs/.vitepress/notes/captcha-4pda.md">Captcha Note</a></li>
  <li><a href="https://appdb.to">AppDB</a> - App Library</li>
  <li><a href="https://iosvizor.com/">iOSVizor</a> - Tweaked Apps / <a href="https://t.me/iosvizor">Telegram</a></li>
  <li><a href="https://raw.githubusercontent.com/driftywinds/driftywinds.github.io/master/AltStore/apps.json">DriftyWinds</a> - AltStore App Source</li>
  <li><a href="https://fastsign.dev/">\u2060Alan's Gigantic Repo</a> - Tweaked App Library / <a href="https://discord.gg/UAYA4ZuKXD">Discord</a></li>
  <li><a href="https://fnd.io/">fnd</a> - App Store Search</li>
  <li><a href="https://github.com/Neoncat-OG/TrollStore-IPAs">TrollStore-IPAs</a> - Tweaked Apps</li>
  <li><a href="https://rentry.co/FMHYB64#moes-app">Moe's App Hub</a> - Tweaked Apps</li>
  <li><a href="https://platinmods.com/">PlatinMods</a> - Tweaked Apps / Requires Sign-Up</li>
  <li><a href="https://repository.apptesters.org/">AppTesters</a> - Tweaked Apps / <a href="https://t.me/AppleTesters">Telegram</a></li>
  <li><a href="https://stuffed18.github.io/ipa-archive-updated">IPA Archive</a> - Search Engine</li>
  <li><a href="https://archive.org/details/iOSObscura">iOSObscura</a> - Old App Archive / <a href="https://iphoneosobscura.litten.ca/">Search Engine</a></li>
  <li><a href="https://applecensorship.com/">AppleCensorship</a> - Censored App Store Apps</li>
  <li><a href="https://github.com/majd/ipatool">IPATool</a> - Search / Download App Packages</li>
  <li><a href="https://armconverter.com/decryptedappstore">Decrypted App Store</a>, <a href="https://decrypt.34306.lol/">unfaird</a> or <a href="https://anyipa.me/">AnyIPA</a> / <a href="https://t.me/AnyIPAme">Telegram</a> / <a href="https://discord.gg/c233DYUzsw">Discord</a> - Decrypted iOS Apps</li>
</ul>
<hr />
<h2 id="telegram-channels-1" tabindex="-1">
  <a class="header-anchor" href="#telegram-channels-1" aria-label="Permalink to &quot;Telegram Channels&quot;">#</a>
  &#9658; Telegram Channels
</h2>
<ul>
  <li>\u2b50 <strong><a href="https://blatants.fyi/">Blatant's IPA Library</a></strong>, <a href="https://t.me/blatants">2</a> - Tweaked Apps / <a href="https://t.me/blatantbruh">Telegram</a> </li>
</ul>
</div>
</main>
</body>
</html>
"""

FMHY_SECTION_NAMES = {
    "CyPwn",
    "Open-Source iOS Apps",
    "Awesome TestFlight",
    "App Store Tracker",
    "iOS Console Emulators",
    "PDALife",
    "IPALibrary",
    "4PDA",
    "AppDB",
    "iOSVizor",
    "DriftyWinds",
    "Alan's Gigantic Repo",
    "fnd",
    "TrollStore-IPAs",
    "Moe's App Hub",
    "PlatinMods",
    "AppTesters",
    "IPA Archive",
    "iOSObscura",
    "AppleCensorship",
    "IPATool",
    "Decrypted App Store",
}


class TestFMHY:
    def test_parser_extracts_only_ios_ipas_section(self):
        entries = parse_fmhy_entries(FMHY_MOBILE_HTML)
        assert {e["name"] for e in entries} == FMHY_SECTION_NAMES
        by_name = {e["name"]: e for e in entries}
        # Emphasized label with primary link + stripped reference links.
        assert by_name["CyPwn"]["url"] == "https://ipa.cypwn.xyz/"
        assert by_name["CyPwn"]["description"] == "Tweaked App Library"
        # Emphasized label without a link falls back to the first link.
        assert by_name["PDALife"]["url"] == "https://pdalife.com/ios/games"
        assert by_name["PDALife"]["description"] == ""
        # Zero-width word joiner is stripped from the name.
        assert by_name["Alan's Gigantic Repo"]["url"] == "https://fastsign.dev/"
        # Entries outside the section (iOS Privacy, Telegram Channels) are excluded.
        assert "Onion Browser" not in by_name
        assert "Blatant's IPA Library" not in by_name

    async def test_discover(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_MOBILE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            repos, page_info = await connector.discover(limit=100)
            assert page_info.total == len(FMHY_SECTION_NAMES)
            assert page_info.has_next is False
            assert page_info.next_cursor is None
            assert {r.name for r in repos} == FMHY_SECTION_NAMES

            cypwn = next(r for r in repos if r.name == "CyPwn")
            assert cypwn.external_id == "cypwn"
            assert cypwn.full_name == "fmhy/cypwn"
            assert cypwn.homepage == "https://ipa.cypwn.xyz/"
            assert cypwn.description == "Tweaked App Library"
            assert cypwn.source_type == "fmhy"

            pdalife = next(r for r in repos if r.name == "PDALife")
            assert pdalife.html_url == "https://pdalife.com/ios/games"
            assert pdalife.description is None
        finally:
            await connector.close()

    async def test_discover_pagination(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_MOBILE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            first, page1 = await connector.discover(limit=5)
            assert len(first) == 5
            assert page1.has_next is True
            assert page1.next_cursor == "5"

            second, page2 = await connector.discover(limit=5, cursor="5")
            assert len(second) == 5
            assert {r.name for r in first} & {r.name for r in second} == set()
            assert page2.next_cursor == "10"
            assert page2.has_previous is True

            last, page_last = await connector.discover(limit=5, cursor=str(20))
            assert len(last) == 2
            assert page_last.has_next is False
            assert page_last.next_cursor is None
        finally:
            await connector.close()

    async def test_discover_query_filter(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_MOBILE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            repos, _ = await connector.discover(limit=100, query="trollstore")
            assert [r.name for r in repos] == ["TrollStore-IPAs"]
        finally:
            await connector.close()

    async def test_get_repository(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_MOBILE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            by_external = await connector.get_repository("cypwn")
            assert by_external.name == "CyPwn"
            by_full_name = await connector.get_repository("fmhy/cypwn")
            assert by_full_name.external_id == "cypwn"
            by_name = await connector.get_repository("PDALife")
            assert by_name.html_url == "https://pdalife.com/ios/games"

            with pytest.raises(ConnectorError, match="not found"):
                await connector.get_repository("does-not-exist")
        finally:
            await connector.close()

    async def test_releases_assets_and_metadata(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_MOBILE_HTML)

        connector = FMHYConnector()
        await connector.initialize()
        try:
            repo = await connector.get_repository("cypwn")
            assert await connector.get_releases(repo) == []
            assert await connector.get_assets(repo) == []
            metadata = await connector.get_metadata(repo)
            assert metadata["source"] == "fmhy"
            assert "ios-ipas" in metadata["topics"]
        finally:
            await connector.close()

    async def test_health_check(self, respx_mock):
        respx_mock.get("https://fmhy.net/mobile").respond(html=FMHY_MOBILE_HTML)

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
