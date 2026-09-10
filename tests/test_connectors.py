"""Tests for the source connectors added in Stage 10.

All external HTTP traffic is mocked with respx so tests run offline.
"""

import pytest

from omnisource.connectors.base import ConnectorError
from omnisource.connectors.codeberg import CodebergConnector
from omnisource.connectors.fdroid import FDroidConnector
from omnisource.connectors.flathub import FlathubConnector
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
