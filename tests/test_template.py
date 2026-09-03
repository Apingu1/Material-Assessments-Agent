from pathlib import Path

from agent.docx_template import REQUIRED_TAGS, list_content_control_tags, validate_template


def test_agent_ready_template_has_required_tags():
    template = Path("ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment.docx")
    validate_template(template)
    tags = list_content_control_tags(template)
    assert REQUIRED_TAGS.issubset(tags)
