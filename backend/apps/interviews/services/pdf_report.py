"""Professional PDF candidate report (ReportLab)."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PURPLE = colors.HexColor("#5b21b6")
LIGHT = colors.HexColor("#f5f3ff")
GREY = colors.HexColor("#6b7280")
DARK = colors.HexColor("#111827")


def _p(text, style):
    return Paragraph(escape(str(text if text is not None else "")).replace("\n", "<br/>"), style)


def _fmt(v):
    return "n/a" if v is None else f"{v:.2f}".rstrip("0").rstrip(".")


def build_pdf(payload: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Interview report - {payload['candidate']['name']}", author="AI HR Recruitment & Interview System")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=PURPLE, fontSize=20, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=PURPLE, fontSize=12.5, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.2, leading=12.5, textColor=DARK)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=GREY)
    bold = ParagraphStyle("bold", parent=body, fontName="Helvetica-Bold")
    r = payload.get("report") or {}
    el = []

    el += [_p("Candidate Interview Report", h1), _p("AI HR Recruitment & Interview System", small), Spacer(1, 4),
           HRFlowable(width="100%", color=PURPLE, thickness=1.2), Spacer(1, 6)]
    if payload.get("is_mock") or r.get("is_mock"):
        el += [_p("MOCK TESTING MODE - questions/evaluations in this report were NOT produced by a real AI provider and must not be used for decisions.",
                  ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b91c1c"), fontName="Helvetica-Bold")), Spacer(1, 6)]

    date = payload.get("interview_date")
    dur = payload.get("duration_seconds")
    info = [[_p("Candidate", bold), _p(payload["candidate"]["name"], body), _p("Role", bold), _p(payload["job"]["title"], body)],
            [_p("Interview date", bold), _p(date.strftime("%d %b %Y %H:%M UTC") if date else "n/a", body),
             _p("Duration", bold), _p(f"{round(dur / 60, 1)} min" if dur else "n/a", body)]]
    t = Table(info, colWidths=[28 * mm, 58 * mm, 24 * mm, 58 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd6fe")), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el += [t, Spacer(1, 8)]

    w = r.get("weights") or {}
    rows = [[_p("Component", bold), _p("Score /100", bold), _p("Weight", bold)],
            [_p("Resume match", body), _p(_fmt(r.get("resume_score")), body), _p(f"{w.get('resume', '-')}%", body)],
            [_p("General interview", body), _p(_fmt(r.get("general_score")), body), _p(f"{w.get('general', '-')}%", body)],
            [_p("Technical interview", body), _p(_fmt(r.get("technical_score")), body), _p(f"{w.get('technical', '-')}%", body)],
            [_p("Final assessment", bold), _p(_fmt(r.get("final_score")), bold), _p("100%", bold)]]
    st = Table(rows, colWidths=[70 * mm, 50 * mm, 48 * mm])
    st.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#e5e7eb")),
                            ("BACKGROUND", (0, -1), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd6fe"))]))
    el += [_p("Scores", h2), st, Spacer(1, 4), _p(f"Assessment band (advisory): {r.get('band', 'n/a')}", bold)]
    el += [_p("The band is an advisory indicator only. It does not select or reject a candidate.", small)]

    el += [_p("Strengths", h2)]
    el += [_p("- " + f"{s['skill']} (avg {s['avg_score']}/10, Q{', Q'.join(map(str, s['questions']))})", body) for s in r.get("strengths", [])] or [_p("None identified from the available evidence.", body)]
    el += [_p("Areas for improvement", h2)]
    for g in r.get("knowledge_gaps", []) or []:
        extra = (" - " + "; ".join(g.get("missing_points", [])[:2])) if g.get("missing_points") else ""
        el.append(_p(f"- {g['skill']} (avg {g['avg_score']}/10){extra}", body))
    if not r.get("knowledge_gaps"):
        el.append(_p("None identified from the available evidence.", body))

    el += [_p("AI-generated summary", h2), _p(r.get("summary", "Report not generated yet."), body), Spacer(1, 3)]
    el += [_p("Uncertainty and limitations", h2)] + [_p("- " + u, small) for u in r.get("uncertainty", [])]
    c = r.get("coverage") or {}
    if c:
        el.append(_p(f"Coverage: {c.get('evaluated', 0)} of {c.get('questions', 20)} answers evaluated, {c.get('unavailable', 0)} unavailable, {c.get('failed', 0)} pending/failed.", small))

    ec = payload.get("evaluation_criteria", {})
    el += [_p("Evaluation criteria", h2)]
    for kind, ws in ec.get("answer_weights", {}).items():
        el.append(_p(f"{kind.title()} questions: " + ", ".join(f"{k.replace('_', ' ')} {v}%" for k, v in ws.items()), small))

    el += [_p("Question-by-question breakdown", h2)]
    for q in payload.get("questions", []):
        ev, ans = q.get("evaluation"), q.get("answer")
        score = "unavailable" if not ev or ev["status"] != "completed" else f"{_fmt(ev['effective_score'])}/10"
        block = [_p(f"Q{q['number']} ({q['section']}) - Score: {score}", bold), _p(q["question"], body)]
        if ans:
            txt = ans["text"] or "(no answer / not transcribed)"
            block.append(_p("Answer: " + (txt[:900] + ("..." if len(txt) > 900 else "")), small))
        if ev and ev["status"] == "completed":
            if ev["positive_points"]:
                block.append(_p("Strong points: " + "; ".join(ev["positive_points"][:4]), small))
            if ev["missing_points"]:
                block.append(_p("Missing: " + "; ".join(ev["missing_points"][:4]), small))
            if ev["inaccuracies"]:
                block.append(_p("Potential inaccuracies: " + "; ".join(ev["inaccuracies"][:3]), small))
            if ev["feedback"]:
                block.append(_p("Feedback: " + ev["feedback"], small))
            if ev["hr_override_score"] is not None:
                block.append(_p(f"HR-adjusted score: {_fmt(ev['hr_override_score'])}/10 - {ev['hr_override_reason']}", small))
            block.append(_p(f"AI confidence: {_fmt(ev['confidence'])}", small))
        block += [Spacer(1, 3), HRFlowable(width="100%", color=colors.HexColor("#e5e7eb"), thickness=0.4), Spacer(1, 3)]
        el.append(KeepTogether(block))

    el += [_p("Final HR decision", h2)]
    d = payload.get("latest_decision")
    if d:
        el += [_p(f"Decision: {d['decision'].replace('_', ' ').title()}", bold), _p(f"Decided by: {d['decided_by']}", body),
               _p(f"Decided at: {d['decided_at'].strftime('%d %b %Y %H:%M UTC')}", body), _p("HR comments: " + (d["comments"] or "-"), body)]
    else:
        el.append(_p("No decision has been recorded yet. A decision (Selected / Rejected / On Hold) must be entered by an authorised HR user.", body))
    el += [Spacer(1, 8), _p(payload.get("advisory_notice", ""), small)]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, "Confidential - contains personal data. AI scores are advisory only.")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
