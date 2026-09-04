from agent.curation import curate_hazard_sources, curate_sources, is_cleaner_only_decon_source
from agent.models import (
    Conclusion,
    EvidenceSource,
    HazardEvidenceStatus,
    HazardItem,
    HazardResearch,
    SourceType,
)


def source(title, url, tier, extract, interpretation, source_type=SourceType.PEER_REVIEWED, publisher="Test"):
    return EvidenceSource(
        title=title,
        publisher=publisher,
        url=url,
        tier=tier,
        source_type=source_type,
        relevant_extract=extract,
        interpretation=interpretation,
    )


def item(conclusion, status, sources):
    return HazardItem(conclusion=conclusion, evidence_status=status, rationale="test", sources=sources)


def test_hazard_curation_keeps_strong_positive_and_conflict_without_literature_dump():
    positive = source(
        "Positive genotoxicity",
        "https://pubmed.ncbi.nlm.nih.gov/25036041/",
        1,
        "HLP is capable of inducing cyto/genotoxicity in tested cells.",
        "Positive genotoxic evidence.",
    )
    negative = source(
        "Haloperidol SmPC",
        "https://www.medicines.org.uk/emc/product/1/smpc",
        1,
        "No special hazards based on conventional studies of genotoxicity.",
        "Reassuring conventional genotoxicity evidence.",
        SourceType.REGULATORY,
        "eMC",
    )
    extra_positive = source(
        "Another positive paper",
        "https://pubmed.ncbi.nlm.nih.gov/111/",
        1,
        "Positive chromosome aberration findings were reported.",
        "Additional positive evidence.",
    )
    carcin = source(
        "Haloperidol SmPC",
        "https://www.medicines.org.uk/emc/product/1/smpc",
        1,
        "Dose-dependent increases in mammary gland carcinomas were seen in female mice.",
        "Positive rodent tumour finding.",
        SourceType.REGULATORY,
        "eMC",
    )
    repro = source(
        "Haloperidol SmPC",
        "https://www.medicines.org.uk/emc/product/1/smpc",
        1,
        "Haloperidol showed limited teratogenicity and embryo-toxic effects.",
        "Positive reproductive/developmental evidence.",
        SourceType.REGULATORY,
        "eMC",
    )
    sensit = source(
        "Safety Data Sheet: Haloperidol",
        "https://example.com/haloperidol-sds.pdf",
        2,
        "H317 May cause an allergic skin reaction.",
        "Explicit skin sensitiser classification.",
        SourceType.MANUFACTURER,
        "Cayman Chemical",
    )
    hazard = HazardResearch(
        mutagenicity_genotoxicity=item(Conclusion.YES, HazardEvidenceStatus.CONFLICTING, [negative, positive, extra_positive]),
        carcinogenicity=item(Conclusion.YES, HazardEvidenceStatus.SUPPORTED, [carcin]),
        reproductive_developmental_toxicity=item(Conclusion.YES, HazardEvidenceStatus.SUPPORTED, [repro]),
        sensitisation_potential=item(Conclusion.YES, HazardEvidenceStatus.SUPPORTED, [sensit]),
        overall_notes="",
    )
    chosen = curate_hazard_sources(hazard)
    assert len(chosen) <= 5
    urls = [s.url for s in chosen]
    assert positive.url in urls
    assert negative.url in urls
    assert sensit.url in urls
    assert extra_positive.url not in urls


def test_decon_product_page_is_not_material_solubility_evidence():
    cleaner = source(
        "Decon 90",
        "https://example.com/decon-90",
        2,
        "Prepare a 2% to 5% solution of Decon 90 with water.",
        "Describes the cleaning agent.",
        SourceType.MANUFACTURER,
        "ENVCO",
    )
    material_water = source(
        "Haloperidol - British Pharmacopoeia",
        "https://example.com/bp-haloperidol.pdf",
        1,
        "Haloperidol is practically insoluble in water.",
        "Material solvent evidence used for inference.",
        SourceType.PHARMACOPOEIAL,
        "British Pharmacopoeia",
    )
    assert is_cleaner_only_decon_source(cleaner, "Haloperidol 10mg Tablets")
    chosen = curate_sources(
        [cleaner, material_water],
        group="2% Decon Solubility",
        limit=2,
        material_name="Haloperidol 10mg Tablets",
    )
    assert cleaner not in chosen
    assert material_water in chosen


def test_direct_isopropanol_beats_higher_tier_different_alcohol_for_ipa():
    bp_ethanol = source(
        "British Pharmacopoeia",
        "https://example.com/bp.pdf",
        1,
        "Slightly soluble in ethanol 96 per cent.",
        "Ethanol evidence only.",
        SourceType.PHARMACOPOEIAL,
        "British Pharmacopoeia",
    )
    jp_ipa = source(
        "JP Haloperidol",
        "https://example.com/jp.pdf",
        2,
        "Slightly soluble in 2-propanol.",
        "Direct isopropanol evidence.",
        SourceType.PHARMACOPOEIAL,
        "PMDA",
    )
    chosen = curate_sources([bp_ethanol, jp_ipa], group="70% IPA Solubility", limit=1)
    assert chosen == [jp_ipa]
