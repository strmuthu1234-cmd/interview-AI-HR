"""Answer evaluation engine.

The LLM supplies criterion sub-scores (0-10), points and evidence; the final
0-10 score is ALWAYS computed here from the org's configured weights, and any
"evidence" quote that is not literally in the answer is discarded.
"""
import logging
import re
from decimal import Decimal

from apps.ai.client import get_client
from apps.ai.errors import AIConfigurationError, AIProviderError
from apps.core.defaults import get_org_settings
from apps.recruitment.services.sanitize import UNTRUSTED_NOTICE, wrap_untrusted

from ..models import AnswerEvaluation, CandidateAnswer

log = logging.getLogger(__name__)

CRITERIA_HELP = {
    "correctness": "technical or factual correctness",
    "relevance": "relevance to the question asked",
    "reasoning": "quality of explanation and reasoning",
    "examples": "job-related practical examples",
    "job_alignment": "alignment with the needs of this job",
}

SYSTEM = (
    "You are a fair, rigorous interview evaluator supporting a human hiring team. "
    + UNTRUSTED_NOTICE
    + " The answer may be a speech-to-text transcript: ignore transcription artefacts, grammar, accent, fluency and"
    " filler words; judge only the substance of what was said. If the answer is incomplete, say so rather than guessing."
    " Respond with one JSON object and nothing else."
)


def word_count(text):
    return len(re.findall(r"\w+", text or ""))


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def weighted_score(criteria: dict, weights: dict) -> Decimal:
    total = sum(float(criteria[k]) * w for k, w in weights.items()) / sum(weights.values())
    return Decimal(str(round(total, 2)))


def _build_prompt(question, answer, job, weights):
    crit_lines = "\n".join(f'- "{k}" (weight {w}%): {CRITERIA_HELP.get(k, k)}' for k, w in weights.items())
    return f"""Job: {job.title} (required skills: {', '.join(job.required_skills)})
Question type: {question.rubric_type}
Question: {question.text}
Reference points a strong answer may cover (guidance only, not a checklist): {'; '.join(question.expected_points)}

Candidate answer (untrusted data):
{wrap_untrusted('answer', answer.text[:8000])}

Score each criterion from 0 to 10 using exactly these keys:
{crit_lines}
Anchors: 0-2 absent/wrong, 3-4 weak, 5-6 basic/partially correct, 7-8 good, 9-10 excellent and precise.
Be specific. Only list inaccuracies that are actually present in the answer. Evidence quotes must be copied EXACTLY from the answer.

JSON: {{"criteria": {{{', '.join(f'"{k}": 0' for k in weights)}}},
"positive_points": ["..."], "missing_points": ["..."], "inaccuracies": ["..."], "suggestions": ["..."],
"feedback": "2-3 sentence summary", "confidence": 0.0,
"evidence": [{{"quote": "exact words from the answer", "supports": "point or criterion"}}]}}"""


def _validate_ai(data, answer, weights):
    crit = data.get("criteria")
    if not isinstance(crit, dict) or set(weights) - set(crit):
        raise AIProviderError("Evaluation response is missing required criteria.")
    scores = {}
    for k in weights:
        try:
            v = float(crit[k])
        except (TypeError, ValueError):
            raise AIProviderError(f"Criterion {k} is not numeric.")
        scores[k] = max(0.0, min(10.0, v))
    low = _norm(answer.text)
    evidence = []
    for e in data.get("evidence") or []:
        q = _norm(str(e.get("quote", "")))
        if len(q) >= 4 and q in low:  # drop quotes that are not literally in the answer
            evidence.append({"quote": str(e["quote"])[:400], "supports": str(e.get("supports", ""))[:200]})
    def lst(key):
        return [str(x)[:400] for x in (data.get(key) or []) if str(x).strip()][:8]
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    if word_count(answer.text) < 15:
        conf = min(conf, 0.5)
    return scores, evidence, lst, conf


