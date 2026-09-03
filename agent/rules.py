from __future__ import annotations

from .models import (
    CleanabilityResearch,
    Conclusion,
    HazardEvidenceStatus,
    HazardResearch,
    PhysicalClass,
    PotencyResearch,
    ScoringResult,
    SolubilityClass,
)


HAZARD_SCORES = {
    "mutagenicity_genotoxicity": 5,
    "carcinogenicity": 4,
    "reproductive_developmental_toxicity": 3,
    "sensitisation_potential": 2,
}


def _hazard_source_urls(hazard: HazardResearch) -> list[str]:
    items = [
        hazard.mutagenicity_genotoxicity,
        hazard.carcinogenicity,
        hazard.reproductive_developmental_toxicity,
        hazard.sensitisation_potential,
    ]
    return [source.url.lower() for item in items for source in item.sources]


def score_hazard(hazard: HazardResearch) -> tuple[int, str, list[str]]:
    flags: list[str] = []
    selected: list[tuple[int, str]] = []

    for field_name, score in HAZARD_SCORES.items():
        item = getattr(hazard, field_name)
        if item.conclusion == Conclusion.YES:
            selected.append((score, field_name))
        elif item.conclusion in {Conclusion.UNKNOWN, Conclusion.CONFLICTING}:
            flags.append(
                f"Hazard {field_name.replace('_', ' ')} is {item.conclusion.value}; operator review required."
            )
        if item.evidence_status == HazardEvidenceStatus.CONFLICTING:
            flags.append(
                f"Hazard {field_name.replace('_', ' ')} has CONFLICTING evidence; conservative positive scoring is retained where Tier 1 positive evidence was identified."
            )
        elif item.evidence_status == HazardEvidenceStatus.INSUFFICIENT:
            flags.append(
                f"Hazard {field_name.replace('_', ' ')} has insufficient evidence; operator review required."
            )

    urls = _hazard_source_urls(hazard)
    if not any("pubmed.ncbi.nlm.nih.gov" in url or "pmc.ncbi.nlm.nih.gov" in url for url in urls):
        flags.append(
            "Evidence-hardening check: no PubMed/PMC hazard source was retained. Confirm the mandatory peer-reviewed hazard search lane was completed."
        )
    if not any(
        token in url
        for url in urls
        for token in ("medicines.org.uk", "gov.uk", "mhra", "ema.europa.eu", "echa.europa.eu")
    ):
        flags.append(
            "Evidence-hardening check: no UK/EU regulatory hazard source was retained. Confirm the regulatory hazard search lane was completed."
        )

    if selected:
        score, field_name = max(selected, key=lambda x: x[0])
        return score, field_name, flags

    return 1, "therapeutic_category_risk", flags


def score_potency(potency: PotencyResearch) -> tuple[int | None, list[str]]:
    flags: list[str] = []
    if not potency.bnf_nice_checked:
        flags.append("BNF/NICE primary dose lane was not successfully checked; operator review required.")
    if not potency.emc_checked:
        flags.append("UK eMC/SmPC dose corroboration lane was not successfully checked; operator review required.")

    if not potency.dose_available or potency.lowest_typical_daily_dose_mg is None:
        flags.append(
            "Lowest typical daily dose could not be converted to a reliable mg/day value; potency and overall screening score require operator completion."
        )
        return None, flags

    dose = potency.lowest_typical_daily_dose_mg
    if dose <= 0.1:
        score = 5
    elif dose <= 1:
        score = 4
    elif dose <= 10:
        score = 3
    elif dose <= 100:
        score = 2
    else:
        score = 1

    if potency.evidence_status.value != "SUPPORTED":
        flags.append(
            f"Potency evidence status is {potency.evidence_status.value}: {potency.review_note or 'review supporting evidence.'}"
        )
    return score, flags


def _score_solubility(value: SolubilityClass, label: str) -> tuple[int, list[str]]:
    if value == SolubilityClass.FREELY_SOLUBLE:
        return 1, []
    if value == SolubilityClass.SLIGHT_MODERATE:
        return 3, []
    if value == SolubilityClass.PRACTICALLY_INSOLUBLE:
        return 5, []
    return 3, [f"{label} classification requires review; provisional intermediate score 3 used in the draft."]


def _score_physical(value: PhysicalClass) -> tuple[int, list[str]]:
    if value == PhysicalClass.CRYSTALLINE_NON_STICKY:
        return 1, []
    if value == PhysicalClass.CAKING_SUSPENSION_RESIDUE:
        return 3, []
    if value == PhysicalClass.OILY_STICKY_FILM_FORMING:
        return 5, []
    return 3, [
        "Physical cleanability classification requires review; provisional intermediate score 3 used in the draft."
    ]


def score_cleanability(cleanability: CleanabilityResearch) -> tuple[int, int, int, int, int, list[str]]:
    flags: list[str] = []
    water, f = _score_solubility(cleanability.water.classification, "Water solubility")
    flags.extend(f)
    ipa, f = _score_solubility(cleanability.ipa70.classification, "70% IPA solubility")
    flags.extend(f)
    decon, f = _score_solubility(cleanability.decon2.classification, "2% Decon solubility")
    flags.extend(f)
    physical, f = _score_physical(cleanability.physical.classification)
    flags.extend(f)

    for label, item in (
        ("Water", cleanability.water),
        ("70% IPA", cleanability.ipa70),
        ("2% Decon", cleanability.decon2),
        ("Physical cleanability", cleanability.physical),
    ):
        if item.evidence_status.value != "SUPPORTED":
            flags.append(
                f"{label} evidence status is {item.evidence_status.value}: {item.review_note or item.rationale}"
            )

    subtotal = water + ipa + decon + physical
    return subtotal, water, ipa, decon, physical, flags


def calculate_scoring(
    hazard: HazardResearch,
    potency: PotencyResearch,
    cleanability: CleanabilityResearch,
) -> ScoringResult:
    a, hazard_selected, flags = score_hazard(hazard)
    b, potency_flags = score_potency(potency)
    flags.extend(potency_flags)

    c, water, ipa, decon, physical, clean_flags = score_cleanability(cleanability)
    flags.extend(clean_flags)

    d = a * b * c if b is not None else None
    hard_reason = ""

    if hazard.mutagenicity_genotoxicity.conclusion == Conclusion.YES:
        pde_requirement = "MANDATORY"
        hard_reason = "Genotoxicity/Mutagenicity selected: mandatory PDE escalation rule."
    elif hazard.carcinogenicity.conclusion == Conclusion.YES and c >= 12:
        pde_requirement = "MANDATORY"
        hard_reason = "Carcinogenicity selected and Cleanability Subtotal >=12: mandatory PDE escalation rule."
    elif d is None:
        pde_requirement = "UNDETERMINED"
    elif d <= 80:
        pde_requirement = "NOT_REQUIRED"
    elif d <= 149:
        pde_requirement = "RECOMMENDED"
    else:
        pde_requirement = "MANDATORY"

    return ScoringResult(
        hazard_score_a=a,
        hazard_selected=hazard_selected,
        potency_score_b=b,
        cleanability_score_c=c,
        water_score=water,
        ipa70_score=ipa,
        decon2_score=decon,
        physical_score=physical,
        overall_screening_risk_d=d,
        pde_requirement=pde_requirement,
        hard_escalation_reason=hard_reason,
        review_flags=flags,
    )
