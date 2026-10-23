import logging

from celery import shared_task

from .models import JobPosting, Resume
from .services import pipeline

log = logging.getLogger(__name__)


@shared_task
def process_resume_task(resume_id):
    resume = Resume.objects.select_related("candidate", "job", "organization").get(pk=resume_id)
    ok = False
    try:
        ok = pipeline.process_resume(resume)
    except Exception:  # keep the batch moving; error is recorded on the resume
        log.exception("Resume %s failed", resume_id)
        resume.parse_status, resume.parse_error = Resume.ParseStatus.FAILED, "Unexpected processing error."
        resume.save(update_fields=["parse_status", "parse_error"])
    if resume.batch_id:
        pipeline.record_resume_done(resume.batch_id, ok)
    return ok


@shared_task
def reanalyze_job_task(job_id, batch_id=None):
    """Re-score every parsed resume of a job (e.g. after rubric or profile changes)."""
    job = JobPosting.objects.get(pk=job_id)
    qs = Resume.objects.filter(job=job, parse_status=Resume.ParseStatus.PARSED).select_related("candidate", "job", "organization")
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    n = 0
    for resume in qs:
        pipeline.analyze_resume(resume)
        n += 1
    pipeline.propose_shortlist(job)
    return n
