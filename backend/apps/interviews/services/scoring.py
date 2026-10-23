"""Final assessment scoring and report generation (deterministic numbers, AI narrative optional).

Final = 20% resume + 15% general + 65% technical (configurable), each normalised to 0-100.
Bands are advisory only; nothing here accepts or rejects a candidate.
"""
import logging
from collections import defaultdict
from decimal import Decimal

from apps.ai.client import get_client
from apps.ai.errors import AIConfigurationError, AIProviderError
from apps.core.defaults import band_for, get_org_settings
from apps.recruitment.models import ResumeAnalysis
from apps.recruitment.services import skills as sk
from apps.recruitment.services.sanitize import UNTRUSTED_NOTICE

from ..models import AnswerEvaluation, InterviewReport, InterviewSession

log = logging.getLogger(__name__)


def _avg100(evals):
    scores = [float(e.effective_score) for e in evals if e.effective_score is not None and e.status == AnswerEvaluation.Status.COMPLETED]
    return round(sum(scores) / len(scores) * 10, 2) if scores else None


def combine(resume, general, technical, weights):
    """Weighted final score. Missing components are excluded and weights renormalised (and flagged by caller)."""
    parts = {"resume": resume, "general": general, "technical": technical}
    avail = {k: v for k, v in parts.items() if v is not None and weights.get(k, 0) > 0}
    if not avail:
        return None
    wsum = sum(weights[k] for k in avail)
    return round(sum(v * weights[k] for k, v in avail.items()) / wsum, 2)


def compute_scores(session):
    org_settings = get_org_settings(session.organization)
    qs = list(session.questions.select_related("answer__evaluation").order_by("index"))
    evals = {}
    for q in qs:
        ans = getattr(q, "answer", None)
        ev = getattr(ans, "evaluation", None) if ans else None
        evals[q.index] = (q, ans, ev)
    general = [ev for q, a, ev in evals.values() if q.section == "general" and ev]
    technical = [ev for q, a, ev in evals.values() if q.section == "technical" and ev]
    analysis = session.analysis or ResumeAnalysis.objects.filter(candidate=session.candidate, is_current=True).first()
    resume_score = float(analysis.effective_score) if analysis else None
    g, t = _avg100(general), _avg100(technical)
    weights = org_settings["final_weights"]
    final = combine(resume_score, g, t, weights)
    interview_scores = [float(e.effective_score) for e in general + technical if e.status == "completed" and e.effective_score is not None]
    overall_interview = round(sum(interview_scores) / len(interview_scores) * 10, 2) if interview_scores else None

    by_skill = defaultdict(list)
    for q, a, ev in evals.values():
        if q.section == "technical" and ev and ev.status == "completed" and ev.effective_score is not None:
            # group aliases ("React" / "React.js") under one display name; one question counts once per skill
            tags = {sk.display_name(sk.canonical(t)) if sk.canonical(t) in sk.TAXONOMY else t for t in (q.skill_tags or ["General technical"])}
            for tag in tags:
                by_skill[tag].append((float(ev.effective_score), q.index + 1))
    skill_avgs = [{"skill": s, "avg_score": round(sum(v for v, _ in vs) / len(vs), 1), "questions": [i for _, i in vs]} for s, vs in by_skill.items()]
    strengths = sorted([s for s in skill_avgs if s["avg_score"] >= 7], key=lambda s: -s["avg_score"])[:6]
    gaps = sorted([s for s in skill_avgs if s["avg_score"] <= 5], key=lambda s: s["avg_score"])[:6]
    for s in gaps:  # attach concrete missing points as evidence
        pts = []
        for q, a, ev in evals.values():
            q_tags = {sk.display_name(sk.canonical(t)) if sk.canonical(t) in sk.TAXONOMY else t for t in (q.skill_tags or [])}
            if ev and s["skill"] in q_tags and ev.missing_points:
                pts += ev.missing_points[:2]
        s["missing_points"] = pts[:4]

    n_total = len(qs)
    statuses = [ev.status if ev else "none" for _, _, ev in evals.values()]
    coverage = {"questions": n_total, "answered": sum(1 for _, a, _ in evals.values() if a and a.status == "submitted"),
                "evaluated": statuses.count("completed"), "unavailable": statuses.count("unavailable"),
                "failed": statuses.count("failed") + statuses.count("none")}
    uncertainty = ["AI scores are decision-support only; the final selection decision is made by an authorised HR user."]
    if coverage["failed"]:
        uncertainty.append(f"{coverage['failed']} answer(s) could not be evaluated yet and are excluded from the scores.")
    if coverage["unavailable"]:
        uncertainty.append(f"{coverage['unavailable']} answer(s) were skipped or unavailable and are excluded from the scores.")
    if resume_score is None:
        uncertainty.append("No resume analysis was available; the final score uses interview components only.")
    if g is None or t is None:
        uncertainty.append("A score component is missing; weights were renormalised over the available components.")
    low_conf = sum(1 for ev in general + technical if ev.confidence is not None and float(ev.confidence) < 0.5 and ev.status == "completed")
    if low_conf:
        uncertainty.append(f"{low_conf} evaluation(s) have low confidence (short or unclear answers) - review transcripts.")
    if any(ev.is_mock for ev in general + technical) or session.is_mock:
        uncertainty.append("MOCK TESTING MODE: questions/evaluations came from the mock provider and are not a real assessment.")
    if any(ev.hr_override_score is not None for ev in general + technical):
        uncertainty.append("Some answer scores were adjusted by HR.")
    return {
        "resume_score": resume_score, "general_score": g, "technical_score": t, "overall_interview_score": overall_interview,
        "final_score": final, "band": band_for(final, org_settings) if final is not None else "Not available",
        "weights": weights, "coverage": coverage, "strengths": strengths, "knowledge_gaps": gaps, "uncertainty": uncertainty,
    }


