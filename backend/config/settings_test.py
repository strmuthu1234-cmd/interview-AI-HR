"""Settings used by the automated test-suite (SQLite, eager Celery, temp media, no real AI keys)."""
import os
import tempfile

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ["DATABASE_URL"] = "sqlite://:memory:"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["AI_PROVIDER"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

from .settings import *  # noqa: E402,F401,F403

MEDIA_ROOT = tempfile.mkdtemp(prefix="hrai-test-media-")
CELERY_TASK_EAGER_PROPAGATES = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {k: "100000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SECURE_SSL_REDIRECT = False
