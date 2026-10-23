import mimetypes
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai import speech
from apps.ai.errors import AIConfigurationError, AIProviderError
from apps.core.audit import log_action
from apps.core.authentication import hash_token
from apps.core.defaults import get_org_settings
from apps.core.permissions import IsCandidate, IsHR
from apps.core.signing import read_file_token, sign_file_token
from apps.core.throttles import CandidateRateThrottle
from apps.recruitment.models import Candidate
from apps.recruitment.services import skills as sk

from .models import (TOTAL_QUESTIONS, AnswerEvaluation, CandidateAnswer, HRDecision, InterviewInvitation, InterviewQuestion,
                     InterviewReport, InterviewSession, PendingAudio)
from .services import flow, scoring
from .services.flow import FlowError
from .services.pdf_report import build_pdf
from .services.questions import allowed_technologies, unsupported_technologies
from .services.report_payload import report_payload, sessions_csv
from .tasks import generate_questions_task, generate_report_task

INSTRUCTIONS = [
    "This is a structured interview with 20 questions. You will see ONE question at a time.",
    "You can answer by voice (recommended) or by typing. You can record, pause, replay and re-record before you submit.",
    "Nothing moves forward automatically: the next question appears only after you press Submit.",
    "If your connection drops or you close the page, reopen your link to continue where you stopped.",
    "Your answers are evaluated for job-relevant content only. Accent, voice, background noise and grammar are not scored.",
    "AI assists the hiring team, but every hiring decision is made by a human.",
    "Audio is recorded only if you give consent below. You may decline and answer by typing or by browser speech-to-text.",
]
AUDIO_MAGIC = [(b"\x1aE\xdf\xa3", 0), (b"OggS", 0), (b"RIFF", 0), (b"ID3", 0), (b"\xff\xfb", 0), (b"\xff\xf3", 0), (b"ftyp", 4)]


def flow_error_response(exc: FlowError):
    return Response({"detail": exc.message, "code": exc.code}, status=exc.status)


# ============================================================ candidate side
class CandidateSessionMixin:
    permission_classes = [IsCandidate]
    throttle_classes = [CandidateRateThrottle]

    def get_session(self, pk):
        inv = self.request.auth
        if not isinstance(inv, InterviewInvitation) or str(inv.session_id) != str(pk):
            raise PermissionDenied("This link does not give access to that interview.")
        return InterviewSession.objects.select_related("organization", "job", "candidate").get(pk=pk)


def question_payload(session, q):
    pending = PendingAudio.objects.filter(question=q).first()
    return {
        "id": str(q.id), "number": q.index + 1, "total": TOTAL_QUESTIONS, "text": q.text, "is_self_introduction": q.is_self_introduction,
        "section": q.section,  # only the label; expected points are never sent to candidates
        "pending_audio": None if not pending else {"duration_seconds": pending.duration_seconds, "transcript": pending.transcript,
                                                    "transcript_source": pending.transcript_source},
        "settings": flow.candidate_settings(session),
    }


class AccessView(APIView):
    """POST /api/interviews/access/  (Authorization: Invitation <token>) -> what the candidate may see."""

    permission_classes = [IsCandidate]
    throttle_classes = [CandidateRateThrottle]

    def post(self, request):
        inv = request.auth
        s = InterviewSession.objects.select_related("organization", "job", "candidate").get(pk=inv.session_id)
        if inv.opened_at is None and inv.status in ("pending", "sent"):
            inv.status, inv.opened_at = "opened", timezone.now()
            inv.save(update_fields=["status", "opened_at"])
            log_action(request, "interview.link_opened", s, org=s.organization)
        first = (s.candidate.full_name or "").split(" ")[0]
        return Response({
            "session_id": str(s.id), "status": s.status, "available": s.status in ("ready", "in_progress", "completed"),
            "company": s.organization.name, "job_title": s.job.title, "candidate_first_name": first,
            "duration_minutes": s.job.interview_duration_minutes, "language": s.language, "instructions": INSTRUCTIONS,
            "progress": flow.progress(s), "settings": flow.candidate_settings(s),
        })


