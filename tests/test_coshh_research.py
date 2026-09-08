from agent.prompts import cleanability_prompt, coshh_prompt
from agent.research import _safe_schema_name


def test_decon_prompt_uses_alkaline_solubility_waterfall_and_acid_base_safeguard():
    prompt = cleanability_prompt(
        "Haloperidol 10 mg Tablets",
        "Haloperidol",
        "Haloperidol",
        ["haloperidol"],
        ["haloperidol solubility", "haloperidol pKa"],
        "Suspension",
        "Tablets are crushed for manufacture",
        "Crushed tablet material",
    )
    assert "ALKALINE SOLUBILITY WATERFALL" in prompt
    assert "COMPARABLE_ALKALINE_CLEANER" in prompt
    assert "PH_SOLUBILITY" in prompt
    assert "PKA_IONISATION_INFERENCE" in prompt
    assert "basic compound" in prompt
    assert "can REDUCE aqueous solubility" in prompt
    assert "MUST begin with \"Evidence basis:" in prompt


def test_coshh_prompt_is_sds_first_and_separates_substance_from_material_context():
    prompt = coshh_prompt(
        "Haloperidol 10 mg Tablets",
        "Haloperidol",
        "Haloperidol",
        ["haloperidol"],
        "Crushed haloperidol tablet material",
        "Tablets are crushed for suspension manufacture",
    )
    assert "SDS-FIRST RULE" in prompt
    assert "Haloperidol 10 mg Tablets" in prompt
    assert "COSHH substance name \"Haloperidol\"" in prompt
    assert "material_use_context" in prompt
    assert "actual Eaststone supplier" in prompt
    assert "GB Workplace Exposure Limit" in prompt
    assert "Do not invent Eaststone engineering controls" in prompt


def test_structured_output_schema_names_are_clamped_to_64_characters():
    problematic = "evidence_rescue_2pct_decon_solubility_comparable_alkaline_cleaner"
    assert len(problematic) == 65
    safe = _safe_schema_name(problematic)
    assert len(safe) <= 64
    assert safe != problematic
    assert _safe_schema_name("coshh_research") == "coshh_research"
