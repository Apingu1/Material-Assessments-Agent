from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import fitz
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
    attempts: list[dict[str, str]] = field(default_factory=list)
    identity_match: str = ""


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (value or "SDS")[:90]


def _looks_pdf(content: bytes, content_type: str) -> bool:
    return "application/pdf" in (content_type or "").lower() or content[:5] == b"%PDF-"


def _pdf_links(html: str, base_url: str) -> list[str]:
    # SDS pages frequently place the download in an iframe, embedded PDF viewer
    # or data-href rather than an ordinary anchor link.
    links = re.findall(
        r'(?:href|src|data-href|data-url)\s*=\s*["\']([^"\']+)["\']',
        html, flags=re.IGNORECASE,
    )
    absolute: list[str] = []
    seen: set[str] = set()
    for href in links:
        url = urljoin(base_url, href.strip())
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        text = url.lower()
        if not any(word in text for word in (".pdf", "sds", "msds", "safety-data", "safety_data")):
            continue
        if url in seen:
            continue
        seen.add(url)
        absolute.append(url)

    return sorted(
        absolute,
        key=lambda url: (
            0 if any(term in url.lower() for term in ("sds", "msds", "safety-data")) else 1,
            0 if ".pdf" in url.lower() else 1,
        ),
    )[:10]


def _clean_substance(value: str) -> str:
    """Drop the incoming presentation, dose or route; preserve salts/hydrates."""
    value = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|%)\b", " ", value or "", flags=re.I)
    value = re.sub(
        r"\b(powder|tablets?|capsules?|granules?|oral|solution|suspension|for injection|"
        r"active pharmaceutical ingredient|api)\b", " ", value, flags=re.I,
    )
    return re.sub(r"\s+", " ", value).strip(" ,;-").lower()


def sds_search_names(material_name: str, chemical_identity: str = "", active_moiety: str = "") -> list[str]:
    """SDS is identified by the chemical, not the dosage form or administration route."""
    names = [_clean_substance(x) for x in (chemical_identity, material_name, active_moiety)]
    result = list(dict.fromkeys(x for x in names if x))
    return result


def known_authoritative_sds_urls(names: list[str]) -> list[str]:
    """Direct document URLs verified from official publisher catalogues.

    Registry is deliberately small: never generate guessed regulator PDF URLs.
    """
    if any(re.search(r"\blevomepromazine(?:\s+maleate)?\b", name, re.I) for name in names):
        return [
            "https://www.pharmacopoeia.com/content/file/products/healthandsafety/CAT-723_GB.pdf",
            "https://www.pharmacopoeia.tso.co.uk/content/file/products/healthandsafety/CAT-723_GB.pdf",
        ]
    return []


