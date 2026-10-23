"""Short-lived signed tokens for streaming private files (resume preview, audio)."""
from django.core import signing

_SALT = "private-file-v1"


def sign_file_token(kind, pk, user_id):
    return signing.dumps({"k": kind, "pk": str(pk), "u": str(user_id)}, salt=_SALT)


def read_file_token(token, kind, max_age=300):
    try:
        data = signing.loads(token, salt=_SALT, max_age=max_age)
    except signing.BadSignature:
        return None
    return data if data.get("k") == kind else None
