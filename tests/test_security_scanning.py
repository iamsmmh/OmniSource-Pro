"""Tests for OSV vulnerability scanning and asset integrity verification."""

import pytest

from omnisource.processing.validation.integrity import (
    evaluate_asset_integrity,
    find_signature_companion,
    parse_checksum_file,
    verify_against_checksum_file,
)
from omnisource.processing.validation.osv import query_batch, worst_severity
from omnisource.processing.validation.security import SecurityScanner

pytestmark = pytest.mark.asyncio


D_APPIMAGE = "0a1b2c3d" * 8  # 64 hex chars
D_DMG = "e5f6a7b8" * 8
D_EXE = "11223344556677889900aabbccddeeff" * 2

SHA256SUMS = f"""# comment line
{D_APPIMAGE}  localsend-1.0.AppImage
{D_DMG} *localsend-1.0.dmg
SHA256 (localsend-1.0.exe) = {D_EXE}
"""


class TestChecksumFiles:
    def test_parse_gnu_style(self):
        parsed = parse_checksum_file("0a1b2c3d4e5f6789  file.tar.gz\n0a1b2c3d4e5f6788 *file.zip\n")
        assert parsed == {"file.tar.gz": "0a1b2c3d4e5f6789", "file.zip": "0a1b2c3d4e5f6788"}

    def test_parse_bsd_style(self):
        parsed = parse_checksum_file("SHA256 (app) = abcdef\n")
        assert parsed == {"app": "abcdef"}

    def test_parse_skips_comments_and_blank(self):
        digest = "ab" * 32
        parsed = parse_checksum_file(f"# header\n\n   \n{digest}  x.bin\n")
        assert parsed == {"x.bin": digest}

    def test_verify_match(self):
        verdict = verify_against_checksum_file(
            "localsend-1.0.AppImage", D_APPIMAGE.upper(), SHA256SUMS
        )
        assert verdict["verified"] is True

    def test_verify_mismatch(self):
        other = "deadbeef" * 8
        verdict = verify_against_checksum_file("localsend-1.0.dmg", other, SHA256SUMS)
        assert verdict["verified"] is False
        assert verdict["reason"] == "checksum_mismatch"

    def test_verify_no_entry(self):
        verdict = verify_against_checksum_file("unknown.bin", "deadbeef" * 8, SHA256SUMS)
        assert verdict["verified"] is None


class TestSignatures:
    def test_find_companion(self):
        companions = find_signature_companion(["app.dmg", "app.dmg.sig", "other.zip"])
        assert companions["app.dmg"] == "app.dmg.sig"
        assert companions["other.zip"] is None

    def test_evaluate_verified_and_signed(self):
        digest = "cd" * 32
        result = evaluate_asset_integrity(
            filename="app.AppImage",
            actual_sha256=digest,
            checksum_file_content=f"{digest}  app.AppImage\n",
            companion_assets=["app.AppImage.sig"],
        )
        assert result["status"] == "verified"
        assert result["signed"] is True

    def test_evaluate_failed_mismatch_short_circuits(self):
        result = evaluate_asset_integrity(
            filename="app.dmg",
            actual_sha256="bad" * 22,  # 66 chars, valid shape but wrong value
            checksum_file_content=f"{'00' * 32}  app.dmg\n",
            companion_assets=["app.dmg.asc"],
        )
        assert result["status"] == "failed"

    def test_evaluate_unverified_without_evidence(self):
        result = evaluate_asset_integrity(filename="app.zip", actual_sha256=None)
        assert result["status"] == "unverified"


class TestOSV:
    async def test_query_batch_ok(self, respx_mock):
        respx_mock.post("https://api.osv.dev/v1/querybatch").respond(
            json={
                "results": [
                    {"vulns": [{"id": "GHSA-xxxx", "modified": "2026-01-01"}]},
                    {},
                ]
            }
        )
        result = await query_batch(
            [
                {"name": "requests", "ecosystem": "pypi", "version": "2.25.1"},
                {"name": "left-pad", "ecosystem": "npm"},
            ]
        )
        assert result["status"] == "ok"
        assert result["results"][0][0]["id"] == "GHSA-xxxx"
        assert result["results"][1] == []

    async def test_query_batch_network_error_degrades(self, respx_mock):
        import httpx

        respx_mock.post("https://api.osv.dev/v1/querybatch").mock(
            side_effect=httpx.ConnectError("boom")
        )
        result = await query_batch([{"name": "x", "ecosystem": "npm"}])
        assert result["status"] == "error"
        assert "error" in result

    async def test_query_batch_empty(self):
        result = await query_batch([])
        assert result == {"status": "ok", "results": []}

    def test_worst_severity_prefers_critical(self):
        assert (
            worst_severity({"database_specific": {"severity": "MODERATE"}, "severity": []})
            == "moderate"
        )
        assert (
            worst_severity(
                {
                    "database_specific": {"severity": "LOW"},
                    "severity": [{"score": "CVSS:3.1/AV:N", "type": "CVSS_V3"}],
                }
            )
            == "high"
        )
        assert worst_severity({}) is None


class TestScannerVulnerabilities:
    async def test_scan_vulnerabilities_flags_high_risk(self, respx_mock):
        respx_mock.post("https://api.osv.dev/v1/querybatch").respond(
            json={"results": [{"vulns": [{"id": "GHSA-high"}]}]}
        )
        respx_mock.get("https://api.osv.dev/v1/vulns/GHSA-high").respond(
            json={"id": "GHSA-high", "database_specific": {"severity": "CRITICAL"}}
        )
        scanner = SecurityScanner()
        result = await scanner.scan_vulnerabilities(
            [{"name": "openssl", "ecosystem": "linux", "version": "1.1.1"}]
        )
        assert result["scan_type"] == "osv"
        assert result["scan_status"] == "flagged"
        assert result["quarantine"] is True
        assert result["vulnerabilities"][0]["severity"] == "critical"

    async def test_scan_vulnerabilities_pass_when_clean(self, respx_mock):
        respx_mock.post("https://api.osv.dev/v1/querybatch").respond(json={"results": [{}]})
        scanner = SecurityScanner()
        result = await scanner.scan_vulnerabilities([{"name": "zlib", "ecosystem": "linux"}])
        assert result["scan_status"] == "passed_vulnerability_scan"
        assert result["quarantine"] is False

    async def test_scan_vulnerabilities_unavailable_service(self, respx_mock):
        import httpx

        respx_mock.post("https://api.osv.dev/v1/querybatch").mock(
            side_effect=httpx.ConnectError("down")
        )
        scanner = SecurityScanner()
        result = await scanner.scan_vulnerabilities([{"name": "x", "ecosystem": "npm"}])
        assert result["scan_status"] == "unavailable"
        assert result["vulnerabilities"] == []
