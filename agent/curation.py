from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import (
    Conclusion,
    EvidenceApplicability,
    EvidenceSource,
    HazardEvidenceStatus,
    HazardResearch,
    SourceType,
)


_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
_UK_MARKERS = (
    "bnf.nice.org.uk", "nice.org.uk", "medicines.org.uk", "gov.uk", "mhra",
    "british pharmacopoeia", "bp 202", "hpra.ie",
)
_SOURCE_TYPE_ORDER = {
    SourceType.REGULATORY: 0,
    SourceType.CLINICAL: 1,
    SourceType.PHARMACOPOEIAL: 2,
    SourceType.OFFICIAL_DATABASE: 3,
    SourceType.PEER_REVIEWED: 4,
    SourceType.MANUFACTURER: 5,
    SourceType.SECONDARY: 6,
    SourceType.OTHER: 7,
}


def _normalise(value: str) -> str:
    value = value.lower().replace("µ", "u")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def canonical_url(url: str) -> str:
    """Normalise a URL so one source document is physically appended only once."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def evidence_key(source: EvidenceSource) -> str:
    """Document-level key used for cross-group appendix deduplication."""
    return canonical_url(source.url)


def _is_uk(source: EvidenceSource) -> bool:
    raw = f"{source.title} {source.publisher} {source.url}".lower()
    return any(marker in raw for marker in _UK_MARKERS)


def _base_rank(source: EvidenceSource) -> tuple[int, int, int]:
    return (source.tier, 0 if _is_uk(source) else 1, _SOURCE_TYPE_ORDER.get(source.source_type, 9))


def _merge_lines(first: str, second: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for raw in (first, second):
        for line in str(raw or "").splitlines():
            line = " ".join(line.split()).strip()
            if not line:
                continue
            key = _normalise(line)
            if key in seen:
                continue
            seen.add(key)
            values.append(line)
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "\n".join(f"• {value.lstrip('• ').strip()}" for value in values)


def merge_evidence_sources(primary: EvidenceSource, secondary: EvidenceSource) -> EvidenceSource:
    """Merge different relevant findings from the same source document without duplicating it."""
    preferred = min((primary, secondary), key=_base_rank)
    applicability: list[EvidenceApplicability] = []
    for tag in [*primary.applicability, *secondary.applicability]:
        if tag not in applicability:
            applicability.append(tag)
    return EvidenceSource(
        title=preferred.title,
        publisher=preferred.publisher,
        url=preferred.url,
        tier=min(primary.tier, secondary.tier),
        source_type=preferred.source_type,
        relevant_extract=_merge_lines(primary.relevant_extract, secondary.relevant_extract),
        interpretation=_merge_lines(primary.interpretation, secondary.interpretation),
        applicability=applicability,
    )


def _merge_by_document(sources: list[EvidenceSource]) -> list[EvidenceSource]:
    merged: dict[str, EvidenceSource] = {}
    order: list[str] = []
    for source in sources:
        key = evidence_key(source)
        if key not in merged:
            merged[key] = source
            order.append(key)
        else:
            merged[key] = merge_evidence_sources(merged[key], source)
    return [merged[key] for key in order]


def _applicability_rank(source: EvidenceSource, group: str) -> int:
    tags = set(source.applicability)
    if group == "Potency":
        if EvidenceApplicability.ACTIVE_MOIETY in tags or EvidenceApplicability.CLINICAL_FORMULATION in tags:
            return 0
        if EvidenceApplicability.EXACT_MATERIAL in tags:
            return 1
        return 2
    if group in {"Water Solubility", "70% IPA Solubility", "2% Decon Solubility"}:
        if EvidenceApplicability.CHEMICAL_SPECIES in tags:
            return 0
        if EvidenceApplicability.ACTIVE_MOIETY in tags:
            return 1
        if EvidenceApplicability.EXACT_MATERIAL in tags:
            return 2
        return 3
    if group == "Physical Cleanability":
        if EvidenceApplicability.PROCESS_CONTEXT in tags:
            return 0
        if EvidenceApplicability.EXACT_MATERIAL in tags:
            return 1
        return 2
    return 1


def _hazard_applicability_rank(source: EvidenceSource) -> int:
    tags = set(source.applicability)
    if EvidenceApplicability.CHEMICAL_SPECIES in tags:
        return 0
    if EvidenceApplicability.ACTIVE_MOIETY in tags:
        return 1
    if EvidenceApplicability.EXACT_MATERIAL in tags:
        return 2
    return 3


def _group_directness(source: EvidenceSource, group: str) -> int:
    text = _normalise(f"{source.title} {source.relevant_extract} {source.interpretation}")
    if group == "Potency":
        if "bnf" in text or "nice" in text or "bnf.nice.org.uk" in source.url.lower():
            return 0
        if "smpc" in source.title.lower() or "medicines.org.uk" in source.url.lower():
            return 1
        return 2
    if group == "Water Solubility":
        return 0 if "water" in text else 2
    if group == "70% IPA Solubility":
        if any(term in text for term in ("70 ipa", "70 isoprop", "2 propanol", "isopropanol")):
            return 0
        if any(term in text for term in ("ethanol", "alcohol", "methanol")):
            return 1
        return 2
    if group == "2% Decon Solubility":
        if "decon" in text:
            return 0
        if any(term in text for term in ("water", "2 propanol", "isopropanol", "ethanol", "methanol", "solub")):
            return 1
        return 2
    if group == "Physical Cleanability":
        if any(term in text for term in ("tablet", "crush", "suspension", "powder", "residue", "sticky", "film", "oil")):
            return 0
        return 1
    return 1


def _dedupe_exact(sources: list[EvidenceSource]) -> list[EvidenceSource]:
    return _merge_by_document(sources)


def _material_token(material_name: str) -> str:
    excluded = {
        "tablet", "tablets", "capsule", "capsules", "solution", "suspension", "cream",
        "ointment", "powder", "mg", "ml",
    }
    for token in re.findall(r"[A-Za-z][A-Za-z-]{3,}", material_name.lower()):
        if token not in excluded:
            return token
    return ""


def is_cleaner_only_decon_source(source: EvidenceSource, material_name: str) -> bool:
    """Reject literature that describes Decon 90 itself but not the assessed material's behaviour."""
    url_title = _normalise(f"{source.title} {source.publisher} {source.url}")
    extract = _normalise(source.relevant_extract)
    if "decon" not in url_title:
        return False
    token = _material_token(material_name)
    return bool(token) and token not in extract


