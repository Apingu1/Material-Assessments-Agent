from agent.models import EvidenceSource, IdentityResearch
from agent.prompts import cleanability_prompt, evidence_rescue_prompt, identity_prompt, potency_prompt


def test_structured_output_models_require_all_new_fields():
    evidence_schema = EvidenceSource.model_json_schema()
    assert set(evidence_schema["required"]) == set(evidence_schema["properties"])

    identity_schema = IdentityResearch.model_json_schema()
    assert set(identity_schema["required"]) == set(identity_schema["properties"])


def test_identity_prompt_separates_controlled_name_from_research_identity():
    prompt = identity_prompt(
        "Levothyroxine Sodium Powder",
        "Solution",
        "Oral",
        "Powder is used to manufacture an oral solution",
    )
    assert "CONTROLLED MATERIAL NAME" in prompt
    assert "chemical identity should usually be levothyroxine sodium" in prompt
    assert "active moiety should usually be levothyroxine" in prompt
    assert "Remove strength and presentation words" in prompt


def test_potency_prompt_ignores_starting_strength_and_expands_formulations():
    prompt = potency_prompt(
        "Haloperidol 10mg Tablets",
        "Haloperidol",
        ["haloperidol"],
        ["haloperidol oral solution", "haloperidol tablets"],
        "Oral",
        "Tablets are crushed for suspension manufacture",
        "ADULT_DEFAULT",
    )
    assert "patient's therapeutic dose belongs to the ACTIVE MEDICINAL INGREDIENT" in prompt
    assert "must not prevent use of oral haloperidol dose information from lower-strength tablets or oral solution" in prompt
    assert "ROUTINE ADULT therapeutic daily dose" in prompt


def test_cleanability_prompt_keeps_salt_for_solubility_but_uses_process_for_physical():
    prompt = cleanability_prompt(
        "Levothyroxine Sodium Powder",
        "Levothyroxine sodium",
        "Levothyroxine",
        ["thyroxine", "T4"],
        ["levothyroxine sodium solubility"],
        "Solution",
        "Powder is dissolved to manufacture an oral solution",
        "Levothyroxine sodium powder handled and dissolved during solution manufacture",
    )
    assert "Physicochemical chemical species: Levothyroxine sodium" in prompt
    assert "research \"levothyroxine sodium\" rather than \"Levothyroxine Sodium Powder\"" in prompt
    assert "For PHYSICAL CLEANABILITY" in prompt
    assert "prioritise what actually contacts the equipment" in prompt


def test_rescue_prompt_searches_alternative_evidence_without_changing_conclusion():
    prompt = evidence_rescue_prompt(
        group="Potency",
        material_name="Levothyroxine Sodium Powder",
        chemical_identity="Levothyroxine sodium",
        active_moiety="Levothyroxine",
        synonyms=["thyroxine", "T4"],
        clinical_search_terms=["levothyroxine oral solution", "levothyroxine tablets"],
        physicochemical_search_terms=["levothyroxine sodium solubility"],
        routes="Oral",
        context="Oral solution manufacture",
        target_summary="Routine adult oral dose supports <=0.1 mg/day",
        existing_urls=["https://example.com/blocked"],
    )
    assert "Find an ALTERNATIVE" in prompt
    assert "Do not change or reverse the conclusion" in prompt
    assert "search the active ingredient across route-appropriate formulations and strengths" in prompt
