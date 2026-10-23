"""Write the synthetic sample job + resume files to disk (default: ../samples)."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.recruitment.sample_data import SAMPLE_JOB, SAMPLE_RESUMES, build_file


class Command(BaseCommand):
    help = "Export synthetic sample resumes (PDF/DOCX) and the example job description."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR).parent / "samples"))

    def handle(self, *args, **opts):
        out = Path(opts["out"])
        (out / "resumes").mkdir(parents=True, exist_ok=True)
        (out / "job_python_full_stack.json").write_text(json.dumps(SAMPLE_JOB, indent=2), encoding="utf-8")
        for spec in SAMPLE_RESUMES:
            (out / "resumes" / spec["filename"]).write_bytes(build_file(spec))
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(SAMPLE_RESUMES)} resumes and the job file to {out}"))