class AcceptInstructionsView(CandidateSessionMixin, APIView):
    def post(self, request, pk):
        s = self.get_session(pk)
        if request.data.get("accept") is not True:
            return Response({"detail": "You must accept the interview instructions to continue.", "code": "not_accepted"}, status=400)
        consent = request.data.get("recording_consent")
        if not isinstance(consent, bool):
            return Response({"detail": "recording_consent must be true or false.", "code": "consent_required"}, status=400)
        try:
            s = flow.accept_instructions(s, consent)
        except FlowError as exc:
            return flow_error_response(exc)
        log_action(request, "interview.start", s, org=s.organization, metadata={"recording_consent": s.recording_consent})
        return Response({"progress": flow.progress(s)})


class QuestionView(CandidateSessionMixin, APIView):
    """GET /api/interviews/{id}/question/ -> ONLY the current question."""

    def get(self, request, pk):
        s = self.get_session(pk)
        try:
            q = flow.active_question(s)
        except FlowError as exc:
            return flow_error_response(exc)
        s.refresh_from_db()
        if q is None:
            return Response({"done": True, "progress": flow.progress(s)})
        return Response({"done": False, "question": question_payload(s, q), "progress": flow.progress(s)})


class ProgressView(CandidateSessionMixin, APIView):
    def get(self, request, pk):
        return Response(flow.progress(self.get_session(pk)))


def _looks_like_audio(head: bytes) -> bool:
    return any(head[off: off + len(m)] == m for m, off in AUDIO_MAGIC)


