from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_JSON = ROOT / "work" / "presentations" / "dealerai_interview" / "speaker_script.json"
OUTPUT = ROOT / "outputs" / "dealerai_ops_interview_script.pdf"

INK = colors.HexColor("#1F262A")
MUTED = colors.HexColor("#68767A")
TEAL = colors.HexColor("#245C5A")
LINE = colors.HexColor("#D8D7D0")
SOFT = colors.HexColor("#F7F5EF")


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=MUTED,
            spaceAfter=16,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=TEAL,
            spaceBefore=14,
            spaceAfter=5,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            spaceBefore=5,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.7,
            leading=13.8,
            textColor=INK,
            spaceAfter=7,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.8,
            textColor=INK,
            leftIndent=8,
            spaceAfter=2,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13.2,
            textColor=INK,
            backColor=SOFT,
            borderColor=LINE,
            borderWidth=0.5,
            borderPadding=8,
            spaceAfter=10,
        ),
    }


S = make_styles()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, "bullet"), bulletColor=TEAL) for item in items],
        bulletType="bullet",
        leftIndent=14,
    )


def on_page(canvas, doc) -> None:
    canvas.saveState()
    width, height = LETTER
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(0.65 * inch, height - 0.55 * inch, width - 0.65 * inch, height - 0.55 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.65 * inch, 0.38 * inch, "DealerAI Ops - Interview Speaker Script")
    canvas.drawRightString(width - 0.65 * inch, 0.38 * inch, f"Page {doc.page}")
    canvas.restoreState()


OBJECTIVES = [
    "Frame the project honestly and confidently.",
    "State the architectural philosophy.",
    "Explain why the system is more than a chatbot.",
    "Whiteboard the end-to-end flow.",
    "Show why deterministic synthetic data matters.",
    "Defend the ML methodology and leakage controls.",
    "Explain grounded retrieval and evaluation.",
    "Make the tool layer the main safety boundary.",
    "Show how guardrails constrain the agent loop.",
    "Connect evaluation to release readiness.",
    "Separate implemented operations from proposed AWS mapping.",
    "Close with strengths and honest limitations.",
]


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    slides = json.loads(SCRIPT_JSON.read_text(encoding="utf-8"))

    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=LETTER,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.65 * inch,
        title="DealerAI Ops Interview Script",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame], onPage=on_page)])

    story = [
        p("DealerAI Ops Interview Script", "title"),
        p(
            "Slide-by-slide talk track for a Senior Data Scientist / AI Engineer interview. "
            "Use this as a rehearsal guide; keep delivery conversational and adapt depth to the interviewer.",
            "subtitle",
        ),
        p(
            "Positioning rule: describe this as a production-oriented local/reference implementation using synthetic data. "
            "Do not claim live AWS deployment, real customer data, or production dealership integration.",
            "callout",
        ),
        p("Suggested Opening Rhythm", "h1"),
        bullets(
            [
                "First 90 seconds: explain the problem, the architecture thesis, and the strongest implemented evidence.",
                "Main walkthrough: spend more time on tool safety, ML leakage controls, RAG evaluation, and the release gate.",
                "When challenged: distinguish implemented local behavior from proposed AWS production mappings.",
            ]
        ),
        PageBreak(),
    ]

    for idx, item in enumerate(slides, start=1):
        block = [
            p(f"Slide {idx}: {item['title']}", "h1"),
            p("Speaker objective", "label"),
            p(OBJECTIVES[idx - 1]),
            p("Script", "label"),
            p(item["notes"]),
            p("Likely interviewer hook", "label"),
        ]
        if idx in {1, 12}:
            hook = "Be ready to state clearly what is implemented and what is intentionally not claimed."
        elif idx in {6, 10}:
            hook = "Expect follow-up questions about methodology, metrics, leakage, and whether results generalize."
        elif idx in {7, 8, 9}:
            hook = "Expect follow-up questions about failure modes, hallucination control, and policy enforcement."
        elif idx == 11:
            hook = "Expect AWS questions; keep the distinction between adapter design and deployed infrastructure crisp."
        else:
            hook = "Tie the slide back to separation of concerns and reproducible engineering behavior."
        block.append(p(hook))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 0.12 * inch))
        if idx in {4, 8}:
            story.append(PageBreak())

    doc.build(story)


if __name__ == "__main__":
    build()
