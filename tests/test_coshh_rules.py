from agent.coshh_rules import build_coshh_assessment
from agent.models import (
    COSHHArea,
    COSHHResearch,
    EvidenceApplicability,
    EvidenceSource,
    GHSCode,
    MaterialInput,
    SDSResearch,
    SourceType,
)


def source():
    return EvidenceSource(
        title="Safety Data Sheet",
        publisher="Example Manufacturer",
        url="https://example.com/sds.pdf",
        tier=2,
        source_type=SourceType.MANUFACTURER,
        relevant_extract="Harmful if swallowed. May cause an allergic skin reaction.",
        interpretation="The SDS classifies the substance as harmful if swallowed and a skin sensitiser.",
        applicability=[EvidenceApplicability.CHEMICAL_SPECIES],
    )


def research(*, high=False, reference=True):
    src = source()
    hazards = ["H302 - Harmful if swallowed", "H317 - May cause an allergic skin reaction"]
    pictograms = [GHSCode.GHS07]
    if high:
        hazards.append("H334 - May cause allergy or asthma symptoms or breathing difficulties if inhaled")
        pictograms.append(GHSCode.GHS08)
    return COSHHResearch(
        coshh_substance_name="Haloperidol",
        material_use_context="Haloperidol 10 mg Tablets - tablets are crushed for manufacture",
        sds=SDSResearch(
            substance_name="Haloperidol",
            cas_number="52-86-8",
            synonyms=["Haloperidol"],
            manufacturer="Example Manufacturer",
            product_name="Haloperidol",
            product_number="H123",
            revision_date="01 Jan 2026",
            url=src.url,
            is_supplier_specific=not reference,
            match_status="REFERENCE_SDS" if reference else "MATCHED",
            match_rationale="Reference SDS for the exact substance." if reference else "Supplier SDS confirmed.",
            source=src,
        ),
        physical_form="solid powder / crushed tablet material",
        colour="white",
        odour="not stated",
        signal_word="WARNING",
        pictograms=pictograms,
        hazard_statements=hazards,
        precautionary_statements=[],
        inhalation_hazard=high,
        skin_hazard=True,
        eye_hazard=False,
        ingestion_hazard=True,
        first_aid_inhalation="Move to fresh air.",
        first_aid_skin="Wash with soap and water.",
        first_aid_eye="Rinse with water.",
        first_aid_ingestion="Rinse mouth and seek advice.",
        spill_response="Avoid dust and collect into a suitable container.",
        storage_handling="Keep container tightly closed.",
        firefighting_media="Use media appropriate to surrounding fire.",
        environmental_precautions="Avoid release to drains.",
        disposal="Dispose through an approved route.",
        workplace_exposure_limit_found=False,
        workplace_exposure_limit="No GB WEL identified",
        health_surveillance_considered=True,
        health_surveillance_recommended=True,
        health_surveillance_rationale="Skin sensitisation requires reviewer consideration.",
        core_controls=["Avoid dust formation", "Avoid unnecessary skin contact", "Keep container closed"],
        review_note="",
        sources=[src],
    )


def test_goods_in_outer_pack_is_contained_and_does_not_force_rpe():
    item = MaterialInput(material_name="Haloperidol 10 mg Tablets", coshh_areas=[COSHHArea.GOODS_IN_WAREHOUSE])
    assessment = build_coshh_assessment(item, research())
    outer = next(x for x in assessment.activities if x.activity == "Open outer packaging")
    assert outer.exposure_scenario == "Primary material remains contained"
    assert outer.residual_risk.value == "LOW"
    assert not any("RPE" in value for value in outer.ppe)


def test_high_concern_powder_weighing_requires_review_and_p3_when_controls_unknown():
    item = MaterialInput(
        material_name="Haloperidol 10 mg Tablets",
        product_context="Tablets are crushed to a powder before compounding",
        coshh_areas=[COSHHArea.PRODUCTION],
        existing_controls="",
    )
    assessment = build_coshh_assessment(item, research(high=True))
    weighing = next(x for x in assessment.activities if x.activity == "Weighing")
    assert weighing.initial_risk.value == "HIGH"
    assert weighing.review_required is True
    assert any("P3" in value for value in weighing.ppe)
    assert any("engineering" in flag.lower() for flag in assessment.review_flags)


def test_reference_sds_is_flagged_for_human_review():
    item = MaterialInput(material_name="Haloperidol 10 mg Tablets", coshh_areas=[COSHHArea.QC])
    assessment = build_coshh_assessment(item, research(reference=True))
    assert any("reference SDS" in flag for flag in assessment.review_flags)


def test_confirmed_supplier_sds_removes_reference_sds_flag():
    item = MaterialInput(
        material_name="Haloperidol 10 mg Tablets",
        coshh_areas=[COSHHArea.QC],
        typical_quantity="10 g",
        existing_controls="fume cupboard",
    )
    assessment = build_coshh_assessment(item, research(reference=False))
    assert not any("reference SDS" in flag for flag in assessment.review_flags)