def _template_summary(session, s):
    c = s["coverage"]
    parts = [f"Final assessment {s['final_score']}/100 ({s['band']}) for {session.job.title}: resume {s['resume_score']}, general interview {s['general_score']}, technical interview {s['technical_score']}."
             if s["final_score"] is not None else "A final score could not be calculated from the available data."]
    parts.append(f"{c['evaluated']} of {c['questions']} answers were evaluated.")
    if s["strengths"]:
        parts.append("Stronger areas: " + ", ".join(f"{x['skill']} ({x['avg_score']}/10)" for x in s["strengths"][:3]) + ".")
    if s["knowledge_gaps"]:
        parts.append("Weaker areas: " + ", ".join(f"{x['skill']} ({x['avg_score']}/10)" for x in s["knowledge_gaps"][:3]) + ".")
    return " ".join(parts)


def _ai_summary(client, session, s):
    rows = []
    for q in session.questions.select_related("answer__evaluation").order_by("index"):
        ev = getattr(getattr(q, "answer", None), "evaluation", None)
        if ev and ev.status == "completed":
            rows.append(f"Q{q.index + 1} [{q.section}] score {ev.effective_score}/10 tags {q.skill_tags}: {ev.feedback[:240]}")
    user = f"""Role: {session.job.title}
Scores (0-100): resume {s['resume_score']}, general {s['general_score']}, technical {s['technical_score']}, final {s['final_score']} ({s['band']}).
Coverage: {s['coverage']}
Skill averages - strengths: {s['strengths']}; gaps: {s['knowledge_gaps']}
Per-question evaluations (data):
""" + "\n".join(rows[:20]) + """

Write a balanced summary for the hiring manager in at most 170 words: key strengths and gaps with reference to question numbers,
and explicitly state the main uncertainties. Do not recommend hiring or rejecting. JSON: {"summary": "..."}"""
    data = client.complete_json("You summarise interview evaluation data for a human hiring team. " + UNTRUSTED_NOTICE + " Respond with JSON only.", user, max_tokens=700)
    text = str(data.get("summary", "")).strip()
    if len(text) < 30:
        raise AIProviderError("Summary too short")
    return text[:1500]


def build_report(session: InterviewSession) -> InterviewReport:
    s = compute_scores(session)
    summary, provider, is_mock = None, "", False
    try:
        client = get_client(session.organization)
        is_mock = client.is_mock
        if client.is_mock:
            summary = "[MOCK TESTING MODE] " + _template_summary(session, s)
        else:
            summary, provider = _ai_summary(client, session, s), client.label()
    except (AIConfigurationError, AIProviderError) as exc:
        s["uncertainty"].append("AI narrative unavailable; summary generated from scores only.")
        log.warning("Report summary fallback: %s", exc)
    summary = summary or _template_summary(session, s)
    d = lambda v: None if v is None else Decimal(str(v))
    report, _ = InterviewReport.objects.update_or_create(
        session=session,
        defaults=dict(resume_score=d(s["resume_score"]), general_score=d(s["general_score"]), technical_score=d(s["technical_score"]),
                      overall_interview_score=d(s["overall_interview_score"]), final_score=d(s["final_score"]), band=s["band"], weights=s["weights"],
                      coverage=s["coverage"], strengths=s["strengths"], knowledge_gaps=s["knowledge_gaps"], summary=summary,
                      uncertainty=s["uncertainty"], provider=provider, is_mock=is_mock or session.is_mock),
    )
    return report