class VoiceUploadView(CandidateSessionMixin, APIView):
    """POST /api/interviews/{id}/voice-upload/ – store a recording for the ACTIVE question (not yet submitted)."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        s = self.get_session(pk)
        if not s.recording_consent:
            return Response({"detail": "Audio recording requires your consent. Answer by typing or browser speech-to-text instead.", "code": "no_consent"}, status=403)
        try:
            q = flow.active_question(s)
        except FlowError as exc:
            return flow_error_response(exc)
        if q is None:
            return Response({"detail": "All questions have been answered.", "code": "all_answered"}, status=409)
        audio = request.FILES.get("audio")
        if audio is None:
            return Response({"detail": "audio file is required."}, status=400)
        if audio.size == 0 or audio.size > settings.MAX_AUDIO_FILE_MB * 1024 * 1024:
            return Response({"detail": f"Recording must be between 1 byte and {settings.MAX_AUDIO_FILE_MB} MB."}, status=400)
        head = audio.read(16)
        audio.seek(0)
        if not _looks_like_audio(head):
            return Response({"detail": "File is not a recognised audio recording."}, status=400)
        try:
            duration = max(0, min(int(float(request.data.get("duration", 0))), 3600))
        except (TypeError, ValueError):
            duration = 0
        transcript = (request.data.get("transcript") or "")[:settings.MAX_ANSWER_CHARS].strip()
        t_source = "browser" if transcript else ""
        voice_cfg = get_org_settings(s.organization)["voice"]
        transcription = "browser" if transcript else "unavailable"
        if voice_cfg["stt_provider"] == "server":
            try:
                text = speech.transcribe(audio.read(), audio.name or "answer.webm", audio.content_type, s.language)
                audio.seek(0)
                if text:
                    transcript, t_source, transcription = text, "server_stt", "server"
            except (AIConfigurationError, AIProviderError) as exc:
                transcription = "failed"
                request.transcription_error = str(exc)
        old = PendingAudio.objects.filter(question=q).first()
        if old:
            old.audio_file.delete(save=False)
            old.delete()
        pending = PendingAudio(session=s, question=q, duration_seconds=duration, transcript=transcript, transcript_source=t_source)
        pending.audio_file.save(audio.name or "answer.webm", audio, save=False)
        pending.save()
        return Response({"transcript": transcript, "transcript_source": t_source, "transcription": transcription,
                         "server_stt_available": speech.server_stt_available() and voice_cfg["stt_provider"] == "server"}, status=201)


class AnswerView(CandidateSessionMixin, APIView):
    """POST /api/interviews/{id}/answer/ – validated entirely on the backend."""

    def post(self, request, pk):
        s = self.get_session(pk)
        d = request.data
        try:
            answer, duplicate = flow.submit_answer(
                s, question_id=d.get("question_id"), text=d.get("text", ""), input_mode=d.get("input_mode", "text"),
                client_submission_id=str(d.get("client_submission_id", ""))[:64], skip=bool(d.get("skip", False)),
                transcript_source=str(d.get("transcript_source", ""))[:20])
        except FlowError as exc:
            return flow_error_response(exc)
        if not duplicate:
            log_action(request, "interview.answer", answer, org=s.organization, metadata={"question": answer.question.index + 1})
        s.refresh_from_db()
        body = {"saved": True, "duplicate": duplicate, "progress": flow.progress(s)}
        if get_org_settings(s.organization)["interview"]["reveal_results_to_candidate"] or s.reveal_results:
            ev = AnswerEvaluation.objects.filter(answer=answer).first()
            if ev and ev.status == "completed":
                body["feedback"] = {"score": float(ev.effective_score), "feedback": ev.feedback, "suggestions": ev.suggestions}
        return Response(body, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)


class CompleteView(CandidateSessionMixin, APIView):
    def post(self, request, pk):
        s = self.get_session(pk)
        try:
            s, first_time = flow.complete(s)
        except FlowError as exc:
            return flow_error_response(exc)
        if first_time:
            log_action(request, "interview.complete", s, org=s.organization)
            generate_report_task.delay(str(s.pk))
        return Response({"completed": True, "message": "Thank you! Your interview has been submitted. The hiring team will be in touch."})


# =================================================================== HR side
def session_row(s):
    rep = getattr(s, "report", None)
    latest = s.decisions.first() if hasattr(s, "decisions") else None
    return {
        "id": str(s.id), "candidate_id": str(s.candidate_id), "candidate_name": s.candidate.full_name, "job_id": str(s.job_id), "job_title": s.job.title,
        "status": s.status, "current_index": s.current_index, "answered": s.answers.count(), "total": TOTAL_QUESTIONS, "is_mock": s.is_mock,
        "generation_error": s.generation_error, "has_invitation": hasattr(s, "invitation"), "invitation_status": s.invitation.status if hasattr(s, "invitation") else None,
        "invitation_expires_at": s.invitation.expires_at if hasattr(s, "invitation") else None,
        "final_score": float(rep.final_score) if rep and rep.final_score is not None else None, "band": rep.band if rep else None,
        "decision": latest.decision if latest else None, "reveal_results": s.reveal_results, "created_at": s.created_at,
        "completed_at": s.completed_at, "recording_consent": s.recording_consent,
    }


class InterviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsHR]

    def get_queryset(self):
        qs = (InterviewSession.objects.filter(organization=self.request.user.organization)
              .select_related("candidate", "job", "invitation", "report").prefetch_related("decisions", "answers"))
        p = self.request.query_params
        if p.get("job"):
            qs = qs.filter(job_id=p["job"])
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("candidate"):
            qs = qs.filter(candidate_id=p["candidate"])
        return qs

    def list(self, request, *a, **kw):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([session_row(s) for s in page])

    def retrieve(self, request, *a, **kw):
        s = self.get_object()
        data = session_row(s)
        p = report_payload(s)
        data["questions"] = [{**q, "id": str(qq.id), "number": q["number"], "edited": qq.edited_by_id is not None, "original_text": qq.original_text,
                              "grounding": qq.grounding, "is_self_introduction": qq.is_self_introduction}
                             for q, qq in zip(p["questions"], s.questions.order_by("index"))]
        data["report"] = p["report"]
        data["decisions"] = p["decisions"]
        data["ai_provider"] = s.ai_provider
        data["questions_approved_at"] = s.questions_approved_at
        data["duration_seconds"] = s.duration_seconds
        return Response(data)

    def partial_update(self, request, pk=None):
        """HR explicitly enables/disables showing per-answer feedback to the candidate."""
        s = self.get_object()
        if "reveal_results" in request.data:
            s.reveal_results = bool(request.data["reveal_results"])
            s.save(update_fields=["reveal_results"])
            log_action(request, "interview.reveal_results", s, metadata={"value": s.reveal_results})
        return Response(session_row(s))


class HRSessionMixin:
    permission_classes = [IsHR]

    def get_session(self, pk):
        return get_object_or_404(InterviewSession.objects.select_related("candidate", "job", "organization"), pk=pk,
                                 organization=self.request.user.organization)


class GenerateQuestionsView(HRSessionMixin, APIView):
    """(Re)generate the 20 questions – e.g. after fixing the AI configuration or the candidate profile."""

    def post(self, request, pk):
        s = self.get_session(pk)
        if s.status not in (s.Status.GENERATION_FAILED, s.Status.DRAFT, s.Status.GENERATING):
            return Response({"detail": "Questions can no longer be regenerated for this interview."}, status=409)
        s.status = s.Status.GENERATING
        s.save(update_fields=["status"])
        log_action(request, "questions.generate", s)
        generate_questions_task.delay(str(s.pk))
        s.refresh_from_db()
        return Response(session_row(s), status=202)


class EditQuestionView(HRSessionMixin, APIView):
    def patch(self, request, pk, qid):
        s = self.get_session(pk)
        if s.status not in (s.Status.DRAFT, s.Status.READY) or s.answers.exists():
            return Response({"detail": "Questions can only be edited before the interview starts."}, status=409)
        q = get_object_or_404(InterviewQuestion, pk=qid, session=s)
        text = " ".join(str(request.data.get("text", q.text)).split())
        if not 10 <= len(text) <= 700:
            return Response({"detail": "Question must be 10-700 characters."}, status=400)
        points = request.data.get("expected_points")
        if points is not None:
            if not isinstance(points, list) or not all(isinstance(x, str) for x in points):
                return Response({"detail": "expected_points must be a list of strings."}, status=400)
            q.expected_points = [x.strip()[:200] for x in points if x.strip()][:8]
        warnings = []
        bad = unsupported_technologies(text, allowed_technologies(s.job, s.candidate.profile or {}))
        if bad:
            warnings.append(f"Mentions technologies not found in the resume or job requirements: {', '.join(bad)}.")
        q.text, q.edited_by = text, request.user
        q.save()
        if s.status == s.Status.READY:  # edits require re-approval
            s.status, s.questions_approved_at, s.questions_approved_by = s.Status.DRAFT, None, None
            s.save(update_fields=["status", "questions_approved_at", "questions_approved_by"])
        log_action(request, "question.edit", q, metadata={"index": q.index + 1})
        return Response({"id": str(q.id), "number": q.index + 1, "text": q.text, "expected_points": q.expected_points, "warnings": warnings})


class ApproveQuestionsView(HRSessionMixin, APIView):
    def post(self, request, pk):
        s = self.get_session(pk)
        if s.status == s.Status.READY:
            return Response(session_row(s))
        if s.status != s.Status.DRAFT or s.questions.count() != TOTAL_QUESTIONS:
            return Response({"detail": "Exactly 20 generated questions are required before approval."}, status=409)
        s.status, s.questions_approved_by, s.questions_approved_at = s.Status.READY, request.user, timezone.now()
        s.save(update_fields=["status", "questions_approved_by", "questions_approved_at"])
        log_action(request, "questions.approve", s)
        return Response(session_row(s))


def _new_link(session, token, request_user=None):
    return f"{settings.FRONTEND_URL}/interview/{token}"


class CreateInvitationView(HRSessionMixin, APIView):
    """POST /api/interviews/create/ {session_id, expires_in_days?, send_email?} – HR approves the invitation."""

    def post(self, request):
        s = self.get_session(request.data.get("session_id"))
        if s.status != s.Status.READY:
            return Response({"detail": "Approve the 20 interview questions before inviting the candidate."}, status=409)
        if hasattr(s, "invitation"):
            return Response({"detail": "An invitation already exists. Use regenerate-link to issue a new link.", "code": "exists"}, status=409)
        days = int(request.data.get("expires_in_days") or get_org_settings(s.organization)["interview"]["invite_expiry_days"])
        if not 1 <= days <= 60:
            return Response({"detail": "expires_in_days must be between 1 and 60."}, status=400)
        token = secrets.token_urlsafe(32)
        inv = InterviewInvitation.objects.create(organization=s.organization, candidate=s.candidate, job=s.job, session=s,
                                                 token_hash=hash_token(token), expires_at=timezone.now() + timedelta(days=days), created_by=request.user)
        Candidate.objects.filter(pk=s.candidate_id, status__in=["shortlisted", "screened"]).update(status=Candidate.Status.INTERVIEW_INVITED)
        log_action(request, "invitation.create", inv, metadata={"expires_in_days": days})
        email_sent = _maybe_email(request, s, inv, token)
        return Response({"invitation_id": str(inv.id), "link": _new_link(s, token), "expires_at": inv.expires_at, "email_sent": email_sent}, status=201)


def _maybe_email(request, session, inv, token):
    if not request.data.get("send_email") or not session.candidate.email:
        return False
    try:
        send_mail(
            subject=f"Your interview for {session.job.title} at {session.organization.name}",
            message=(f"Hello,\n\nYou have been invited to complete an online interview for the {session.job.title} position.\n"
                     f"Open your personal link: {_new_link(session, token)}\nThe link expires on {inv.expires_at:%d %b %Y}.\n\n"
                     "You will need a quiet place and a microphone (or you can type your answers)."),
            from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[session.candidate.email])
        inv.status, inv.sent_at = "sent", timezone.now()
        inv.save(update_fields=["status", "sent_at"])
        return True
    except Exception:  # SMTP problems must not break invitation creation
        return False


class RegenerateLinkView(HRSessionMixin, APIView):
    def post(self, request, pk):
        s = self.get_session(pk)
        inv = getattr(s, "invitation", None)
        if inv is None or s.status in (s.Status.COMPLETED,):
            return Response({"detail": "No active invitation to regenerate."}, status=409)
        token = secrets.token_urlsafe(32)
        inv.token_hash, inv.status = hash_token(token), "pending"
        inv.expires_at = timezone.now() + timedelta(days=get_org_settings(s.organization)["interview"]["invite_expiry_days"])
        inv.save()
        log_action(request, "invitation.regenerate", inv)
        return Response({"link": _new_link(s, token), "expires_at": inv.expires_at, "email_sent": _maybe_email(request, s, inv, token)})


class RevokeInvitationView(HRSessionMixin, APIView):
    def post(self, request, pk):
        s = self.get_session(pk)
        inv = getattr(s, "invitation", None)
        if inv is None:
            return Response({"detail": "No invitation exists."}, status=404)
        inv.status = "revoked"
        inv.save(update_fields=["status"])
        log_action(request, "invitation.revoke", inv)
        return Response({"revoked": True})


class OverrideView(HRSessionMixin, APIView):
    """HR reviews a disputed evaluation: adjust an answer's score with a mandatory reason; report is recalculated."""

    def post(self, request, pk):
        s = self.get_session(pk)
        ans = get_object_or_404(CandidateAnswer, pk=request.data.get("answer_id"), session=s)
        ev = get_object_or_404(AnswerEvaluation, answer=ans)
        reason = str(request.data.get("reason", "")).strip()
        try:
            score = float(request.data.get("score"))
        except (TypeError, ValueError):
            return Response({"detail": "score must be a number between 0 and 10."}, status=400)
        if not 0 <= score <= 10 or len(reason) < 5:
            return Response({"detail": "Provide a score between 0 and 10 and a reason (min 5 characters)."}, status=400)
        ev.hr_override_score, ev.hr_override_reason, ev.overridden_by = score, reason[:1000], request.user
        ev.save()
        log_action(request, "evaluation.override", ev, metadata={"question": ans.question.index + 1, "score": score})
        if hasattr(s, "report"):
            scoring.build_report(s)
        return Response({"ok": True})


