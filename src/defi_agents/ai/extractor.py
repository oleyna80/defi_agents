from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import EXTRACTOR_VERSION, MAX_RESPONSE_BYTES
from ..scout.models import ReasonCode

try:
    import dns.resolver  # type: ignore
except Exception:  # noqa: BLE001
    dns = None  # type: ignore[assignment]


DENY_NETWORKS: tuple[ipaddress._BaseNetwork, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


class ExtractionError(RuntimeError):
    def __init__(self, reason_code: ReasonCode, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass
class ExtractionResult:
    text: str
    source: str
    reason_code: ReasonCode | None
    content_hash: str


@dataclass
class _FetchResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    url: str


class ContentExtractor:
    JINA_PREFIX = "https://r.jina.ai/"
    EXTRACTOR_VERSION = EXTRACTOR_VERSION

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_redirects: int = 5,
        max_chars: int = 25_000,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_redirects = max_redirects
        self.max_chars = max_chars
        self.max_response_bytes = max_response_bytes

    async def extract(self, url: str | None) -> ExtractionResult:
        if not url:
            return self._empty_result(ReasonCode.NO_DATA)

        stripped = url.strip()
        if stripped.lower().endswith(".pdf"):
            return self._empty_result(ReasonCode.PDF_UNSUPPORTED)

        try:
            self._validate_url(stripped)
        except ExtractionError as exc:
            return self._empty_result(exc.reason_code)

        try:
            text = await self._fetch_via_jina(stripped)
            if text:
                return self._result(text=text, source="jina", reason_code=None)
        except ExtractionError as exc:
            if exc.reason_code == ReasonCode.SSRF_BLOCKED:
                return self._empty_result(ReasonCode.SSRF_BLOCKED)
        except Exception:  # noqa: BLE001
            pass

        try:
            text = await self._fetch_direct(stripped)
            if text:
                return self._result(text=text, source="fallback_http", reason_code=None)
        except ExtractionError as exc:
            return self._empty_result(exc.reason_code)
        except Exception:  # noqa: BLE001
            return self._empty_result(ReasonCode.EXTRACTION_FAILED)

        return self._empty_result(ReasonCode.EXTRACTION_FAILED)

    async def _fetch_via_jina(self, url: str) -> str:
        jina_url = f"{self.JINA_PREFIX}{url}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
            response = await self._request_once(client, jina_url)
        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" in content_type:
            raise ExtractionError(ReasonCode.PDF_UNSUPPORTED, "PDF content type is unsupported")
        text = response.body.decode("utf-8", errors="ignore")
        return self._sanitize_text(text)

    async def _fetch_direct(self, url: str) -> str:
        response = await self._fetch_with_redirect_checks(url)
        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" in content_type:
            raise ExtractionError(ReasonCode.PDF_UNSUPPORTED, "PDF content type is unsupported")
        raw = response.body.decode("utf-8", errors="ignore")
        return self._sanitize_text(raw)

    async def _fetch_with_redirect_checks(self, url: str) -> _FetchResponse:
        current = url
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
            for _ in range(self.max_redirects + 1):
                # TOCTOU guard: validate current URL immediately before each fetch.
                self._validate_url(current)
                response = await self._request_once(client, current)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ExtractionError(ReasonCode.EXTRACTION_FAILED, "Redirect without Location")
                    current = urljoin(current, location)
                    continue
                return response
        raise ExtractionError(ReasonCode.EXTRACTION_FAILED, "Too many redirects")

    async def _request_once(self, client: httpx.AsyncClient, url: str) -> _FetchResponse:
        body = bytearray()
        async with client.stream("GET", url, follow_redirects=False) as response:
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    raise ExtractionError(
                        ReasonCode.EXTRACTION_FAILED,
                        f"Response exceeded limit ({self.max_response_bytes} bytes)",
                    )
            headers = {k.lower(): v for k, v in response.headers.items()}
            return _FetchResponse(
                status_code=response.status_code,
                headers=headers,
                body=bytes(body),
                url=str(response.url),
            )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ExtractionError(ReasonCode.SSRF_BLOCKED, "Only http/https schemes are allowed")

        host = parsed.hostname
        if not host:
            raise ExtractionError(ReasonCode.SSRF_BLOCKED, "Host is required")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in {80, 443}:
            raise ExtractionError(ReasonCode.SSRF_BLOCKED, f"Port {port} is blocked")

        if host.lower() in {"localhost", "localhost.localdomain"}:
            raise ExtractionError(ReasonCode.SSRF_BLOCKED, "localhost is blocked")

        ips = self._resolve_ips(host)
        if not ips:
            raise ExtractionError(ReasonCode.EXTRACTION_FAILED, "Could not resolve host")
        for ip in ips:
            if self._is_blocked_ip(ip):
                raise ExtractionError(ReasonCode.SSRF_BLOCKED, f"Blocked target IP: {ip}")

    def _resolve_ips(self, host: str) -> set[str]:
        resolved: set[str] = set()

        if dns is not None:
            try:
                for rr in dns.resolver.resolve(host, "A"):
                    resolved.add(rr.to_text())
            except Exception:  # noqa: BLE001
                pass
            try:
                for rr in dns.resolver.resolve(host, "AAAA"):
                    resolved.add(rr.to_text())
            except Exception:  # noqa: BLE001
                pass

        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            for info in infos:
                sockaddr = info[4]
                if sockaddr:
                    resolved.add(sockaddr[0])
        except socket.gaierror:
            pass

        return resolved

    def _is_blocked_ip(self, ip_raw: str) -> bool:
        ip_obj = ipaddress.ip_address(ip_raw)
        return any(ip_obj in network for network in DENY_NETWORKS)

    def _sanitize_text(self, text: str) -> str:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        plain = soup.get_text(" ", strip=True)
        plain = re.sub(r"\s+", " ", plain)
        # Remove common prompt-injection directives from source text.
        plain = re.sub(
            r"ignore (all|any|the) (previous|prior) instructions",
            "",
            plain,
            flags=re.IGNORECASE,
        )
        if len(plain) > self.max_chars:
            plain = plain[: self.max_chars]
        return plain.strip()

    def _result(self, *, text: str, source: str, reason_code: ReasonCode | None) -> ExtractionResult:
        content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        return ExtractionResult(text=text, source=source, reason_code=reason_code, content_hash=content_hash)

    def _empty_result(self, reason_code: ReasonCode) -> ExtractionResult:
        return ExtractionResult(
            text="",
            source="none",
            reason_code=reason_code,
            content_hash=hashlib.sha256(b"").hexdigest(),
        )