def curate_sources(
    sources: list[EvidenceSource],
    *,
    group: str,
    limit: int,
    material_name: str = "",
) -> list[EvidenceSource]:
    candidates = _dedupe_exact(sources)
    if group == "2% Decon Solubility":
        candidates = [s for s in candidates if not is_cleaner_only_decon_source(s, material_name)]
    candidates.sort(
        key=lambda s: (
            _group_directness(s, group),
            _applicability_rank(s, group),
            *_base_rank(s),
        )
    )
    return candidates[:limit]


def _polarity(source: EvidenceSource) -> str:
    text = _normalise(f"{source.relevant_extract} {source.interpretation}")
    negative_terms = (
        "no evidence", "negative", "no special hazards", "not mutagenic", "not clastogenic",
        "did not reveal", "no increased", "reassuring", "not carcinogenic", "do not represent a major",
    )
    positive_terms = (
        "positive", "mutagen", "genotoxic", "clastogenic in vivo", "inducing", "induced",
        "chromosome aberration", "micronucleus", "dna damage", "tumour", "tumor", "carcinoma",
        "adenoma", "developmental toxicity", "reproductive toxicity", "embryo toxic", "teratogenic",
        "h317", "allergic skin reaction", "sensitizer", "sensitiser",
    )
    has_negative = any(term in text for term in negative_terms)
    has_positive = any(term in text for term in positive_terms)
    if has_positive and not has_negative:
        return "POSITIVE"
    if has_negative and not has_positive:
        return "NEGATIVE"
    return "MIXED"


def _best_matching(sources: list[EvidenceSource], polarity: str) -> EvidenceSource | None:
    matches = [source for source in sources if _polarity(source) == polarity]
    if not matches:
        return None
    return sorted(matches, key=lambda s: (_hazard_applicability_rank(s), *_base_rank(s)))[0]


def curate_hazard_sources(hazard: HazardResearch, limit: int = 5) -> list[EvidenceSource]:
    """Keep broad research in JSON, but append only the strongest evidence needed for the form."""
    chosen: list[EvidenceSource] = []
    fields = (
        "mutagenicity_genotoxicity",
        "carcinogenicity",
        "reproductive_developmental_toxicity",
        "sensitisation_potential",
    )
    for field in fields:
        item = getattr(hazard, field)
        if item.conclusion != Conclusion.YES:
            continue
        sources = sorted(
            _dedupe_exact(item.sources),
            key=lambda s: (_hazard_applicability_rank(s), *_base_rank(s)),
        )
        if not sources:
            continue

        if item.evidence_status == HazardEvidenceStatus.CONFLICTING:
            positive = _best_matching(sources, "POSITIVE")
            negative = _best_matching(sources, "NEGATIVE")
            picks = [source for source in (positive, negative) if source is not None]
            if not picks:
                picks = sources[:2]
        else:
            positive = _best_matching(sources, "POSITIVE")
            picks = [positive or sources[0]]

        for source in picks:
            key = evidence_key(source)
            existing_index = next(
                (index for index, existing in enumerate(chosen) if evidence_key(existing) == key),
                None,
            )
            if existing_index is None:
                chosen.append(source)
            else:
                chosen[existing_index] = merge_evidence_sources(chosen[existing_index], source)
            if len(chosen) >= limit:
                return chosen
    return chosen[:limit]
