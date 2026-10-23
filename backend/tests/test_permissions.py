"""Role-based access, tenant isolation, settings validation, scoring maths and API docs."""
import pytest

from apps.accounts.models import AuditLog, User
from apps.core.defaults import DEFAULT_ORG_SETTINGS, band_for, validate_org_settings
from apps.interviews.services.scoring import combine
from apps.recruitment.models import Candidate, JobPosting

HR_ENDPOINTS = ["/api/jobs/", "/api/candidates/", "/api/batches/", "/api/shortlists/", "/api/interviews/", "/api/dashboard/stats/",
                "/api/settings/", "/api/hr/decisions/", "/api/reports/export/", "/api/auth/me/"]
ADMIN_ONLY = ["/api/users/", "/api/audit-logs/"]


def test_anonymous_gets_401_everywhere(anon):
    for url in HR_ENDPOINTS + ADMIN_ONLY:
        assert anon.get(url).status_code == 401, url
    assert anon.post("/api/resumes/bulk-upload/", {}).status_code == 401
    assert anon.post("/api/shortlists/approve/", {}).status_code == 401


def test_hr_cannot_use_admin_endpoints(hr_client):
    for url in ADMIN_ONLY:
        assert hr_client.get(url).status_code == 403, url
    assert hr_client.patch("/api/settings/", {"settings": {"final_weights": {"resume": 50, "general": 25, "technical": 25}}}, format="json").status_code == 403
    for url in HR_ENDPOINTS:
        assert hr_client.get(url).status_code == 200, url


def test_admin_user_management(admin_client, org):
    r = admin_client.post("/api/users/", {"username": "newhr", "email": "n@example.com", "password": "Str0ng-Passw0rd!x", "role": "hr_manager"}, format="json")
    assert r.status_code == 201 and User.objects.get(username="newhr").organization == org
    assert admin_client.post("/api/users/", {"username": "weak", "email": "w@example.com", "password": "123", "role": "hr_manager"}, format="json").status_code == 400
    listing = admin_client.get("/api/users/").content.decode().lower()
    assert "pbkdf2" not in listing and "md5$" not in listing and '"password"' not in listing  # hashes never exposed
    me = User.objects.get(username="admin1")
    assert admin_client.patch(f"/api/users/{me.pk}/", {"is_active": False}, format="json").status_code == 400  # cannot lock self out
    assert AuditLog.objects.filter(action="user.create").exists()
    assert admin_client.get("/api/audit-logs/").status_code == 200


def test_tenant_isolation(hr_client, other_client, screened_job):
    cand = Candidate.objects.filter(job=screened_job).first()
    assert other_client.get(f"/api/candidates/{cand.pk}/").status_code == 404
    assert other_client.get(f"/api/jobs/{screened_job.pk}/").status_code == 404
    assert other_client.get("/api/candidates/").data["count"] == 0
    assert other_client.post("/api/resumes/bulk-upload/", {"job": str(screened_job.pk)}, format="multipart").status_code == 404
    assert other_client.post("/api/resumes/analyze/", {"job_id": str(screened_job.pk)}, format="json").status_code == 404
    assert other_client.get(f"/api/candidates/{cand.pk}/resume-url/").status_code == 404
    assert other_client.get("/api/dashboard/stats/").data["total_resumes"] == 0
    assert hr_client.get("/api/dashboard/stats/").data["total_resumes"] > 0


def test_login_and_refresh(anon, hr):
    r = anon.post("/api/auth/login/", {"username": "hr1", "password": "S3cure-Passw0rd!"}, format="json")
    assert r.status_code == 200 and {"access", "refresh", "user"} <= set(r.data) and r.data["user"]["role"] == "hr_manager"
    assert anon.post("/api/auth/login/", {"username": "hr1", "password": "wrong"}, format="json").status_code == 401
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert anon.get("/api/auth/me/").data["username"] == "hr1"
    assert AuditLog.objects.filter(action="auth.login_failed").exists()


def test_job_validation_and_crud(hr_client):
    base = {"title": "QA Engineer", "description": "Test things", "required_skills": ["Selenium"], "min_experience_years": 2}
    assert hr_client.post("/api/jobs/", {**base, "required_skills": []}, format="json").status_code == 400
    assert hr_client.post("/api/jobs/", {**base, "max_experience_years": 1}, format="json").status_code == 400
    assert hr_client.post("/api/jobs/", {**base, "shortlist_size": 0}, format="json").status_code == 400
    r = hr_client.post("/api/jobs/", base, format="json")
    assert r.status_code == 201 and r.data["shortlist_size"] == 10
    assert hr_client.patch(f"/api/jobs/{r.data['id']}/", {"preferred_skills": ["Cypress", "cypress"]}, format="json").data["preferred_skills"] == ["Cypress"]
    assert hr_client.delete(f"/api/jobs/{r.data['id']}/").status_code == 405


def test_settings_validation(admin_client):
    bad = {"final_weights": {"resume": 50, "general": 50, "technical": 50}}
    assert admin_client.patch("/api/settings/", {"settings": bad}, format="json").status_code == 400
    ok = {"final_weights": {"resume": 30, "general": 20, "technical": 50}, "retention": {"audio_days": 30}}
    r = admin_client.patch("/api/settings/", {"settings": ok}, format="json")
    assert r.status_code == 200 and r.data["settings"]["final_weights"]["resume"] == 30 and r.data["settings"]["retention"]["resume_days"] == 365
    assert admin_client.patch("/api/settings/", {"settings": {"ai": {"provider": "skynet"}}}, format="json").status_code == 400
    s = admin_client.get("/api/settings/").data
    assert "api_key" not in str(s).lower() and s["ai_status"]["keys_present"] == {"openai": False, "anthropic": False}


def test_final_score_formula_matches_spec():
    w = DEFAULT_ORG_SETTINGS["final_weights"]
    assert combine(88, 80, 85, w) == 84.85  # example from the product spec
    assert combine(None, 80, 80, w) == pytest.approx(80.0)  # renormalised over available components
    assert combine(None, None, None, w) is None
    s = DEFAULT_ORG_SETTINGS
    assert [band_for(x, s) for x in (100, 85, 84.99, 70, 69.9, 50, 49.9, 0)] == [
        "Strong match", "Strong match", "Good match", "Good match", "Needs further review", "Needs further review",
        "Significant gaps identified", "Significant gaps identified"]
    assert band_for(84.85, s) == "Good match"
    validate_org_settings({**s, "bands": s["bands"]})


def test_openapi_docs_available(anon):
    r = anon.get("/api/schema/")
    assert r.status_code == 200
    assert b"/api/interviews/{id}/answer/" in r.content and b"/api/resumes/bulk-upload/" in r.content


def test_retention_purge_removes_old_audio_and_resumes(screened_job, org):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.tasks import purge_expired_data
    from apps.recruitment.models import Resume

    Resume.objects.filter(job=screened_job).update(uploaded_at=timezone.now() - timedelta(days=400))
    stats = purge_expired_data()
    assert stats["resumes"] == Resume.objects.filter(job=screened_job).count()
    assert not Resume.objects.filter(job=screened_job).exclude(file="").exists()