class ReportView(HRSessionMixin, APIView):
    def get(self, request, pk):
        s = self.get_session(pk)
        if s.status == s.Status.COMPLETED and not hasattr(s, "report"):
            scoring.build_report(s)
            s.refresh_from_db()
        log_action(request, "report.view", s)
        return Response(report_payload(s))


class ReportRegenerateView(HRSessionMixin, APIView):
    def post(self, request, pk):
        s = self.get_session(pk)
        if s.status != s.Status.COMPLETED:
            return Response({"detail": "The interview is not completed yet."}, status=409)
        from .tasks import retry_failed_evaluations

        retry_failed_evaluations(str(s.pk))
        scoring.build_report(s)
        s.refresh_from_db()
        log_action(request, "report.regenerate", s)
        return Response(report_payload(s))


class ReportPdfView(HRSessionMixin, APIView):
    def get(self, request, pk):
        s = self.get_session(pk)
        if s.status != s.Status.COMPLETED:
            return Response({"detail": "The interview is not completed yet."}, status=409)
        if not hasattr(s, "report"):
            scoring.build_report(s)
            s.refresh_from_db()
        pdf = build_pdf(report_payload(s))
        log_action(request, "report.pdf_download", s)
        name = "".join(c if c.isalnum() else "_" for c in s.candidate.full_name)[:40] or "candidate"
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="interview_report_{name}.pdf"'
        return resp


