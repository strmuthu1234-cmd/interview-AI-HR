import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


def resume_upload_path(instance, filename):
    # Never trust the user-supplied name for the storage path.
    ext = "pdf" if filename.lower().endswith(".pdf") else "docx"
    return f"resumes/{instance.organization_id}/{uuid.uuid4().hex}.{ext}"


class JobPosting(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    required_skills = models.JSONField(default=list)
    preferred_skills = models.JSONField(default=list, blank=True)
    min_experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    max_experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    responsibilities = models.TextField(blank=True)
    mandatory_qualifications = models.JSONField(default=list, blank=True)
    shortlist_size = models.PositiveSmallIntegerField(default=10)
    interview_duration_minutes = models.PositiveSmallIntegerField(default=45)
    interview_language = models.CharField(max_length=10, default="en")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(shortlist_size__gte=1) & Q(shortlist_size__lte=50), name="job_shortlist_size_1_50"),
            models.CheckConstraint(condition=Q(min_experience_years__gte=0), name="job_min_exp_nonneg"),
        ]

    def __str__(self):
        return self.title


class ScreeningBatch(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="batches")
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="batches")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    total_files = models.PositiveSmallIntegerField(default=0)
    rejected_files = models.JSONField(default=list, blank=True)  # [{filename, reason}]
    processed_count = models.PositiveSmallIntegerField(default=0)
    failed_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["job", "-created_at"])]


class Candidate(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        SCREENED = "screened", "Screened"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW_INVITED = "interview_invited", "Interview invited"
        INTERVIEWING = "interviewing", "Interview in progress"
        INTERVIEWED = "interviewed", "Interview completed"
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"
        ON_HOLD = "on_hold", "On hold"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="candidates")
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="candidates")
    batch = models.ForeignKey(ScreeningBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="candidates")
    full_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    # Structured profile (HR-correctable). Original parser output stays on Resume.parsed_data.
    profile = models.JSONField(default=dict, blank=True)
    profile_corrected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    profile_corrected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "job", "status"]),
            models.Index(fields=["job", "email"]),
        ]

    def __str__(self):
        return self.full_name or f"Candidate {str(self.id)[:8]}"


class Resume(models.Model):
    class ParseStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="resumes")
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="resumes")
    batch = models.ForeignKey(ScreeningBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="resumes")
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name="resume")
    file = models.FileField(upload_to=resume_upload_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=5)  # pdf | docx
    file_size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    extracted_text = models.TextField(blank=True)
    parse_status = models.CharField(max_length=10, choices=ParseStatus.choices, default=ParseStatus.PENDING)
    parse_error = models.TextField(blank=True)
    parsed_data = models.JSONField(default=dict, blank=True)  # original parser output (never edited)
    extraction_method = models.CharField(max_length=20, blank=True)
    security_flags = models.JSONField(default=list, blank=True)  # e.g. prompt-injection attempts
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        constraints = [models.UniqueConstraint(fields=["job", "sha256"], name="uniq_resume_per_job_hash")]
        indexes = [models.Index(fields=["batch", "parse_status"])]


class ResumeAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="analyses")
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="analyses")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="analyses")
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="analyses")
    is_current = models.BooleanField(default=True)
    rubric = models.JSONField(default=dict)  # weights snapshot used for this score
    category_scores = models.JSONField(default=dict)  # {category: {score, weight, applicable, detail}}
    match_score = models.DecimalField(max_digits=5, decimal_places=2)
    matching_skills = models.JSONField(default=list)
    missing_required_skills = models.JSONField(default=list)
    relevant_projects = models.JSONField(default=list)
    experience_alignment = models.JSONField(default=dict)
    evidence = models.JSONField(default=list)  # [{claim, snippet, category}]
    limitations = models.JSONField(default=list)
    summary = models.TextField(blank=True)
    method = models.CharField(max_length=30, default="rule_based")  # rule_based | ai_assisted | mock
    provider = models.CharField(max_length=60, blank=True)
    is_mock = models.BooleanField(default=False)
    # Human oversight
    is_disputed = models.BooleanField(default=False)
    hr_review_note = models.TextField(blank=True)
    hr_adjusted_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["job", "is_current", "-match_score"])]
        constraints = [
            models.UniqueConstraint(fields=["resume"], condition=Q(is_current=True), name="one_current_analysis_per_resume"),
            models.CheckConstraint(condition=Q(match_score__gte=0) & Q(match_score__lte=100), name="analysis_score_0_100"),
        ]

    @property
    def effective_score(self):
        return self.hr_adjusted_score if self.hr_adjusted_score is not None else self.match_score


class Shortlist(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="shortlists")
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="shortlists")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    modified_by_hr = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["job"], condition=Q(status="proposed"), name="one_proposed_shortlist_per_job"),
        ]


class ShortlistEntry(models.Model):
    shortlist = models.ForeignKey(Shortlist, on_delete=models.CASCADE, related_name="entries")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="shortlist_entries")
    analysis = models.ForeignKey(ResumeAnalysis, on_delete=models.SET_NULL, null=True, related_name="+")
    rank = models.PositiveSmallIntegerField()
    added_manually = models.BooleanField(default=False)

    class Meta:
        ordering = ["rank"]
        constraints = [models.UniqueConstraint(fields=["shortlist", "candidate"], name="uniq_candidate_per_shortlist")]
