from agent.sds import _looks_pdf, _pdf_links


def test_pdf_detection_accepts_pdf_magic_or_content_type():
    assert _looks_pdf(b"%PDF-1.7 test", "application/octet-stream")
    assert _looks_pdf(b"not magic", "application/pdf")
    assert not _looks_pdf(b"<html>", "text/html")


def test_sds_pdf_links_are_ranked_and_resolved():
    html = '''
    <a href="/docs/general.pdf">General PDF</a>
    <a href="/documents/product-sds.pdf">Safety Data Sheet</a>
    <a href="https://cdn.example.com/MSDS_123">MSDS</a>
    '''
    links = _pdf_links(html, "https://example.com/product")
    assert links[0] == "https://example.com/documents/product-sds.pdf"
    assert "https://cdn.example.com/MSDS_123" in links
