from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .models import COSHHResearch


@dataclass
class StoredSDS:
    status: str
    original_url: str
    resolved_pdf_url: str
    local_path: str
    sha256: str
    note: str


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (value or "SDS")[:90]


def _looks_pdf(content: bytes, content_type: str) -> bool:
    return "application/pdf" in (content_type or "").lower() or content[:5] == b"%PDF-"


def _pdf_links(html: str, base_url: str) -> list[str]:
    links = re.findall(r"href\s*=\s*[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    absolute: list[str] = []
    seen: set[str] = set()
    for href in links:
        url = urljoin(base_url, href.strip())
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        text = url.lower()
        if not (".pdf" in text or "sds" in text or "msds" in text or "safety-data" in text):
            continue
        if url in seen:
            continue
        seen.add(url)
        absolute.append(url)

    def rank(url: str) -> tuple[int, int]:
        text = url.lower()
        return (
            0 if ("sds" in text or "msds" in text or "safety-data" in text) else 1,
            0 if ".pdf" in text else 1,
        )

    return sorted(absolute, key=rank)[:8]


class SDSStore:
    """Best-effort downloader that preserves the selected SDS PDF bytes unchanged."""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def acquire(self, research: COSHHResearch, material_dir: Path) -> StoredSDS:
        sds_dir = material_dir / "sds"
        sds_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = sds_dir / "SDS_METADATA.json"
        source_url = research.sds.url.strip() or research.sds.source.url.strip()
        result = StoredSDS(
            status="NOT_AVAILABLE",
            original_url=source_url,
            resolved_pdf_url="",
            local_path="",
            sha256="",
            note="Original SDS PDF could not be downloaded automatically; use the recorded source URL during review.",
        )

        if not source_url:
            metadata_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
            return result

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
        }

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self.timeout_seconds,
                headers=headers,
            ) as client:
                response = client.get(source_url)
                response.raise_for_status()
                pdf_bytes: bytes | None = None
                pdf_url = str(response.url)
                if _looks_pdf(response.content, response.headers.get("content-type", "")):
                    pdf_bytes = response.content
                else:
                    html = response.text
                    for candidate in _pdf_links(html, str(response.url)):
                        try:
                            candidate_response = client.get(candidate, referer=str(response.url))
                            candidate_response.raise_for_status()
                        except Exception:
                            continue
                        if _looks_pdf(
                            candidate_response.content,
                            candidate_response.headers.get("content-type", ""),
                        ):
                            pdf_bytes = candidate_response.content
                            pdf_url = str(candidate_response.url)
                            break

                if pdf_bytes is not None:
                    filename = f"{_slug(research.coshh_substance_name)} - Safety Data Sheet.pdf"
                    path = sds_dir / filename
                    # The SDS is deliberately not rendered, merged, annotated or rewritten.
                    path.write_bytes(pdf_bytes)
                    digest = hashlib.sha256(pdf_bytes).hexdigest()
                    result = StoredSDS(
                        status="STORED_UNCHANGED",
                        original_url=source_url,
                        resolved_pdf_url=pdf_url,
                        local_path=str(path),
                        sha256=digest,
                        note="Original SDS PDF stored byte-for-byte unchanged.",
                    )
        except Exception as exc:
            result.note = f"Automatic SDS download failed: {type(exc).__name__}. Source URL retained for review."

        payload = {
            **asdict(result),
            "substance_name": research.sds.substance_name,
            "cas_number": research.sds.cas_number,
            "manufacturer": research.sds.manufacturer,
            "product_name": research.sds.product_name,
            "product_number": research.sds.product_number,
            "revision_date": research.sds.revision_date,
            "match_status": research.sds.match_status,
            "match_rationale": research.sds.match_rationale,
            "is_supplier_specific": research.sds.is_supplier_specific,
        }
        metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return result