class AudioUrlView(HRSessionMixin, APIView):
    def get(self, request, pk, aid):
        s = self.get_session(pk)
        ans = get_object_or_404(CandidateAnswer, pk=aid, session=s)
        if not ans.audio_file:
            return Response({"detail": "No recording exists for this answer."}, status=404)
        log_action(request, "audio.access", ans)
        return Response({"url": f"/api/files/audio/{sign_file_token('audio', ans.pk, request.user.pk)}/"})


class AudioFileView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    def get(self, request, token):
        data = read_file_token(token, "audio")
        if not data:
            raise Http404
        ans = get_object_or_404(CandidateAnswer.objects.select_related("session"), pk=data["pk"])
        from apps.accounts.models import User

        if not ans.audio_file or not User.objects.filter(pk=data["u"], is_active=True, organization=ans.session.organization).exists():
            raise Http404
        ctype = mimetypes.guess_type(ans.audio_file.name)[0] or "audio/webm"
        resp = FileResponse(ans.audio_file.open("rb"), content_type=ctype)
        resp["Cache-Control"] = "private, no-store"
        resp["X-Content-Type-Options"] = "nosniff"
        return resp


class DecisionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    decision = serializers.ChoiceField(choices=HRDecision.Decision.choices)
    comments = serializers.CharField(allow_blank=True, max_length=4000, required=False, default="")


