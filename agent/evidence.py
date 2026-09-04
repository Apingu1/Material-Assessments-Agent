from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pymupdf
from PIL import Image
from playwright.sync_api import sync_playwright

from .config import Settings
from .curation import evidence_key
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


class EvidenceCaptureError(RuntimeError):
    pass


def _safe_slug(value: str, max_len: int = 80) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (value or "source")[:max_len]


def unique_sources(sources: list[EvidenceSource]) -> list[EvidenceSource]:
    seen: set[str] = set()
    result: list[EvidenceSource] = []
    for source in sources:
        key = evidence_key(source)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _normalise(value: str) -> str:
    value = value.lower().replace("µ", "u")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _keywords(value: str) -> set[str]:
    stop = {
        "about", "after", "before", "document", "evidence", "official", "report",
        "source", "tablets", "tablet", "monograph", "public", "assessment", "finding",
        "with", "from", "that", "this", "were", "was", "have", "has", "into", "than",
        "according", "provides", "showed", "shows", "using", "used",
    }
    return {token for token in _normalise(value).split() if len(token) >= 4 and token not in stop}


def _page_matches_source(body_text: str, source: EvidenceSource) -> bool:
    body_norm = _normalise(body_text)
    quote_norm = _normalise(source.relevant_extract)
    if quote_norm and quote_norm in body_norm:
        return True
    quote_words = _keywords(source.relevant_extract)
    if not quote_words:
        return False
    body_words = set(body_norm.split())
    overlap = len(quote_words & body_words) / len(quote_words)
    return overlap >= 0.58


def _looks_blocked_or_broken(status: int | None, body_text: str) -> bool:
    if status is not None and status >= 400:
        return True
    body = _normalise(body_text)
    blocked_markers = (
        "403 forbidden", "access denied", "request blocked", "robot check", "captcha",
        "oops we couldn t find the page", "page not found", "404 not found",
    )
    return any(marker in body for marker in blocked_markers)


def _pubmed_fallback_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "pubmed.ncbi.nlm.nih.gov" not in parsed.netloc.lower():
        return None
    match = re.search(r"/(\d+)/?", parsed.path)
    if not match:
        return None
    pmid = match.group(1)
    return (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={pmid}&rettype=abstract&retmode=text"
    )


def _friendly_capture_error(exc: Exception) -> str:
    text = str(exc)
    lower = text.lower()
    if "libatk-1.0.so.0" in lower or "error while loading shared libraries" in lower:
        return "Chromium system dependencies are missing. Run: playwright install --with-deps chromium"
    if "blocked" in lower or "forbidden" in lower or "403" in lower:
        return "Source blocked automated capture. URL retained in evidence metadata."
    if "404" in lower or "not found" in lower or "broken" in lower:
        return "Source link returned a missing/broken page. URL retained in evidence metadata."
    if "relevant evidence text" in lower:
        return "The source opened, but the relevant evidence text could not be verified on the rendered page."
    if "timeout" in lower:
        return "Automated webpage capture timed out. URL retained in evidence metadata."
    if "target page, context or browser has been closed" in lower:
        return "Chromium could not start or closed unexpectedly. URL retained in evidence metadata."
    return "Automated webpage capture failed. URL retained in evidence metadata."


