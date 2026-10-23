import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Organization, User
from apps.recruitment.models import JobPosting
from apps.recruitment.sample_data import SAMPLE_JOB, SAMPLE_RESUMES, build_file


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme HR", slug="acme", settings={"ai": {"provider": "mock"}})


@pytest.fixture
def other_org(db):
    return Organization.objects.create(name="Other Co", slug="other", settings={"ai": {"provider": "mock"}})


def _mk_user(org, username, role):
    return User.objects.create_user(username=username, email=f"{username}@example.com", password="S3cure-Passw0rd!", role=role, organization=org)


@pytest.fixture
def admin(org):
    return _mk_user(org, "admin1", User.Role.ADMIN)


@pytest.fixture
def hr(org):
    return _mk_user(org, "hr1", User.Role.HR_MANAGER)


@pytest.fixture
def other_hr(other_org):
    return _mk_user(other_org, "hr_other", User.Role.HR_MANAGER)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def hr_client(hr):
    return client_for(hr)


@pytest.fixture
def admin_client(admin):
    return client_for(admin)


@pytest.fixture
def other_client(other_hr):
    return client_for(other_hr)


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def job(org, hr):
    data = {k: v for k, v in SAMPLE_JOB.items()}
    return JobPosting.objects.create(organization=org, created_by=hr, **data)


def upload_file(spec):
    data = build_file(spec)
    ctype = "application/pdf" if spec["format"] == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return SimpleUploadedFile(spec["filename"], data, content_type=ctype)


@pytest.fixture
def sample_files():
    return [upload_file(s) for s in SAMPLE_RESUMES]


@pytest.fixture
def screened_job(hr_client, job, sample_files):
    """Job with all sample resumes uploaded, parsed (eager Celery) and a proposed shortlist."""
    r = hr_client.post("/api/resumes/bulk-upload/", {"job": str(job.pk), "files": sample_files}, format="multipart")
    assert r.status_code == 201, r.content
    return job
