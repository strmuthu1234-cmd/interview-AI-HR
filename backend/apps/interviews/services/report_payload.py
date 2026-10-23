"""Assemble the HR-facing report data used by the JSON API, PDF export, comparison and CSV."""
import csv
import io

from apps.core.defaults import get_org_settings

from ..models import HRDecision, InterviewReport, InterviewSession

CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _f(v):
    return None if v is None else float(v)


def evaluation_dict(ev):
    if ev is None:
        return None
    return {
        "status": ev.status, "score": _f(ev.score), "effective_score": _f(ev.effective_score), "criterion_scores": ev.criterion_scores,
        "weights": ev.weights, "positive_points": ev.positive_points, "missing_points": ev.missing_points, "inaccuracies": ev.inaccuracies,
        "suggestions": ev.suggestions, "feedback": ev.feedback, "evidence": ev.evidence, "confidence": _f(ev.confidence),
        "provider": ev.provider, "is_mock": ev.is_mock, "error": ev.error, "hr_override_score": _f(ev.hr_override_score),
        "hr_override_reason": ev.hr_override_reason,
    }


def question_rows(session):
    rows = []
    for q in session.questions.select_related("answer__evaluation").order_by("index"):
        ans = getattr(q, "answer", None)
        ev = getattr(ans, "evaluation", None) if ans else None
        rows.append({
            "number": q.index + 1, "section": q.section, "rubric_type": q.rubric_type, "question": q.text, "expected_points": q.expected_points,
            "skill_tags": q.skill_tags, "difficulty": q.difficulty,
            "answer": None if ans is None else {
                "id": str(ans.id), "text": ans.text, "status": ans.status, "input_mode": ans.input_mode, "transcript_source": ans.transcript_source,
                "has_audio": bool(ans.audio_file), "audio_duration_seconds": ans.audio_duration_seconds, "submitted_at": ans.submitted_at,
            },
            "evaluation": evaluation_dict(ev),
        })
    return rows


def decision_dict(d):
    return {"id": str(d.id), "decision": d.decision, "comments": d.comments, "decided_by": d.decided_by.get_full_name() or d.decided_by.get_username(),
            "decided_at": d.decided_at, "ai_score_at_decision": _f(d.ai_score_at_decision)}


def report_payload(session: InterviewSession, with_questions=True):
    try:
        r = session.report
    except InterviewReport.DoesNotExist:
        r = None
    decisions = list(session.decisions.select_related("decided_by"))
    settings_ = get_org_settings(session.organization)
    out = {
        "session_id": str(session.id), "candidate": {"id": str(session.candidate_id), "name": session.candidate.full_name, "email": session.candidate.email},
        "job": {"id": str(session.job_id), "title": session.job.title, "department": session.job.department},
        "status": session.status, "interview_date": session.completed_at or session.started_at, "duration_seconds": session.duration_seconds,
        "recording_consent": session.recording_consent, "is_mock": session.is_mock,
        "report": None if r is None else {
            "resume_score": _f(r.resume_score), "general_score": _f(r.general_score), "technical_score": _f(r.technical_score),
            "overall_interview_score": _f(r.overall_interview_score), "final_score": _f(r.final_score), "band": r.band, "weights": r.weights,
            "coverage": r.coverage, "strengths": r.strengths, "knowledge_gaps": r.knowledge_gaps, "summary": r.summary,
            "uncertainty": r.uncertainty, "provider": r.provider, "is_mock": r.is_mock, "generated_at": r.generated_at,
        },
        "evaluation_criteria": {"answer_weights": settings_["answer_weights"], "final_weights": settings_["final_weights"], "bands": settings_["bands"]},
        "decisions": [decision_dict(d) for d in decisions],
        "latest_decision": decision_dict(decisions[0]) if decisions else None,
        "advisory_notice": "AI scores and bands are decision-support only. The final decision is made and recorded by an authorised HR user.",
    }
    if with_questions:
        out["questions"] = question_rows(session)
    return out


def _safe_cell(v):
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(CSV_DANGEROUS) else s


def sessions_csv(sessions):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Candidate", "Email", "Job", "Resume score", "General interview", "Technical interview", "Final score", "Assessment band",
                "HR decision", "Decided by", "Decided at", "Interview date", "Duration (min)", "Mock mode"])
    for s in sessions:
        p = report_payload(s, with_questions=False)
        r, d = p["report"] or {}, p["latest_decision"] or {}
        w.writerow([_safe_cell(x) for x in [
            p["candidate"]["name"], p["candidate"]["email"], p["job"]["title"], r.get("resume_score"), r.get("general_score"),
            r.get("technical_score"), r.get("final_score"), r.get("band"), d.get("decision", "pending"), d.get("decided_by"),
            d.get("decided_at"), p["interview_date"], round(s.duration_seconds / 60, 1) if s.duration_seconds else "", "yes" if p["is_mock"] else "no"]])
    return buf.getvalue()