class EvidenceCollector:
    def __init__(self, settings: Settings):
        self.settings = settings

    def capture_group(
        self,
        group: str,
        appendix_number: int,
        sources: list[EvidenceSource],
        evidence_dir: Path,
        max_successful: int | None = None,
    ) -> list[EvidenceCapture]:
        """Capture only verified evidence. Failed attempts remain in diagnostics, not the dossier."""
        evidence_dir.mkdir(parents=True, exist_ok=True)
        captures: list[EvidenceCapture] = []
        appendix_index = 1
        for source in unique_sources(sources):
            suffix = chr(64 + appendix_index) if appendix_index <= 26 else str(appendix_index)
            label = f"{appendix_number}{suffix}"
            capture = self.capture_source(source, group, label, evidence_dir)
            if capture.capture_status != "CAPTURED" or not capture.capture_path:
                continue
            captures.append(capture)
            appendix_index += 1
            if max_successful is not None and len(captures) >= max_successful:
                break
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
            if pdf_capture is not None:
                capture_path, original_path, note = pdf_capture
                status = "CAPTURED" if capture_path else "FAILED"
                return EvidenceCapture(
                    source, group, appendix_label, capture_path, original_path, status, note
                )
        except Exception as exc:
            self._write_diagnostic(evidence_dir, stem, source.url, "PDF", exc)

        try:
            capture_path = self._capture_html(source, evidence_dir, stem)
            return EvidenceCapture(
                source,
                group,
                appendix_label,
                capture_path,
                None,
                "CAPTURED",
                "Verified relevant webpage evidence captured",
            )
        except Exception as exc:
            self._write_diagnostic(evidence_dir, stem, source.url, "BROWSER", exc)
            return EvidenceCapture(
                source,
                group,
                appendix_label,
                None,
                None,
                "FAILED",
                _friendly_capture_error(exc),
            )

    def _write_diagnostic(
        self, evidence_dir: Path, stem: str, url: str, stage: str, exc: Exception
    ) -> None:
        path = evidence_dir / f"{stem}-{stage}-DIAGNOSTIC.txt"
        path.write_text(f"URL: {url}\nStage: {stage}\n\n{exc}\n", encoding="utf-8")

    def _try_pdf(
        self, source: EvidenceSource, evidence_dir: Path, stem: str
    ) -> tuple[Path | None, Path, str] | None:
        parsed = urlparse(source.url)
        if parsed.scheme not in {"http", "https"}:
            return None
        headers = {"User-Agent": "Mozilla/5.0 MaterialAssessmentAgent/0.3"}
        with httpx.Client(follow_redirects=True, timeout=25, headers=headers) as client:
            response = client.get(source.url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        looks_pdf = "application/pdf" in content_type or response.content[:5] == b"%PDF-"
        if not looks_pdf:
            return None

        pdf_path = evidence_dir / f"{stem}.pdf"
        pdf_path.write_bytes(response.content)
        doc = pymupdf.open(stream=response.content, filetype="pdf")
        try:
            page_index = self._find_relevant_pdf_page(doc, source)
            if page_index is None:
                return (
                    None,
                    pdf_path,
                    "PDF downloaded, but the relevant evidence page could not be located automatically.",
                )

            page = doc[page_index]
            quote = source.relevant_extract.strip()
            rects = page.search_for(quote) if quote else []
            if not rects and quote:
                for fragment in self._search_fragments(quote):
                    rects = page.search_for(fragment)
                    if rects:
                        break
            for rect in rects:
                annot = page.add_highlight_annot(rect)
                annot.update()

            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
            image_path = evidence_dir / f"{stem}.png"
            pix.save(str(image_path))
            return image_path, pdf_path, f"Relevant PDF page {page_index + 1} captured"
        finally:
            doc.close()

    def _find_relevant_pdf_page(self, doc, source: EvidenceSource) -> int | None:
        quote_norm = _normalise(source.relevant_extract)
        quote_words = _keywords(source.relevant_extract)
        title_words = _keywords(source.title)
        best_index: int | None = None
        best_score = 0.0

        for idx, page in enumerate(doc):
            text = page.get_text("text") or ""
            norm = _normalise(text)
            if not norm:
                continue
            words = set(norm.split())
            score = 0.0
            if quote_norm and quote_norm in norm:
                score += 6.0
            if quote_words:
                score += 3.0 * (len(quote_words & words) / len(quote_words))
            if title_words:
                score += 2.0 * (len(title_words & words) / len(title_words))
            if score > best_score:
                best_index, best_score = idx, score

        return best_index if best_score >= 2.2 else None

    def _search_fragments(self, quote: str) -> list[str]:
        words = quote.split()
        fragments: list[str] = []
        for size in (10, 8, 6, 4):
            if len(words) >= size:
                for start in range(0, len(words) - size + 1, max(1, size // 2)):
                    fragments.append(" ".join(words[start : start + size]).strip("\"'.,;:"))
        return fragments[:16]

    def _navigate_verified(self, page, url: str, source: EvidenceSource) -> str:
        response = page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        status = response.status if response is not None else None
        body_text = page.locator("body").inner_text(timeout=self.settings.playwright_timeout_ms)
        if _looks_blocked_or_broken(status, body_text):
            raise EvidenceCaptureError(f"Source blocked or broken (HTTP {status or 'unknown'}).")
        if not _page_matches_source(body_text, source):
            raise EvidenceCaptureError("Relevant evidence text was not located on rendered page.")
        return body_text

    def _scroll_to_relevant(self, page, source: EvidenceSource) -> None:
        candidates = [source.relevant_extract.strip(), *self._search_fragments(source.relevant_extract)]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                locator = page.get_by_text(candidate, exact=False).first
                if locator.count() > 0:
                    locator.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    def _capture_html(self, source: EvidenceSource, evidence_dir: Path, stem: str) -> Path:
        image_path = evidence_dir / f"{stem}.jpg"
        fallback_url = _pubmed_fallback_url(source.url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1100}, ignore_https_errors=True
                )
                page = context.new_page()
                page.set_default_timeout(self.settings.playwright_timeout_ms)
                try:
                    try:
                        self._navigate_verified(page, source.url, source)
                    except EvidenceCaptureError:
                        if not fallback_url:
                            raise
                        self._navigate_verified(page, fallback_url, source)

                    self._scroll_to_relevant(page, source)
                    page.screenshot(path=str(image_path), full_page=False, type="jpeg", quality=86)
                finally:
                    context.close()
            finally:
                browser.close()

        with Image.open(image_path) as image:
            if image.width > 1800:
                ratio = 1800 / image.width
                image = image.resize((1800, int(image.height * ratio)))
                image.save(image_path, quality=86)
        return image_path
