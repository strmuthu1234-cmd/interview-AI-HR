"""Create a demo organisation, users and the sample job. Optionally upload the synthetic resumes.

    python manage.py seed_demo                 # org + users + job
    python manage.py seed_demo --with-resumes  # also upload and screen the 11 synthetic resumes
Passwords come from DEMO_ADMIN_PASSWORD / DEMO_HR_PASSWORD or are generated and printed once.
"""
import os
import secrets

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.accounts.models import Organization, User
from apps.recruitment.models import Candidate, JobPosting, Resume, ScreeningBatch
from apps.recruitment.sample_data import SAMPLE_JOB, SAMPLE_RESUMES, build_file
from apps.recruitment.tasks import process_resume_task
import hashlib


class Command(BaseCommand):
    help = "Seed a demo organisation, admin/HR users and a sample job (synthetic data only)."

    def add_arguments(self, parser):
        parser.add_argument("--with-resumes", action="store_true")

    def handle(self, *args, **opts):
        org, _ = Organization.objects.get_or_create(slug="demo", defaults={"name": "Demo Company"})
        creds = []
        for username, role, env in (("admin", User.Role.ADMIN, "DEMO_ADMIN_PASSWORD"), ("hr", User.Role.HR_MANAGER, "DEMO_HR_PASSWORD")):
            user = User.objects.filter(username=username).first()
            if user is None:
                pw = os.environ.get(env) or secrets.token_urlsafe(12)
                user = User.objects.create_user(username=username, email=f"{username}@demo.example.com", password=pw, role=role, organization=org)
                creds.append((username, pw))
        job, created = JobPosting.objects.get_or_create(organization=org, title=SAMPLE_JOB["title"], defaults={**SAMPLE_JOB, "created_by": User.objects.get(username="hr")})
        for u, p in creds:
            self.stdout.write(self.style.WARNING(f"Created user '{u}' with password: {p}  (shown once)"))
        self.stdout.write(self.style.SUCCESS(f"Org '{org.name}', job '{job.title}' ready."))
        if opts["with_resumes"]:
            batch = ScreeningBatch.objects.create(organization=org, job=job, created_by=User.objects.get(username="hr"), total_files=len(SAMPLE_RESUMES))
            ids = []
            for spec in SAMPLE_RESUMES:
                data = build_file(spec)
                sha = hashlib.sha256(data).hexdigest()
                if Resume.objects.filter(job=job, sha256=sha).exists():
                    continue
                cand = Candidate.objects.create(organization=org, job=job, batch=batch, full_name=spec["filename"].rsplit(".", 1)[0])
                res = Resume(organization=org, job=job, batch=batch, candidate=cand, original_filename=spec["filename"], file_type=spec["format"], file_size=len(data), sha256=sha)
                res.file.save(spec["filename"], ContentFile(data), save=False)
                res.save()
                ids.append(str(res.pk))
            for rid in ids:
                process_resume_task.delay(rid)
            self.stdout.write(self.style.SUCCESS(f"Uploaded {len(ids)} synthetic resumes for screening."))
