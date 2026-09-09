"""Presentation helpers: retain factual qualifications, remove workflow commentary."""
import re


def assessment_text(value: str) -> str:
    text = str(value or "").replace("**", "")
    # Narrow legacy cleanup only. Never remove an unknown hazard or control limitation.
    text = re.sub(
        r"[;,.]?\s*specific processing steps (?:were not|have not been) supplied\.?",
        "", text, flags=re.I,
    )
    text = text.replace("human review", "assessment review").replace("Human review", "Assessment review")
    text = text.replace("has not been supplied; confirm during assessment review", "to be confirmed before approval")
    text = text.replace("have not been supplied; confirm before approval", "to be confirmed before approval")
    text = text.strip().rstrip(";")
    if text and re.search(r"specific processing steps", str(value), re.I) and not text.endswith("."):
        text += "."
    return text


def hanging_bullet(paragraph, text: str, size: float = 8.5):
    from docx.shared import Inches, Pt
    pf = paragraph.paragraph_format
    pf.left_indent = Inches(0.14)
    pf.first_line_indent = Inches(-0.14)
    pf.tab_stops.add_tab_stop(Inches(0.14))
    pf.space_before = Pt(0)
    pf.space_after = Pt(3)
    run = paragraph.add_run("•\t" + assessment_text(text).lstrip("• "))
    run.font.name = "Arial"
    run.font.size = Pt(size)
    return run
