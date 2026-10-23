import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

TOTAL_QUESTIONS = 20
GENERAL_COUNT = 5
TECHNICAL_COUNT = 15


def audio_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    ext = ext if ext in {"webm", "ogg", "wav", "mp3", "m4a", "mp4"} else "webm"
    return f"audio/{instance.session.organization_id}/{instance.session_id}/{uuid.uuid4().hex}.{ext}"


class InterviewSession(models.Model):
    class Status(models.TextChoices):
        GENERATING = "generating_questions", "Generating questions"
        GENERATION_FAILED = "generation_failed", "Question generation failed"
        DRAFT = "draft", "Questions awaiting HR review"
        READY = "ready", "Approved – ready for invitation"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="interview_sessions")
    candidate = models.ForeignKey("recruitment.Candidate", on_delete=models.CASCADE, related_name="sessions")
    job = models.ForeignKey("recruitment.JobPosting", on_delete=models.CASCADE, related_name="sessions")
    analysis = models.ForeignKey("recruitment.ResumeAnalysis", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.GENERATING)
    language = models.CharField(max_length=10, default="en")
    current_index = models.PositiveSmallIntegerField(default=0)  # 0-based index of the active question
    generation_error = models.TextField(blank=True)
    ai_provider = models.CharField(max_length=60, blank=True)
    is_mock = models.BooleanField(default=False)  # questions produced in labelled mock testing mode
    questions_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    questions_approved_at = models.DateTimeField(null=True, blank=True)
    instructions_accepted_at = models.DateTimeField(null=True, blank=True)
    recording_consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    reveal_results = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"]), models.Index(fields=["job", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(current_index__lte=TOTAL_QUESTIONS), name="session_index_bounds"),
        ]

    @property
    def total_questions(self):
        return TOTAL_QUESTIONS


class InterviewInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        OPENED = "opened", "Opened"
        COMPLETED = "completed", "Completed"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="invitations")
    candidate = models.ForeignKey("recruitment.Candidate", on_delete=models.CASCADE, related_name="invitations")
    job = models.ForeignKey("recruitment.JobPosting", on_delete=models.CASCADE, related_name="invitations")
    session = models.OneToOneField(InterviewSession, on_delete=models.CASCADE, related_name="invitation")
    token_hash = models.CharField(max_length=64, unique=True)  # SHA-256 of the secret link token
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "status"])]

    def is_usable(self):
        return self.status != self.Status.REVOKED and (self.expires_at > timezone.now() or self.status == self.Status.COMPLETED)


class InterviewQuestion(models.Model):
    class Section(models.TextChoices):
        GENERAL = "general", "General"
        TECHNICAL = "technical", "Technical (resume-based)"

    class Rubric(models.TextChoices):
        BEHAVIORAL = "behavioral", "Behavioral"
        TECHNICAL = "technical", "Technical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="questions")
    index = models.PositiveSmallIntegerField()  # 0..19
    section = models.CharField(max_length=10, choices=Section.choices)
    rubric_type = models.CharField(max_length=12, choices=Rubric.choices)
    text = models.TextField()
    original_text = models.TextField(blank=True)  # AI-generated text before HR edits
    expected_points = models.JSONField(default=list)  # hidden from candidates
    skill_tags = models.JSONField(default=list)
    grounding = models.JSONField(default=list)  # resume facts the question is based on
    difficulty = models.CharField(max_length=10, blank=True)
    is_self_introduction = models.BooleanField(default=False)
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["session", "index"], name="uniq_question_index_per_session"),
            models.CheckConstraint(condition=Q(index__lt=TOTAL_QUESTIONS), name="question_index_lt_20"),
        ]


class CandidateAnswer(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNAVAILABLE = "unavailable", "Unavailable / skipped"

    class Mode(models.TextChoices):
        TEXT = "text", "Typed"
        VOICE = "voice", "Voice"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="answers")
    question = models.OneToOneField(InterviewQuestion, on_delete=models.CASCADE, related_name="answer")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
    input_mode = models.CharField(max_length=6, choices=Mode.choices, default=Mode.TEXT)
    text = models.TextField(blank=True)  # final (candidate-reviewed) answer / transcript
    transcript_source = models.CharField(max_length=20, blank=True)  # typed | browser | server_stt
    audio_file = models.FileField(upload_to=audio_upload_path, null=True, blank=True)
    audio_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    client_submission_id = models.CharField(max_length=64, blank=True)  # idempotency for network retries
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["session", "submitted_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "client_submission_id"], condition=~Q(client_submission_id=""), name="uniq_submission_id_per_session"
            )
        ]


class PendingAudio(models.Model):
    """Recording uploaded for the active question but not yet submitted as an answer."""

    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="pending_audio")
    question = models.OneToOneField(InterviewQuestion, on_delete=models.CASCADE, related_name="pending_audio")
    audio_file = models.FileField(upload_to=audio_upload_path)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    transcript = models.TextField(blank=True)
    transcript_source = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AnswerEvaluation(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Evaluation failed – retry pending"
        UNAVAILABLE = "unavailable", "Unavailable (no answer)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.OneToOneField(CandidateAnswer, on_delete=models.CASCADE, related_name="evaluation")
    status = models.CharField(max_length=12, choices=Status.choices)
    rubric_type = models.CharField(max_length=12)
    weights = models.JSONField(default=dict)
    criterion_scores = models.JSONField(default=dict)  # each 0-10
    score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # 0-10, computed server-side
    positive_points = models.JSONField(default=list)
    missing_points = models.JSONField(default=list)
    inaccuracies = models.JSONField(default=list)
    suggestions = models.JSONField(default=list)
    feedback = models.TextField(blank=True)
    evidence = models.JSONField(default=list)  # quotes from the answer supporting the scores
    confidence = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)  # 0-1
    provider = models.CharField(max_length=60, blank=True)
    is_mock = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    hr_override_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    hr_override_reason = models.TextField(blank=True)
    overridden_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(score__isnull=True) | (Q(score__gte=0) & Q(score__lte=10)), name="eval_score_0_10"),
        ]

    @property
    def effective_score(self):
        return self.hr_override_score if self.hr_override_score is not None else self.score


class InterviewReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(InterviewSession, on_delete=models.CASCADE, related_name="report")
    resume_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    general_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    overall_interview_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    band = models.CharField(max_length=40, blank=True)
    weights = models.JSONField(default=dict)
    coverage = models.JSONField(default=dict)  # answered / evaluated counts
    strengths = models.JSONField(default=list)
    knowledge_gaps = models.JSONField(default=list)
    summary = models.TextField(blank=True)
    uncertainty = models.JSONField(default=list)
    provider = models.CharField(max_length=60, blank=True)
    is_mock = models.BooleanField(default=False)
    generated_at = models.DateTimeField(auto_now=True)


class HRDecision(models.Model):
    class Decision(models.TextChoices):
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"
        ON_HOLD = "on_hold", "On Hold"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="decisions")
    candidate = models.ForeignKey("recruitment.Candidate", on_delete=models.CASCADE, related_name="decisions")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    comments = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="decisions")
    decided_at = models.DateTimeField(auto_now_add=True)
    ai_score_at_decision = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-decided_at"]
        indexes = [models.Index(fields=["session", "-decided_at"])]