def _candidate_urls(research: COSHHResearch, extra_urls: list[str] | None = None) -> list[str]:
    urls = [research.sds.url, research.sds.source.url, *(extra_urls or [])]
    for source in research.sources:
        label = f"{source.title} {source.url}".lower()
        if any(term in label for term in ("sds", "msds", "safety data sheet", "safety-data")):
            urls.append(source.url)
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        url = (url or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result[:12]


def _valid_sds_pdf(
    content: bytes, substance: str, cas_number: str,
    acceptable_names: list[str] | None = None,
) -> tuple[bool, str]:
    """Check retrieved bytes really contain a readable, identity-relevant SDS.

    This is a download integrity guard, NOT a regulatory verification or
    substitute for checking the supplier, revision and hazard classification.
    """
    if not content.startswith(b"%PDF-"):
        return False, "Downloaded content was not a PDF"
    try:
        with fitz.open(stream=content, filetype="pdf") as pdf:
            text = " ".join(page.get_text() for page in list(pdf)[:6])
    except Exception:
        return False, "Downloaded PDF could not be read"
    normal = re.sub(r"\s+", " ", text).lower()
    if not re.search(r"(material )?safety data sheet|safety information sheet", normal):
        return False, "PDF did not contain identifiable Safety Data Sheet text"
    names = [_clean_substance(substance), *[_clean_substance(x) for x in (acceptable_names or [])]]
    names = list(dict.fromkeys(x for x in names if x))
    cas_found = bool(cas_number and re.search(r"(?<!\d)" + re.escape(cas_number) + r"(?!\d)", normal))
    exact = next((name for name in names if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", normal)), "")
    if not cas_found and not exact:
        return False, "PDF text did not match the selected substance, acceptable name or CAS"
    # A CAS match or exact salt-name match has strongest identity support.
    return True, "CAS_MATCH" if cas_found else ("NAME_MATCH:" + exact)


class SDSStore:
    """Search candidate URLs and download an original, unmodified SDS PDF.

    Records every failed attempt. Alternate-source research is orchestrated by
    AssessmentPipeline; this class performs deterministic URL/link recovery.
    """

    def __init__(self, timeout_seconds: int = 25):
        self.timeout_seconds = timeout_seconds

    def acquire(
        self,
        research: COSHHResearch,
        material_dir: Path,
        *,
        previous_attempts: list[dict[str, str]] | None = None,
        extra_urls: list[str] | None = None,
        acceptable_names: list[str] | None = None,
    ) -> StoredSDS:
        sds_dir = material_dir / "sds"
        sds_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = sds_dir / "SDS_METADATA.json"
        urls = _candidate_urls(research, extra_urls=extra_urls)
        attempts = list(previous_attempts or [])
        result = StoredSDS(
            status="NOT_AVAILABLE",
            original_url=urls[0] if urls else "",
            resolved_pdf_url="",
            local_path="",
            sha256="",
            note="No downloadable, identity-matched SDS PDF found; supplier SDS requires manual verification.",
            attempts=attempts,
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept": "application/pdf,text/html,*/*",
        }
        with httpx.Client(follow_redirects=True, timeout=self.timeout_seconds, headers=headers) as client:
            seen_urls: set[str] = {entry.get("url", "") for entry in attempts}
            for source_url in urls:
                if source_url in seen_urls:
                    continue
                try:
                    response = client.get(source_url)
                    response.raise_for_status()
                    candidates = [response]
                    if not _looks_pdf(response.content, response.headers.get("content-type", "")):
                        candidates = []
                        for link in _pdf_links(response.text, str(response.url)):
                            if link in seen_urls:
                                continue
                            try:
                                linked = client.get(link, headers={"Referer": str(response.url)})
                                linked.raise_for_status()
                                candidates.append(linked)
                            except httpx.HTTPError as exc:
                                attempts.append({"url": link, "result": type(exc).__name__})
                                seen_urls.add(link)
                    if not candidates:
                        attempts.append({"url": source_url, "result": "No linked PDF found"})
                    for candidate in candidates:
                        pdf_url = str(candidate.url)
                        valid, reason = _valid_sds_pdf(
                            candidate.content, research.sds.substance_name or research.coshh_substance_name,
                            research.sds.cas_number, acceptable_names=acceptable_names,
                        )
                        if not valid:
                            attempts.append({"url": pdf_url, "result": reason})
                            continue
                        filename = f"{_slug(research.coshh_substance_name)} - Safety Data Sheet.pdf"
                        path = sds_dir / filename
                        path.write_bytes(candidate.content)  # Preserve original bytes, never modify the SDS.
                        attempts.append({"url": pdf_url, "result": "STORED_UNCHANGED"})
                        result = StoredSDS(
                            status="STORED_UNCHANGED",
                            original_url=source_url,
                            resolved_pdf_url=pdf_url,
                            local_path=str(path),
                            sha256=hashlib.sha256(candidate.content).hexdigest(),
                            note="Original readable SDS PDF stored byte-for-byte unchanged; supplier/revision requires human verification.",
                            attempts=attempts,
                            identity_match=reason,
                        )
                        break
                    if result.status == "STORED_UNCHANGED":
                        break
                except httpx.HTTPError as exc:
                    attempts.append({"url": source_url, "result": type(exc).__name__})
                except Exception as exc:
                    attempts.append({"url": source_url, "result": type(exc).__name__})
                seen_urls.add(source_url)
        self.write_metadata(result, research, material_dir)
        return result

    @staticmethod
    def write_metadata(result: StoredSDS, research: COSHHResearch, material_dir: Path) -> None:
        metadata_path = material_dir / "sds" / "SDS_METADATA.json"
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
