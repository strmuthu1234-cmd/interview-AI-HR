import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

log = logging.getLogger(__name__)


@shared_task
def purge_expired_data():
    """Apply each organisation's retention policy (audio, resumes, completed interviews)."""
    from apps.accounts.models import Organization
    from apps.core.defaults import get_org_settings
    from apps.interviews.models import CandidateAnswer, InterviewSession
    from apps.recruitment.models import Resume

    now = timezone.now()
    stats = {"audio": 0, "resumes": 0, "sessions": 0}
    for org in Organization.objects.all():
        r = get_org_settings(org)["retention"]
        for ans in CandidateAnswer.objects.filter(session__organization=org, audio_file__gt="",
                                                  submitted_at__lt=now - timedelta(days=r["audio_days"])):
            ans.audio_file.delete(save=False)
            ans.audio_file = None
            ans.save(update_fields=["audio_file"])
            stats["audio"] += 1
        for res in Resume.objects.filter(organization=org, uploaded_at__lt=now - timedelta(days=r["resume_days"])):
            res.file.delete(save=False)
            res.file = ""
            res.extracted_text = ""
            res.save(update_fields=["file", "extracted_text"])
            stats["resumes"] += 1
        old = InterviewSession.objects.filter(organization=org, completed_at__lt=now - timedelta(days=r["interview_days"]))
        stats["sessions"] += old.count()
        old.delete()
    log.info("Retention purge: %s", stats)
    return stats
