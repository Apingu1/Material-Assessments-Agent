from pathlib import Path
from types import SimpleNamespace

from agent import web


def test_running_server_reports_controlled_template_and_no_legacy_renderer(monkeypatch):
    monkeypatch.setattr(
        web, "_settings",
        lambda: SimpleNamespace(
            coshh_template_path=Path("templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"),
            template_path=Path("ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment.docx"),
        ),
    )
    result = web.version()
    assert result["coshh_template"] == "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    assert result["coshh_template_fields"] == 134
    assert result["legacy_coshh_renderer"] is False
    assert result["loaded_engine_build"] == web.COSHH_ENGINE_BUILD
    assert result["coshh_template_path"].endswith("/templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx") or result["coshh_template_path"].startswith("templates/")



def test_old_unverified_coshh_download_is_blocked(tmp_path, monkeypatch):
    from fastapi import HTTPException
    import pytest
    monkeypatch.setattr(web, "_output_dir", lambda _: tmp_path)
    monkeypatch.setattr(web, "_coshh_payload", lambda _: {"template_verified": False})
    with pytest.raises(HTTPException) as exc:
        web.download(100, "coshh")
    assert exc.value.status_code == 409
    assert "unverified" in exc.value.detail
