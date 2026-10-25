from pathlib import Path
from types import SimpleNamespace

from agent import web


def test_running_server_reports_controlled_template_and_no_legacy_renderer(monkeypatch):
    monkeypatch.setattr(
        web, "_settings",
        lambda: SimpleNamespace(coshh_template_path=Path("templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx")),
    )
    result = web.version()
    assert result["coshh_template"] == "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    assert result["coshh_template_fields"] == 134
    assert result["legacy_coshh_renderer"] is False