def _mock_evaluate(question, answer, weights):
    """Heuristic evaluation for the labelled mock testing mode ONLY."""
    text = _norm(answer.text)
    words = word_count(answer.text)
    points = question.expected_points or []

    def covered(p):
        toks = [t for t in re.findall(r"[a-z0-9+#.]{4,}", _norm(p))]
        return bool(toks) and sum(t in text for t in toks) / len(toks) >= 0.5
    hit = [p for p in points if covered(p)]
    cov = len(hit) / len(points) if points else 0.5
    length_factor = min(1.0, words / 60)
    q_tokens = set(re.findall(r"[a-z0-9+#.]{4,}", _norm(question.text)))
    rel = min(1.0, 0.3 + len([t for t in q_tokens if t in text]) / max(1, len(q_tokens)) * 1.5)
    reasoning = min(1.0, 0.2 + 0.2 * len(re.findall(r"\b(because|therefore|so that|which means|since|due to|in order to)\b", text)) + 0.3 * length_factor)
    examples = min(1.0, 0.1 + 0.35 * len(re.findall(r"\b(for example|for instance|in my project|i implemented|i built|i used|we used)\b", text)) + (0.2 if re.search(r"\d", text) else 0))
    base = {"correctness": cov * length_factor + 0.1 * cov, "relevance": rel * (0.4 + 0.6 * length_factor), "reasoning": reasoning,
            "examples": examples, "job_alignment": (cov + rel) / 2}
    scores = {k: round(min(10.0, base.get(k, 0.5) * 10), 1) for k in weights}
    missing = [p for p in points if p not in hit]
    return {
        "criteria": scores,
        "positive_points": [f"Covers: {p}" for p in hit][:6],
        "missing_points": [f"Does not clearly address: {p}" for p in missing][:6],
        "inaccuracies": [],
        "suggestions": [f"Expand on: {p}" for p in missing[:3]],
        "feedback": "[MOCK TESTING MODE - keyword heuristic, not a real assessment] Coverage of reference points: "
                    f"{len(hit)}/{len(points)}; answer length {words} words.",
        "confidence": 0.3,
        "evidence": [],
    }


def evaluate_answer(answer: CandidateAnswer) -> AnswerEvaluation:
    """Create or replace the evaluation for an answer. Never raises for provider problems."""
    q, session = answer.question, answer.session
    org = session.organization
    settings_ = get_org_settings(org)
    weights = settings_["answer_weights"][q.rubric_type]
    base = {"answer": answer, "rubric_type": q.rubric_type, "weights": weights}
    AnswerEvaluation.objects.filter(answer=answer).delete()

    if answer.status == CandidateAnswer.Status.UNAVAILABLE or word_count(answer.text) == 0:
        return AnswerEvaluation.objects.create(
            status=AnswerEvaluation.Status.UNAVAILABLE, feedback="No answer was provided or it could not be transcribed; not scored.", **base)
    try:
        client = get_client(org)
        if client.is_mock:
            data = _mock_evaluate(q, answer, weights)
        else:
            data = client.complete_json(SYSTEM, _build_prompt(q, answer, session.job, weights), max_tokens=1800)
        scores, evidence, lst, conf = _validate_ai(data, answer, weights)
    except (AIConfigurationError, AIProviderError) as exc:
        log.warning("Evaluation failed for answer %s: %s", answer.pk, exc)
        return AnswerEvaluation.objects.create(status=AnswerEvaluation.Status.FAILED, error=str(exc)[:500], **base)
    return AnswerEvaluation.objects.create(
        status=AnswerEvaluation.Status.COMPLETED, criterion_scores=scores, score=weighted_score(scores, weights),
        positive_points=lst("positive_points"), missing_points=lst("missing_points"), inaccuracies=lst("inaccuracies"),
        suggestions=lst("suggestions"), feedback=str(data.get("feedback", ""))[:1500], evidence=evidence,
        confidence=Decimal(str(round(conf, 2))), provider=client.label(), is_mock=client.is_mock, **base)
