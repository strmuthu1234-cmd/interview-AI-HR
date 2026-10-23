from rest_framework import serializers

from .models import Candidate, JobPosting, Resume, ResumeAnalysis, ScreeningBatch, Shortlist, ShortlistEntry


def _skill_list(value, field):
    if not isinstance(value, list):
        raise serializers.ValidationError(f"{field} must be a list of strings.")
    cleaned = []
    for v in value:
        if not isinstance(v, str) or not v.strip() or len(v) > 100:
            raise serializers.ValidationError(f"{field} entries must be non-empty strings (max 100 characters).")
        if v.strip().lower() not in [c.lower() for c in cleaned]:
            cleaned.append(v.strip())
    return cleaned


class JobSerializer(serializers.ModelSerializer):
    candidate_count = serializers.SerializerMethodField()

    class Meta:
        model = JobPosting
        fields = ["id", "title", "department", "description", "required_skills", "preferred_skills", "min_experience_years",
                  "max_experience_years", "responsibilities", "mandatory_qualifications", "shortlist_size",
                  "interview_duration_minutes", "interview_language", "status", "created_at", "updated_at", "candidate_count"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "shortlist_size": {"min_value": 1, "max_value": 50},
            "min_experience_years": {"min_value": 0, "max_value": 50},
            "max_experience_years": {"min_value": 0, "max_value": 60},
            "interview_duration_minutes": {"min_value": 5, "max_value": 240},
        }

    def get_candidate_count(self, obj):
        return getattr(obj, "candidate_total", None) if hasattr(obj, "candidate_total") else obj.candidates.count()

    def validate_required_skills(self, value):
        value = _skill_list(value, "required_skills")
        if not value:
            raise serializers.ValidationError("At least one required skill is needed to screen resumes.")
        return value

    def validate_preferred_skills(self, value):
        return _skill_list(value, "preferred_skills")

    def validate_mandatory_qualifications(self, value):
        return _skill_list(value, "mandatory_qualifications")

    def validate_interview_language(self, value):
        if value not in ("en", "ta"):
            raise serializers.ValidationError("Supported interview languages: en, ta.")
        return value

    def validate(self, attrs):
        mn = attrs.get("min_experience_years", getattr(self.instance, "min_experience_years", 0))
        mx = attrs.get("max_experience_years", getattr(self.instance, "max_experience_years", None))
        if mx is not None and mn is not None and mx < mn:
            raise serializers.ValidationError("max_experience_years cannot be lower than min_experience_years.")
        return attrs


class AnalysisSerializer(serializers.ModelSerializer):
    effective_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = ResumeAnalysis
        fields = ["id", "match_score", "effective_score", "hr_adjusted_score", "rubric", "category_scores", "matching_skills",
                  "missing_required_skills", "relevant_projects", "experience_alignment", "evidence", "limitations", "summary",
                  "method", "provider", "is_mock", "is_disputed", "hr_review_note", "created_at"]


def current_analysis(candidate):
    """Current analysis, using the prefetched list when available."""
    cached = getattr(candidate, "_current_analyses", None)
    if cached is not None:
        return cached[0] if cached else None
    return candidate.analyses.filter(is_current=True).first()


class CandidateListSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(source="job.title", read_only=True)
    match_score = serializers.SerializerMethodField()
    missing_required_skills = serializers.SerializerMethodField()
    matching_skills = serializers.SerializerMethodField()
    parse_status = serializers.CharField(source="resume.parse_status", read_only=True)
    resume_filename = serializers.CharField(source="resume.original_filename", read_only=True)
    duplicate_of = serializers.SerializerMethodField()
    security_flag_count = serializers.SerializerMethodField()
    parse_error = serializers.CharField(source="resume.parse_error", read_only=True)

    class Meta:
        model = Candidate
        fields = ["id", "full_name", "email", "phone", "status", "job", "job_title", "match_score", "matching_skills",
                  "missing_required_skills", "parse_status", "parse_error", "resume_filename", "duplicate_of", "security_flag_count", "created_at"]

    def _a(self, obj):
        return current_analysis(obj)

    def get_match_score(self, obj):
        a = self._a(obj)
        return float(a.effective_score) if a else None

    def get_missing_required_skills(self, obj):
        a = self._a(obj)
        return a.missing_required_skills if a else []

    def get_matching_skills(self, obj):
        a = self._a(obj)
        return a.matching_skills if a else []

    def get_duplicate_of(self, obj):
        return obj.profile.get("duplicate_of")

    def get_security_flag_count(self, obj):
        return len(obj.resume.security_flags or [])


class ResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = ["id", "original_filename", "file_type", "file_size", "parse_status", "parse_error", "extraction_method",
                  "security_flags", "uploaded_at"]


class CandidateDetailSerializer(CandidateListSerializer):
    analysis = serializers.SerializerMethodField()
    resume = ResumeSerializer(read_only=True)
    resume_text = serializers.CharField(source="resume.extracted_text", read_only=True)
    original_profile = serializers.JSONField(source="resume.parsed_data", read_only=True)
    sessions = serializers.SerializerMethodField()

    class Meta(CandidateListSerializer.Meta):
        fields = CandidateListSerializer.Meta.fields + ["profile", "profile_corrected_at", "analysis", "resume", "resume_text", "original_profile", "sessions"]

    def get_analysis(self, obj):
        a = self._a(obj)
        return AnalysisSerializer(a).data if a else None

    def get_sessions(self, obj):
        return [{"id": str(s.id), "status": s.status, "current_index": s.current_index, "completed_at": s.completed_at,
                 "final_score": float(s.report.final_score) if hasattr(s, "report") and s.report.final_score is not None else None}
                for s in obj.sessions.all()]


class CandidateCorrectionSerializer(serializers.Serializer):
    """HR corrections of extracted information (original parser output is kept on the resume)."""

    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    profile = serializers.DictField(required=False)
    reanalyze = serializers.BooleanField(default=True)

    ALLOWED_PROFILE_KEYS = {"summary", "skills", "technologies", "experience", "total_experience_years", "education",
                            "certifications", "projects", "achievements"}

    def validate_profile(self, value):
        unknown = set(value) - self.ALLOWED_PROFILE_KEYS
        if unknown:
            raise serializers.ValidationError(f"Cannot edit: {', '.join(sorted(unknown))}")
        return value


class DisputeSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000)
    adjusted_score = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, allow_null=True)


class BatchSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(source="job.title", read_only=True)
    accepted_files = serializers.SerializerMethodField()
    resumes = serializers.SerializerMethodField()

    class Meta:
        model = ScreeningBatch
        fields = ["id", "job", "job_title", "status", "total_files", "accepted_files", "rejected_files", "processed_count",
                  "failed_count", "created_at", "completed_at", "resumes"]

    def get_accepted_files(self, obj):
        return obj.resumes.count()

    def get_resumes(self, obj):
        if not self.context.get("with_resumes"):
            return None
        return [{"id": str(r.id), "candidate": str(r.candidate_id), "filename": r.original_filename, "parse_status": r.parse_status,
                 "parse_error": r.parse_error} for r in obj.resumes.all()]


class ShortlistEntrySerializer(serializers.ModelSerializer):
    candidate_id = serializers.UUIDField(source="candidate.id")
    full_name = serializers.CharField(source="candidate.full_name")
    status = serializers.CharField(source="candidate.status")
    match_score = serializers.SerializerMethodField()
    matching_skills = serializers.JSONField(source="analysis.matching_skills", default=list)
    missing_required_skills = serializers.JSONField(source="analysis.missing_required_skills", default=list)
    summary = serializers.CharField(source="analysis.summary", default="")

    class Meta:
        model = ShortlistEntry
        fields = ["rank", "candidate_id", "full_name", "status", "match_score", "matching_skills", "missing_required_skills", "summary", "added_manually"]

    def get_match_score(self, obj):
        return float(obj.analysis.effective_score) if obj.analysis else None


class ShortlistSerializer(serializers.ModelSerializer):
    entries = ShortlistEntrySerializer(many=True, read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)

    class Meta:
        model = Shortlist
        fields = ["id", "job", "job_title", "status", "approved_at", "modified_by_hr", "created_at", "entries"]


class ShortlistApproveSerializer(serializers.Serializer):
    shortlist_id = serializers.UUIDField()
    candidate_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=50)
