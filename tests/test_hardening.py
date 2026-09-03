from agent.evidence import _friendly_capture_error
from agent.pipeline import _compact_55


def test_section1_compaction_is_55_chars_max():
    value = "Typical antipsychotic butyrophenone derivative with additional explanatory wording"
    compact = _compact_55(value)
    assert len(compact) <= 55


def test_browser_error_is_sanitised_for_dossier():
    exc = RuntimeError(
        "<launching> /tmp/chrome --disable-x --foo\n"
        "error while loading shared libraries: libatk-1.0.so.0: cannot open shared object file"
    )
    note = _friendly_capture_error(exc)
    assert "<launching>" not in note
    assert "libatk" not in note
    assert "playwright install --with-deps chromium" in note
