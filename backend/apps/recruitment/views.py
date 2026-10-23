import hashlib
import mimetypes
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_action
from apps.core.permissions import IsHR
from apps.core.signing import read_file_token, sign_file_token
from apps.core.throttles import UploadRateThrottle

from .models import Candidate, JobPosting, Resume, ResumeAnalysis, ScreeningBatch, Shortlist, ShortlistEntry
from .serializers import (
    BatchSerializer,
    CandidateCorrectionSerializer,
    CandidateDetailSerializer,
    CandidateListSerializer,
    DisputeSerializer,
    JobSerializer,
    ShortlistApproveSerializer,
    ShortlistSerializer,
)
from .services import pipeline
from .services.file_validation import FileRejected, validate_resume_file
from .tasks import process_resume_task, reanalyze_job_task


class OrgScopedMixin:
    permission_classes = [IsHR]

    @property
    def org(self):
        return self.request.user.organization


class JobViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = JobSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "department"]
    ordering_fields = ["created_at", "title"]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        return JobPosting.objects.filter(organization=self.org).annotate(candidate_total=Count("candidates"))

    def perform_create(self, serializer):
        job = serializer.save(organization=self.org, created_by=self.request.user)
        log_action(self.request, "job.create", job)

    def perform_update(self, serializer):
        job = serializer.save()
        log_action(self.request, "job.update", job, metadata={"fields": sorted(serializer.validated_data)})


def _candidates_qs(org):
    return (Candidate.objects.filter(organization=org).select_related("job", "resume")
            .prefetch_related(Prefetch("analyses", queryset=ResumeAnalysis.objects.filter(is_current=True), to_attr="_current_analyses")))


