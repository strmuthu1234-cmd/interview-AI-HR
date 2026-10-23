"""Resume processing pipeline: extract -> parse -> score -> propose shortlist."""
import copy
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.ai.client import get_resume_client
from apps.ai.errors import AIProviderError
from apps.core.defaults import get_org_settings

from ..models import Candidate, ResumeAnalysis, ScreeningBatch, Shortlist, ShortlistEntry
from . import resume_ai
from .resume_parser import parse_resume
from .sanitize import detect_injection
from .screening import build_summary, score_resume
from .text_extraction import ExtractionError, extract_text

log = logging.getLogger(__name__)


def process_resume(resume):
    """Extract text, parse the profile and score. Never raises for bad files."""
    candidate = resume.candidate
    try:
        resume.file.open("rb")
        try:
            data = resume.file.read()
        finally:
            resume.file.close()
        text = extract_text(resume.file_type, data)
    except ExtractionError as exc:
        resume.parse_status, resume.parse_error = resume.ParseStatus.FAILED, str(exc)
        resume.save(update_fields=["parse_status", "parse_error"])
        return False
    except Exception as exc:  # corrupt files must not break the batch
        log.exception("Unexpected extraction failure for %s", resume.pk)
        resume.parse_status, resume.parse_error = resume.ParseStatus.FAILED, f"Could not read file: {exc.__class__.__name__}"
        resume.save(update_fields=["parse_status", "parse_error"])
        return False

    safe_text, flags = detect_injection(text)
    profile = parse_resume(safe_text)
    client = get_resume_client(resume.organization)
    if client is not None and not client.is_mock:
        profile = resume_ai.extract_missing_sections(client, safe_text, profile.get("name", ""), profile)

    resume.extracted_text = text
    resume.security_flags = flags
    resume.parsed_data = profile
    resume.extraction_method = profile.get("extraction_method", "rule_based")
    resume.parse_status, resume.parse_error = resume.ParseStatus.PARSED, ""
    resume.save()

    candidate.profile = copy.deepcopy(profile)
    candidate.full_name = profile.get("name") or resume.original_filename.rsplit(".", 1)[0][:200]
    candidate.email = profile.get("email", "")[:254]
    candidate.phone = profile.get("phone", "")[:40]
    if candidate.email:
        dup = (Candidate.objects.filter(job=candidate.job, email__iexact=candidate.email).exclude(pk=candidate.pk)
               .order_by("created_at").first())
        if dup and dup.created_at <= candidate.created_at:
            candidate.profile["duplicate_of"] = str(dup.pk)
    candidate.save()
    analyze_resume(resume)
    return True


@transaction.atomic
def analyze_resume(resume):
    """(Re)score a parsed resume against its job using the org's current rubric."""
    candidate, job, org = resume.candidate, resume.job, resume.organization
    org_settings = get_org_settings(org)
    weights = org_settings["screening_weights"]
    text, _ = detect_injection(resume.extracted_text)
    result = score_resume(candidate.profile, text, job, weights)
    method, provider, limitations, summary = "rule_based", "", list(result["limitations"]), None
    client = get_resume_client(org)
    if client is not None and not client.is_mock:
        names = [p.get("name", "") for p in candidate.profile.get("projects", [])] or [e.get("header", "") for e in candidate.profile.get("experience", [])]
        try:
            ai = resume_ai.enhance_analysis(client, job, candidate.full_name, text, result, names)
            method, provider = "ai_assisted", client.label()
            summary = ai["summary"] or None
            limitations += ai["limitations"]
            if ai["project_ratings"]:
                top = sorted(ai["project_ratings"], key=lambda r: r["rating"], reverse=True)[:3]
                ai_score = min(100.0, sum(r["rating"] for r in top) / 3 * 10)
                pcat = result["category_scores"]["projects"]
                if pcat["score"] is not None:
                    pcat["detail"]["keyword_score"] = pcat["score"]
                    pcat["detail"]["ai_ratings"] = ai["project_ratings"]
                    pcat["score"] = round((pcat["score"] + ai_score) / 2, 2)
                    _recompute_total(result)
        except AIProviderError as exc:
            limitations.append(f"AI enrichment unavailable for this resume ({exc.__class__.__name__}); score is fully rule-based.")
    elif client is None:
        limitations.append("AI narrative not generated (AI resume processing is off); the score is fully rule-based and deterministic.")
    if resume.security_flags:
        limitations.append(f"{len(resume.security_flags)} line(s) resembling instructions to an AI system were found and ignored.")

    ResumeAnalysis.objects.filter(resume=resume, is_current=True).update(is_current=False)
    analysis = ResumeAnalysis.objects.create(
        organization=org, resume=resume, candidate=candidate, job=job, rubric=weights,
        category_scores=result["category_scores"], match_score=Decimal(str(result["match_score"])),
        matching_skills=result["matching_skills"], missing_required_skills=result["missing_required_skills"],
        relevant_projects=result["relevant_projects"], experience_alignment=result["experience_alignment"],
        evidence=result["evidence"], limitations=limitations,
        summary=summary or build_summary(job, result), method=method, provider=provider,
    )
    if candidate.status == Candidate.Status.NEW:
        candidate.status = Candidate.Status.SCREENED
        candidate.save(update_fields=["status"])
    return analysis


def _recompute_total(result):
    cats = result["category_scores"]
    applicable = {k: v for k, v in cats.items() if v["applicable"]}
    wsum = sum(v["weight"] for v in applicable.values()) or 1
    total = 0.0
    for v in applicable.values():
        v["effective_weight"] = round(100 * v["weight"] / wsum, 2)
        total += v["score"] * v["weight"] / wsum
    result["match_score"] = round(min(100.0, max(0.0, total)), 2)


@transaction.atomic
def propose_shortlist(job):
    """Create/refresh the proposed shortlist: top-N analysed, non-duplicate candidates by score."""
    sl, _ = Shortlist.objects.get_or_create(job=job, status=Shortlist.Status.PROPOSED, defaults={"organization": job.organization})
    sl.entries.all().delete()
    analyses = (ResumeAnalysis.objects.filter(job=job, is_current=True, candidate__status=Candidate.Status.SCREENED)
                .select_related("candidate"))
    ranked = [a for a in analyses if not a.candidate.profile.get("duplicate_of")]
    ranked.sort(key=lambda a: (-float(a.effective_score), -len(a.matching_skills), a.candidate.created_at))
    for i, a in enumerate(ranked[: job.shortlist_size], start=1):
        ShortlistEntry.objects.create(shortlist=sl, candidate=a.candidate, analysis=a, rank=i)
    sl.save()
    return sl


def record_resume_done(batch_id, ok: bool):
    ScreeningBatch.objects.filter(pk=batch_id).update(
        **({"processed_count": F("processed_count") + 1} if ok else {"failed_count": F("failed_count") + 1})
    )
    batch = ScreeningBatch.objects.get(pk=batch_id)
    accepted = batch.resumes.count()
    if batch.processed_count + batch.failed_count >= accepted and batch.status == ScreeningBatch.Status.PROCESSING:
        batch.status = ScreeningBatch.Status.COMPLETED if batch.processed_count else ScreeningBatch.Status.FAILED
        batch.completed_at = timezone.now()
        batch.save(update_fields=["status", "completed_at"])
        if batch.processed_count:
            propose_shortlist(batch.job)