class DecisionView(APIView):
    """POST /api/hr/decisions/ – the ONLY way a candidate becomes Selected / Rejected / On Hold."""

    permission_classes = [IsHR]

    def get(self, request):
        qs = HRDecision.objects.filter(session__organization=request.user.organization).select_related("decided_by", "candidate")
        if request.query_params.get("session"):
            qs = qs.filter(session_id=request.query_params["session"])
        from .services.report_payload import decision_dict

        return Response([{**decision_dict(d), "candidate": d.candidate.full_name, "session_id": str(d.session_id)} for d in qs[:200]])

    @transaction.atomic
    def post(self, request):
        ser = DecisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        s = get_object_or_404(InterviewSession.objects.select_related("candidate"), pk=ser.validated_data["session_id"],
                              organization=request.user.organization)
        if s.status != s.Status.COMPLETED:
            return Response({"detail": "A decision can only be recorded after the interview is completed."}, status=409)
        if not hasattr(s, "report"):
            scoring.build_report(s)
            s.refresh_from_db()
        d = HRDecision.objects.create(session=s, candidate=s.candidate, decision=ser.validated_data["decision"], comments=ser.validated_data["comments"],
                                      decided_by=request.user, ai_score_at_decision=s.report.final_score)
        s.candidate.status = d.decision
        s.candidate.save(update_fields=["status"])
        log_action(request, "hr.decision", d, metadata={"decision": d.decision, "session": str(s.pk)})
        from .services.report_payload import decision_dict

        return Response(decision_dict(d), status=201)


