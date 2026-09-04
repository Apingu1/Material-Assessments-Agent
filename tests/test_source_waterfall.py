from agent.curation import evidence_key, merge_evidence_sources
from agent.models import EvidenceApplicability, EvidenceSource, SourceType
from agent.rescue_prompts import source_family_rescue_prompt
from agent.source_waterfall import rescue_source_families


def _source(extract: str, interpretation: str) -> EvidenceSource:
    return EvidenceSource(
        title="Levothyroxine sodium monograph",
        publisher="British Pharmacopoeia",
        url="https://example.com/levothyroxine.pdf?utm_source=test",
        tier=1,
        source_type=SourceType.PHARMACOPOEIAL,
        relevant_extract=extract,
        interpretation=interpretation,
        applicability=[EvidenceApplicability.CHEMICAL_SPECIES],
    )


def test_same_document_key_ignores_extract_and_tracking_parameters():
    a = _source("Practically insoluble in water.", "Supports water classification.")
    b = _source("Slightly soluble in alcohol.", "Supports alcohol classification.")
    b.url = "https://example.com/levothyroxine.pdf"
    assert evidence_key(a) == evidence_key(b)


def test_same_document_findings_are_merged_not_repeated():
    a = _source("Practically insoluble in water.", "Supports water classification.")
    b = _source("Slightly soluble in alcohol.", "Supports alcohol classification.")
    merged = merge_evidence_sources(a, b)
    assert "Practically insoluble in water" in merged.relevant_extract
    assert "Slightly soluble in alcohol" in merged.relevant_extract
    assert merged.url == a.url


def test_potency_rescue_uses_fixed_uk_first_waterfall():
    families = rescue_source_families("Potency")
    assert families[:2] == ("NICE_GUIDANCE", "EMC_SMPC")
    assert families.index("FDA_DAILYMED") > families.index("EMC_SMPC")


def test_decon_waterfall_checks_direct_material_decon_first():
    families = rescue_source_families("2% Decon Solubility")
    assert families[0] == "DIRECT_MATERIAL_DECON"
    assert "PUBCHEM" in families


def test_nice_rescue_prompt_is_domain_constrained_and_not_starting_material_limited():
    prompt = source_family_rescue_prompt(
        family="NICE_GUIDANCE",
        group="Potency",
        material_name="Levothyroxine Sodium Powder",
        chemical_identity="levothyroxine sodium",
        active_moiety="levothyroxine",
        synonyms=["thyroxine", "T4"],
        clinical_search_terms=["levothyroxine oral solution", "levothyroxine tablets"],
        physicochemical_search_terms=["levothyroxine sodium"],
        routes="Oral",
        context="Used to manufacture an oral solution",
        target_summary="Routine adult dose supports <=0.1 mg/day.",
        existing_urls=["https://bnf.nice.org.uk/drugs/levothyroxine-sodium/"],
    )
    assert "nice.org.uk" in prompt
    assert "Do not return BNF pages" in prompt
    assert "active ingredient across relevant strengths/formulations" in prompt
    assert "Levothyroxine Sodium Powder" in prompt
