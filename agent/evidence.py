from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import fitz
import httpx
from PIL import Image
from playwright.sync_api import sync_playwright

from .config import Settings
from .models import EvidenceSource


@dataclass
class EvidenceCapture:
    source: EvidenceSource
    group: str
    appendix_label: str
    capture_path: Path | None
    original_path: Path | None
    capture_status: str
    capture_note: str


def _safe_slug(value: str, max_len: int = 80) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (value or "source")[:max_len]


def _source_key(source: EvidenceSource) -> str:
    return f"{source.url}|{source.relevant_extract}".lower().strip()


def unique_sources(sources: list[EvidenceSource]) -> list[EvidenceSource]:
    seen: set[str] = set()
    result: list[EvidenceSource] = []
    for source in sources:
        key = _source_key(source)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


class EvidenceCollector:
    def __init__(self, settings: Settings):
        self.settings = settings

    def capture_group(
        self,
        group: str,
        appendix_number: int,
        sources: list[EvidenceSource],
        evidence_dir: Path,
    ) -> list[EvidenceCapture]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        captures: list[EvidenceCapture] = []
        for idx, source in enumerate(unique_sources(sources), start=1):
            suffix = chr(64 + idx) if idx <= 26 else str(idx)
            label = f"{appendix_number}{suffix}"
            captures.append(self.capture_source(source, group, label, evidence_dir))
        return captures

    def capture_source(
        self,
        source: EvidenceSource,
        group: str,
        appendix_label: str,
        evidence_dir: Path,
    ) -> EvidenceCapture:
        stem = f"Appendix-{appendix_label}-{_safe_slug(source.publisher or source.title)}"
        metadata_path = evidence_dir / f"{stem}.json"
        metadata_path.write_text(
            json.dumps(source.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if not self.settings.capture_evidence:
            return EvidenceCapture(
                source, group, appendix_label, None, None, "METADATA_ONLY", "Capture disabled"
            )

        try:
            pdf_capture = self._try_pdf(source, evidence_dir, stem)
            if pdf_capture:
                capture_path, original_path, note = pdf_capture
                return EvidenceCapture(
                    source, group, appendix_label, capture_path, original_path, "CAPTURED", note
                )
        except Exception as exc:
            pdf_error = f"PDF capture attempt failed: {exc}"
        else:
            pdf_error = ""

        try:
            capture_path = self._capture_html(source, evidence_dir, stem)
            return EvidenceCapture(
                source, group, appendix_label, capture_path, None, "CAPTURED", "Browser evidence screenshot captured"
            )
        except Exception as exc:
            note = "; ".join(x for x in [pdf_error, f"Browser capture failed: {exc}"] if x)
            (evidence_dir / f"{stem}-CAPTURE-FAILED.txt").write_text(
                f"URL: {source.url}\nReason: {note}\n", encoding="utf-8"
            )
            return EvidenceCapture(source, group, appendix_label, None, None, "FAILED", note)

    def _try_pdf(
        self, source: EvidenceSource, evidence_dir: Path, stem: str
    ) -> tuple[Path, Path, str] | None:
        parsed = urlparse(source.url)
        if parsed.scheme not in {"http", "https"}:
            return None
        headers = {"User-Agent": "Mozilla/5.0 MaterialAssessmentAgent/0.1"}
        with httpx.Client(follow_redirects=True, timeout=20, headers=headers) as client:
            response = client.get(source.url)
        content_type = response.headers.get("content-type", "").lower()
        looks_pdf = "application/pdf" in content_type or response.content[:5] == b"%PDF-"
        if not looks_pdf:
            return None

        pdf_path = evidence_dir / f"{stem}.pdf"
        pdf_path.write_bytes(response.content)
        doc = fitz.open(stream=response.content, filetype="pdf")
        page_index = 0
        found_rects = []
        quote = source.relevant_extract.strip()
        if quote:
            for idx, page in enumerate(doc):
                rects = page.search_for(quote)
                if rects:
                    page_index = idx
                    found_rects = rects
                    break
        page = doc[page_index]
        for rect in found_rects:
            annot = page.add_highlight_annot(rect)
            annot.update()
        pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        image_path = evidence_dir / f"{stem}.png"
        pix.save(str(image_path))
        doc.close()
        return image_path, pdf_path, f"PDF page {page_index + 1} captured"

    def _capture_html(self, source: EvidenceSource, evidence_dir: Path, stem: str) -> Path:
        image_path = evidence_dir / f"{stem}.jpg"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, ignore_https_errors=True)
            page = context.new_page()
            page.set_default_timeout(self.settings.playwright_timeout_ms)
            page.goto(source.url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)

            quote = source.relevant_extract.strip()
            if quote:
                try:
                    locator = page.get_by_text(quote, exact=False).first
                    if locator.count() > 0:
                        locator.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            page.screenshot(path=str(image_path), full_page=False, type="jpeg", quality=82)
            context.close()
            browser.close()

        with Image.open(image_path) as image:
            if image.width > 1800:
                ratio = 1800 / image.width
                image = image.resize((1800, int(image.height * ratio)))
                image.save(image_path, quality=82)
        return image_path
