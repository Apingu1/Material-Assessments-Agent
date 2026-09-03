from agent.models import (
    CleanabilityResearch,
    Conclusion,
    EvidenceStatus,
    HazardEvidenceStatus,
    HazardItem,
    HazardResearch,
    PhysicalClass,
    PhysicalFinding,
    PotencyResearch,
    SolubilityClass,
    SolubilityFinding,
)
from agent.rules import calculate_scoring


def h(value, evidence_status=HazardEvidenceStatus.SUPPORTED):
    return HazardItem(conclusion=value, evidence_status=evidence_status, rationale="test", sources=[])


def s(value):
    return SolubilityFinding(classification=value, evidence_status=EvidenceStatus.SUPPORTED, rationale="test", review_note="", sources=[])


def physical(value):
    return PhysicalFinding(classification=value, evidence_status=EvidenceStatus.SUPPORTED, assessment_basis="test", rationale="test", review_note="", sources=[])


def clean(water, ipa, decon, phys):
    return CleanabilityResearch(water=s(water), ipa70=s(ipa), decon2=s(decon), physical=physical(phys), overall_notes="")


def potency(dose):
    return PotencyResearch(
        dose_available=True,
        lowest_typical_daily_dose_mg=dose,
        dose_statement=str(dose),
        route_used_for_dose="oral",
        dose_calculation="",
        evidence_status=EvidenceStatus.SUPPORTED,
        review_note="",
        bnf_nice_checked=True,
        emc_checked=True,
        sources=[],
    )


def hazard_set(mut=Conclusion.NO, carc=Conclusion.NO, repro=Conclusion.NO, sens=Conclusion.NO, mut_status=HazardEvidenceStatus.SUPPORTED):
    return HazardResearch(
        mutagenicity_genotoxicity=h(mut, mut_status),
        carcinogenicity=h(carc),
        reproductive_developmental_toxicity=h(repro),
        sensitisation_potential=h(sens),
        overall_notes="",
    )


def test_threshold_180_is_mandatory():
    hazard = hazard_set(repro=Conclusion.YES)
    c = clean(SolubilityClass.PRACTICALLY_INSOLUBLE, SolubilityClass.SLIGHT_MODERATE, SolubilityClass.SLIGHT_MODERATE, PhysicalClass.CRYSTALLINE_NON_STICKY)
    result = calculate_scoring(hazard, potency(0.1), c)
    assert result.hazard_score_a == 3
    assert result.potency_score_b == 5
    assert result.cleanability_score_c == 12
    assert result.overall_screening_risk_d == 180
    assert result.pde_requirement == "MANDATORY"


def test_low_risk_no_pde():
    hazard = hazard_set()
    c = clean(SolubilityClass.PRACTICALLY_INSOLUBLE, SolubilityClass.PRACTICALLY_INSOLUBLE, SolubilityClass.PRACTICALLY_INSOLUBLE, PhysicalClass.OILY_STICKY_FILM_FORMING)
    result = calculate_scoring(hazard, potency(1000), c)
    assert result.hazard_score_a == 1
    assert result.cleanability_score_c == 20
    assert result.overall_screening_risk_d == 20
    assert result.pde_requirement == "NOT_REQUIRED"


def test_carcinogen_cleanability_hard_rule():
    hazard = hazard_set(carc=Conclusion.YES)
    c = clean(SolubilityClass.PRACTICALLY_INSOLUBLE, SolubilityClass.SLIGHT_MODERATE, SolubilityClass.SLIGHT_MODERATE, PhysicalClass.CRYSTALLINE_NON_STICKY)
    result = calculate_scoring(hazard, potency(1000), c)
    assert result.cleanability_score_c == 12
    assert result.overall_screening_risk_d == 48
    assert result.pde_requirement == "MANDATORY"


def test_missing_dose_stops_overall_decision():
    hazard = hazard_set()
    p = potency(1)
    p.dose_available = False
    p.lowest_typical_daily_dose_mg = None
    c = clean(SolubilityClass.FREELY_SOLUBLE, SolubilityClass.FREELY_SOLUBLE, SolubilityClass.FREELY_SOLUBLE, PhysicalClass.CRYSTALLINE_NON_STICKY)
    result = calculate_scoring(hazard, p, c)
    assert result.potency_score_b is None
    assert result.overall_screening_risk_d is None
    assert result.pde_requirement == "UNDETERMINED"


def test_conflicting_tier1_positive_genotoxicity_scores_conservatively():
    hazard = hazard_set(mut=Conclusion.YES, mut_status=HazardEvidenceStatus.CONFLICTING)
    c = clean(SolubilityClass.PRACTICALLY_INSOLUBLE, SolubilityClass.SLIGHT_MODERATE, SolubilityClass.SLIGHT_MODERATE, PhysicalClass.CAKING_SUSPENSION_RESIDUE)
    result = calculate_scoring(hazard, potency(2), c)
    assert result.hazard_score_a == 5
    assert result.hazard_selected == "mutagenicity_genotoxicity"
    assert result.pde_requirement == "MANDATORY"
    assert any("CONFLICTING" in flag for flag in result.review_flags)


def test_missing_bnf_or_emc_is_flagged():
    p = potency(2)
    p.bnf_nice_checked = False
    p.emc_checked = False
    c = clean(SolubilityClass.FREELY_SOLUBLE, SolubilityClass.FREELY_SOLUBLE, SolubilityClass.FREELY_SOLUBLE, PhysicalClass.CRYSTALLINE_NON_STICKY)
    result = calculate_scoring(hazard_set(), p, c)
    joined = " ".join(result.review_flags)
    assert "BNF/NICE" in joined
    assert "eMC/SmPC" in joined
