from pathlib import Path

from agent.pipeline import _new_run_directory


def test_repeated_material_runs_cannot_serve_legacy_coshh(tmp_path):
    prior = tmp_path / "Levomepromazine-Maleate-Powder"
    prior.mkdir()
    (prior / "Levomepromazine - COSHH Assessment - DRAFT.docx").write_text("old-format")
    one = _new_run_directory(tmp_path, "Levomepromazine Maleate Powder")
    two = _new_run_directory(tmp_path, "Levomepromazine Maleate Powder")
    assert one != two
    assert one.parent == prior
    one.mkdir()
    (one / "Levomepromazine Maleate - COSHH Assessment - DRAFT.docx").write_text("correct")
    assert len(list(one.glob("*COSHH Assessment - DRAFT.docx"))) == 1
    assert list(one.glob("*COSHH Assessment - DRAFT.docx"))[0].read_text() == "correct"
    assert list(two.glob("*COSHH Assessment - DRAFT.docx")) == []
