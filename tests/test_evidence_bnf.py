from agent.evidence import _bnf_page_matches_source, _is_bnf_url, EvidenceCollector
from agent.models import EvidenceSource, SourceType
from agent.document_text import assessment_text


def source():
    return EvidenceSource(title="Haloperidol", publisher="BNF", url="https://bnf.nice.org.uk/drugs/haloperidol/",
        tier=1, source_type=SourceType.CLINICAL,
        relevant_extract="0.5 to 5 mg daily", interpretation="Adult oral dose.", applicability=[])


def test_dose_numbers_must_match_not_only_clinical_words():
    assert _bnf_page_matches_source("Adults: 0.5 to 5 mg daily", source())
    assert not _bnf_page_matches_source("Adults: 10 to 20 mg daily", source())
    assert not _bnf_page_matches_source("Adults: 0.5 to 5 micrograms daily", source())
    assert not _bnf_page_matches_source("Adult oral dose. Indications and dose", source())


def test_bnf_hostname_is_exact():
    assert _is_bnf_url(source().url)
    assert not _is_bnf_url("https://bnf.nice.org.uk.example.org/drugs/haloperidol/")


def test_legacy_workflow_comment_removed_but_safety_limit_retained():
    assert assessment_text("Haloperidol tablets used in an oral suspension; specific processing steps were not supplied.") == "Haloperidol tablets used in an oral suspension."
    assert assessment_text("Supplier storage requirements must be verified.") == "Supplier storage requirements must be verified."


def test_failed_bnf_verification_cannot_fall_through_to_generic_capture(tmp_path, monkeypatch):
    from types import SimpleNamespace
    collector = EvidenceCollector(SimpleNamespace(capture_evidence=True))
    monkeypatch.setattr(collector, "_try_pdf", lambda *args: None)
    def fail(*args):
        raise RuntimeError("Relevant evidence text was not located")
    monkeypatch.setattr(collector, "_capture_bnf_html", fail)
    def generic(*args):
        raise AssertionError("Must not accept an unverified generic BNF screenshot")
    monkeypatch.setattr(collector, "_capture_html", generic)
    capture = collector.capture_source(source(), "Potency", "2A", tmp_path)
    assert capture.capture_status == "FAILED"
    assert capture.capture_path is None
    assert list(tmp_path.glob("*BNF_BROWSER-DIAGNOSTIC.txt"))