class CandidateViewSet(OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    filter_backends = [filters.SearchFilter]
    search_fields = ["full_name", "email"]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_serializer_class(self):
        return CandidateDetailSerializer if self.action in ("retrieve", "partial_update") else CandidateListSerializer

    def get_queryset(self):
        qs = _candidates_qs(self.org)
        p = self.request.query_params
        if p.get("job"):
            qs = qs.filter(job_id=p["job"])
        if p.get("batch"):
            qs = qs.filter(batch_id=p["batch"])
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("min_score"):
            qs = qs.filter(analyses__is_current=True, analyses__match_score__gte=p["min_score"])
        if p.get("skill"):
            qs = qs.filter(analyses__is_current=True, analyses__matching_skills__icontains=p["skill"])
        if p.get("ordering") == "score":
            qs = qs.filter(analyses__is_current=True).order_by("-analyses__match_score")
        return qs.distinct()

    def partial_update(self, request, *args, **kwargs):
        """HR correction of extracted information. Original parser output is preserved on the resume."""
        cand = self.get_object()
        ser = CandidateCorrectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        changed = []
        for f in ("full_name", "email", "phone"):
            if f in d:
                setattr(cand, f, d[f])
                changed.append(f)
        if "profile" in d:
            cand.profile = {**cand.profile, **d["profile"]}
            changed += [f"profile.{k}" for k in d["profile"]]
        cand.profile_corrected_by, cand.profile_corrected_at = request.user, timezone.now()
        cand.save()
        if d["reanalyze"] and cand.resume.parse_status == Resume.ParseStatus.PARSED:
            pipeline.analyze_resume(cand.resume)
            pipeline.propose_shortlist(cand.job)
        log_action(request, "candidate.correct_profile", cand, metadata={"fields": changed})
        cand = _candidates_qs(self.org).get(pk=cand.pk)
        return Response(CandidateDetailSerializer(cand, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        """Mark the assessment as disputed and optionally record an HR-adjusted score (with a mandatory reason)."""
        cand = self.get_object()
        ser = DisputeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        analysis = cand.analyses.filter(is_current=True).first()
        if not analysis:
            return Response({"detail": "This candidate has no analysis yet."}, status=400)
        analysis.is_disputed = True
        analysis.hr_review_note = ser.validated_data["note"]
        analysis.hr_adjusted_score = ser.validated_data.get("adjusted_score")
        analysis.reviewed_by = request.user
        analysis.save()
        pipeline.propose_shortlist(cand.job)
        log_action(request, "analysis.dispute", cand, metadata={"adjusted": str(analysis.hr_adjusted_score)})
        return Response(CandidateDetailSerializer(_candidates_qs(self.org).get(pk=cand.pk), context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"], url_path="resume-url")
    def resume_url(self, request, pk=None):
        cand = self.get_object()
        token = sign_file_token("resume", cand.resume.pk, request.user.pk)
        log_action(request, "resume.view", cand)
        return Response({"url": f"/api/files/resume/{token}/"})


class ResumeFileView(APIView):
    """Streams a resume for a short-lived signed token (usable in <iframe>/<a>)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    def get(self, request, token):
        data = read_file_token(token, "resume")
        if not data:
            raise Http404
        resume = get_object_or_404(Resume.objects.select_related("organization"), pk=data["pk"])
        from apps.accounts.models import User

        if not User.objects.filter(pk=data["u"], is_active=True, organization=resume.organization).exists() or not resume.file:
            raise Http404
        ctype = mimetypes.guess_type(f"x.{resume.file_type}")[0] or "application/octet-stream"
        resp = FileResponse(resume.file.open("rb"), content_type=ctype)
        resp["Content-Disposition"] = f'inline; filename="resume.{resume.file_type}"'
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp


class BulkUploadView(OrgScopedMixin, APIView):
    """POST /api/resumes/bulk-upload/  (multipart: job=<id>, files=<1..50 PDF/DOCX>)"""

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UploadRateThrottle]

    def post(self, request):
        job = get_object_or_404(JobPosting, pk=request.data.get("job"), organization=self.org) if request.data.get("job") else None
        if job is None:
            return Response({"detail": "job is required."}, status=400)
        files = request.FILES.getlist("files")
        from django.conf import settings

        if not 1 <= len(files) <= settings.MAX_RESUMES_PER_BATCH:
            return Response({"detail": f"Upload between 1 and {settings.MAX_RESUMES_PER_BATCH} resumes per batch."}, status=400)

        batch = ScreeningBatch.objects.create(organization=self.org, job=job, created_by=request.user, total_files=len(files))
        results, rejected, seen, accepted_ids = [], [], set(), []
        for f in files:
            name = (f.name or "resume")[:255]
            try:
                ftype, data = validate_resume_file(f)
                sha = hashlib.sha256(data).hexdigest()
                if sha in seen or Resume.objects.filter(job=job, sha256=sha).exists():
                    raise FileRejected("Duplicate: this exact resume was already uploaded for this job.")
                seen.add(sha)
            except FileRejected as exc:
                rejected.append({"filename": name, "reason": str(exc)})
                results.append({"filename": name, "status": "rejected", "reason": str(exc)})
                continue
            with transaction.atomic():
                cand = Candidate.objects.create(organization=self.org, job=job, batch=batch, full_name=name.rsplit(".", 1)[0][:200])
                resume = Resume(organization=self.org, job=job, batch=batch, candidate=cand, original_filename=name, file_type=ftype,
                                file_size=len(data), sha256=sha)
                resume.file.save(name, ContentFile(data), save=False)
                resume.save()
            accepted_ids.append(str(resume.pk))
            results.append({"filename": name, "status": "accepted", "candidate_id": str(cand.pk)})
        batch.rejected_files = rejected
        if not accepted_ids:
            batch.status, batch.completed_at = ScreeningBatch.Status.FAILED, timezone.now()
        batch.save()
        log_action(request, "resumes.bulk_upload", batch, metadata={"accepted": len(accepted_ids), "rejected": len(rejected), "job": str(job.pk)})
        for rid in accepted_ids:
            process_resume_task.delay(rid)
        batch.refresh_from_db()
        return Response({"batch_id": str(batch.pk), "accepted": len(accepted_ids), "rejected": len(rejected), "results": results,
                         "batch": BatchSerializer(batch).data}, status=status.HTTP_201_CREATED)


class AnalyzeView(OrgScopedMixin, APIView):
    """POST /api/resumes/analyze/ {job_id, batch_id?} – re-score parsed resumes with the current rubric/profiles."""

    def post(self, request):
        job = get_object_or_404(JobPosting, pk=request.data.get("job_id"), organization=self.org)
        batch_id = request.data.get("batch_id")
        if batch_id:
            get_object_or_404(ScreeningBatch, pk=batch_id, organization=self.org, job=job)
        reanalyze_job_task.delay(str(job.pk), batch_id)
        log_action(request, "resumes.analyze", job, metadata={"batch": batch_id})
        return Response({"detail": "Analysis started.", "job_id": str(job.pk)}, status=status.HTTP_202_ACCEPTED)


class BatchViewSet(OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BatchSerializer

    def get_queryset(self):
        qs = ScreeningBatch.objects.filter(organization=self.org).select_related("job")
        if self.request.query_params.get("job"):
            qs = qs.filter(job_id=self.request.query_params["job"])
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["with_resumes"] = self.action == "retrieve"
        return ctx


class ShortlistViewSet(OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ShortlistSerializer

    def get_queryset(self):
        qs = (Shortlist.objects.filter(organization=self.org).select_related("job")
              .prefetch_related("entries__candidate", "entries__analysis"))
        if self.request.query_params.get("job"):
            qs = qs.filter(job_id=self.request.query_params["job"])
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs


class ShortlistApproveView(OrgScopedMixin, APIView):
    """POST /api/shortlists/approve/ {shortlist_id, candidate_ids} – HR approves or modifies the shortlist.

    Approval starts generation of the 20 questions for each shortlisted candidate.
    """

    @transaction.atomic
    def post(self, request):
        from apps.interviews.models import InterviewSession
        from apps.interviews.tasks import generate_questions_task

        ser = ShortlistApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        sl = get_object_or_404(Shortlist.objects.select_for_update(), pk=ser.validated_data["shortlist_id"], organization=self.org)
        if sl.status != Shortlist.Status.PROPOSED:
            return Response({"detail": "This shortlist was already approved."}, status=409)
        ids = list(dict.fromkeys(ser.validated_data["candidate_ids"]))
        if len(ids) > sl.job.shortlist_size:
            return Response({"detail": f"This job has {sl.job.shortlist_size} shortlist slots; increase the slots on the job to approve more."}, status=400)
        cands = {c.pk: c for c in Candidate.objects.filter(pk__in=ids, job=sl.job, organization=self.org, status=Candidate.Status.SCREENED)}
        if len(cands) != len(ids):
            return Response({"detail": "Some candidates are not eligible (wrong job, not screened yet, or already shortlisted)."}, status=400)
        analyses = {a.candidate_id: a for a in ResumeAnalysis.objects.filter(candidate_id__in=ids, is_current=True)}
        if len(analyses) != len(ids):
            return Response({"detail": "Every shortlisted candidate needs a completed resume analysis."}, status=400)
        proposed = set(sl.entries.values_list("candidate_id", flat=True))
        sl.entries.all().delete()
        order = sorted(ids, key=lambda i: -float(analyses[i].effective_score))
        for rank, cid in enumerate(order, start=1):
            ShortlistEntry.objects.create(shortlist=sl, candidate=cands[cid], analysis=analyses[cid], rank=rank, added_manually=cid not in proposed)
        sl.status, sl.approved_by, sl.approved_at = Shortlist.Status.APPROVED, request.user, timezone.now()
        sl.modified_by_hr = proposed != set(ids)
        sl.save()
        sessions = []
        for cid in order:
            c = cands[cid]
            c.status = Candidate.Status.SHORTLISTED
            c.save(update_fields=["status"])
            sessions.append(InterviewSession.objects.create(organization=self.org, candidate=c, job=sl.job, analysis=analyses[cid],
                                                            language=sl.job.interview_language))
        log_action(request, "shortlist.approve", sl, metadata={"candidates": [str(i) for i in order], "modified": sl.modified_by_hr})
        session_ids = [str(s.pk) for s in sessions]
        transaction.on_commit(lambda: [generate_questions_task.delay(sid) for sid in session_ids])
        # Make sure a fresh proposal exists for remaining candidates.
        transaction.on_commit(lambda: pipeline.propose_shortlist(sl.job))
        return Response({"shortlist": ShortlistSerializer(sl).data, "interview_sessions": session_ids}, status=200)


class DashboardView(OrgScopedMixin, APIView):
    def get(self, request):
        from apps.interviews.models import HRDecision, InterviewSession

        org = self.org
        sessions = InterviewSession.objects.filter(organization=org)
        decided = HRDecision.objects.filter(session__organization=org).values("session_id").distinct()
        completed = sessions.filter(status="completed")
        by_status = dict(Candidate.objects.filter(organization=org).values_list("status").annotate(n=Count("id")))
        return Response({
            "total_jobs": JobPosting.objects.filter(organization=org).count(),
            "total_resumes": Resume.objects.filter(organization=org).count(),
            "screened_candidates": ResumeAnalysis.objects.filter(organization=org, is_current=True).count(),
            "proposed_shortlist": Shortlist.objects.filter(organization=org, status="proposed").aggregate(n=Count("entries"))["n"],
            "interviews_scheduled": sessions.filter(status__in=["ready", "in_progress"], invitation__isnull=False).count(),
            "interviews_completed": completed.count(),
            "pending_hr_reviews": completed.exclude(pk__in=decided).count(),
            "candidates_by_status": by_status,
            "score_distribution": _score_buckets(org),
        })


def _score_buckets(org):
    buckets = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
    for s in ResumeAnalysis.objects.filter(organization=org, is_current=True).values_list("match_score", "hr_adjusted_score"):
        v = float(s[1] if s[1] is not None else s[0])
        buckets["85-100" if v >= 85 else "70-84" if v >= 70 else "50-69" if v >= 50 else "0-49"] += 1
    return [{"range": k, "count": v} for k, v in buckets.items()]