class CompareView(APIView):
    """GET /api/reports/compare/?sessions=id1,id2,...  (2-6 sessions)"""

    permission_classes = [IsHR]

    def get(self, request):
        ids = [i for i in request.query_params.get("sessions", "").split(",") if i][:6]
        sessions = InterviewSession.objects.filter(pk__in=ids, organization=request.user.organization, status="completed").select_related("candidate", "job", "report")
        rows, skills = [], {}
        for s in sessions:
            p = report_payload(s, with_questions=False)
            r = p["report"] or {}
            rows.append({"session_id": p["session_id"], "candidate": p["candidate"]["name"], "job": p["job"]["title"], "resume_score": r.get("resume_score"),
                         "general_score": r.get("general_score"), "technical_score": r.get("technical_score"), "final_score": r.get("final_score"),
                         "band": r.get("band"), "decision": (p["latest_decision"] or {}).get("decision"), "is_mock": p["is_mock"]})
            for st in (r.get("strengths", []) + r.get("knowledge_gaps", [])):
                skills.setdefault(st["skill"], {})[p["candidate"]["name"]] = st["avg_score"]
        rows.sort(key=lambda r: -(r["final_score"] or 0))
        return Response({"candidates": rows, "skills": skills, "notice": "Scores are advisory; compare evidence in each full report."})


class ExportCsvView(APIView):
    permission_classes = [IsHR]

    def get(self, request):
        qs = InterviewSession.objects.filter(organization=request.user.organization, status="completed").select_related("candidate", "job", "report")
        if request.query_params.get("job"):
            qs = qs.filter(job_id=request.query_params["job"])
        log_action(request, "report.csv_export", None, org=request.user.organization)
        resp = HttpResponse(sessions_csv(qs), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="interview_results.csv"'
        return resp


class ResultsView(CandidateSessionMixin, APIView):
    """Candidate-visible feedback – only when HR explicitly enabled it for this interview."""

    def get(self, request, pk):
        s = self.get_session(pk)
        if not (s.reveal_results or get_org_settings(s.organization)["interview"]["reveal_results_to_candidate"]) or s.status != s.Status.COMPLETED:
            return Response({"detail": "Results are not shared for this interview.", "code": "not_shared"}, status=403)
        out = []
        for a in s.answers.select_related("question", "evaluation").order_by("question__index"):
            ev = getattr(a, "evaluation", None)
            if ev and ev.status == "completed":
                out.append({"number": a.question.index + 1, "question": a.question.text, "score": float(ev.effective_score),
                            "feedback": ev.feedback, "suggestions": ev.suggestions})
        return Response({"answers": out})
