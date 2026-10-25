"""Regression: OpenAI rejects strict JSON schema with omitted required fields.

All checks run offline and incur zero API charges.
"""
from types import SimpleNamespace

import pytest

from agent.models import (
    COSHHResearch, IdentityResearch, HazardResearch, PotencyResearch,
    CleanabilityResearch, EvidenceRescueResearch,
)
from agent.research import ResearchAgent, _strict_response_schema

MODELS = (
    COSHHResearch, IdentityResearch, HazardResearch, PotencyResearch,
    CleanabilityResearch, EvidenceRescueResearch,
)


def _check_all_objects(node, location="root"):
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            keys = list(node["properties"])
            assert set(node["required"]) == set(keys), location
            assert len(node["required"]) == len(keys), location
            assert node["additionalProperties"] is False, location
        assert "default" not in node, location
        for key, child in node.items():
            _check_all_objects(child, location + "." + str(key))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            _check_all_objects(child, location + "[" + str(index) + "]")


@pytest.mark.parametrize("model", MODELS)
def test_research_schema_every_nested_property_is_required(model):
    _check_all_objects(_strict_response_schema(model), model.__name__)


def test_missing_relevant_health_effects_was_root_cause():
    original = COSHHResearch.model_json_schema()
    assert "relevant_health_effects" not in original["required"]
    strict = _strict_response_schema(COSHHResearch)
    assert "relevant_health_effects" in strict["required"]
    assert "default" not in strict["properties"]["relevant_health_effects"]


def test_exact_sdk_request_passes_correct_schema_without_network():
    """Capture real ResearchAgent call options, but intercept before any network."""
    class Captured(Exception):
        pass

    seen = []

    def interception(**kwargs):
        seen.append(kwargs)
        raise Captured("Expected offline interception")

    researcher = object.__new__(ResearchAgent)
    researcher.settings = SimpleNamespace(openai_model="test-model")
    researcher.client = SimpleNamespace(
        responses=SimpleNamespace(create=interception)
    )
    with pytest.raises(Captured):
        researcher._structured_web_research(
            "Extract from downloaded Levomepromazine maleate SDS",
            COSHHResearch,
            "coshh_verified_pdf_extraction",
            search_web=False,
        )
    assert len(seen) == 1
    request = seen[0]
    assert request["tools"] == []
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["name"] == "coshh_verified_pdf_extraction"
    schema = request["text"]["format"]["schema"]
    _check_all_objects(schema)
    assert "relevant_health_effects" in schema["required"]


def test_backward_compatibility_preserves_pydantic_default():
    # Saved older JSON that lacks this optional field is still accepted.
    assert "relevant_health_effects" not in COSHHResearch.model_json_schema()["required"]
