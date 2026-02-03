import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.ai.extractor import ContentExtractor, ExtractionError
from defi_agents.scout.models import ReasonCode


class _Resp:
    def __init__(self, status_code: int, headers: dict[str, str], body: bytes, url: str):
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.url = url


def _run(coro):
    return asyncio.run(coro)


def test_ssrf_blocks_private_ipv4():
    extractor = ContentExtractor()
    for url in (
        "http://127.0.0.1/admin",
        "http://192.168.1.1",
        "http://10.0.0.5",
    ):
        try:
            extractor._validate_url(url)
            assert False, f"Expected SSRF block for {url}"
        except ExtractionError as exc:
            assert exc.reason_code == ReasonCode.SSRF_BLOCKED


def test_ssrf_blocks_ipv6_local():
    extractor = ContentExtractor()
    for url in ("http://[::1]/secret", "http://[fc00::1]/secret"):
        try:
            extractor._validate_url(url)
            assert False, f"Expected SSRF block for {url}"
        except ExtractionError as exc:
            assert exc.reason_code == ReasonCode.SSRF_BLOCKED


def test_ssrf_blocks_cloud_metadata():
    extractor = ContentExtractor()
    try:
        extractor._validate_url("http://169.254.169.254/latest/meta-data/")
        assert False, "Expected SSRF block for cloud metadata endpoint"
    except ExtractionError as exc:
        assert exc.reason_code == ReasonCode.SSRF_BLOCKED


def test_redirect_attack_blocked_on_hop(monkeypatch):
    extractor = ContentExtractor()

    def fake_resolve(host: str) -> set[str]:
        if host == "malicious.com":
            return {"93.184.216.34"}
        if host == "127.0.0.1":
            return {"127.0.0.1"}
        return {"93.184.216.34"}

    async def fake_request_once(self, client, url):  # noqa: ANN001
        if "malicious.com" in url:
            return _Resp(302, {"location": "http://127.0.0.1/config"}, b"", url)
        return _Resp(200, {"content-type": "text/html"}, b"<html>ok</html>", url)

    monkeypatch.setattr(ContentExtractor, "_resolve_ips", staticmethod(fake_resolve))
    monkeypatch.setattr(ContentExtractor, "_request_once", fake_request_once)

    try:
        _run(extractor._fetch_with_redirect_checks("http://malicious.com/redirect"))
        assert False, "Expected redirect hop to be blocked by SSRF checks"
    except ExtractionError as exc:
        assert exc.reason_code == ReasonCode.SSRF_BLOCKED


def test_dns_rebinding_guard_revalidates_each_hop(monkeypatch):
    extractor = ContentExtractor()
    calls: list[str] = []

    def fake_resolve(host: str) -> set[str]:
        calls.append(host)
        return {"93.184.216.34"}

    async def fake_request_once(self, client, url):  # noqa: ANN001
        if "a.test" in url:
            return _Resp(302, {"location": "http://b.test/final"}, b"", url)
        return _Resp(200, {"content-type": "text/html"}, b"<html>ok</html>", url)

    monkeypatch.setattr(ContentExtractor, "_resolve_ips", staticmethod(fake_resolve))
    monkeypatch.setattr(ContentExtractor, "_request_once", fake_request_once)

    result = _run(extractor._fetch_with_redirect_checks("http://a.test/start"))
    assert result.status_code == 200
    assert calls == ["a.test", "b.test"]
