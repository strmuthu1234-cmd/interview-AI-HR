"""Default, configurable organisation settings (scoring rubrics, weights, etc.).

Every weight set is stored per organisation so HR/Admin can change it in
Settings; these are only the initial values taken from the product spec.
"""
import copy

DEFAULT_ORG_SETTINGS = {
    # Resume screening rubric (percent weights, must total 100).
    "screening_weights": {
        "required_skills": 35,
        "experience": 25,
        "projects": 20,
        "preferred_skills": 10,
        "qualifications": 10,
    },
    # Per-answer rubrics (percent weights, each set totals 100).
    "answer_weights": {
        "technical": {"correctness": 40, "relevance": 25, "reasoning": 20, "examples": 15},
        "behavioral": {"relevance": 30, "reasoning": 25, "examples": 30, "job_alignment": 15},
    },
    # Final assessment (percent weights, total 100).
    "final_weights": {"resume": 20, "general": 15, "technical": 65},
    # Advisory bands, highest first.
    "bands": [
        {"min": 85, "label": "Strong match"},
        {"min": 70, "label": "Good match"},
        {"min": 50, "label": "Needs further review"},
        {"min": 0, "label": "Significant gaps identified"},
    ],
    "ai": {
        "provider": "",  # "", openai, anthropic, mock
        "model": "",
        # Resume text may only be sent to an external AI provider if HR enabled this.
        "allow_resume_sharing": False,
    },
    "voice": {
        "stt_provider": "browser",  # browser | server (OpenAI)
        "languages": ["en", "ta"],
        "allow_pause": True,
    },
    "interview": {
        "reveal_results_to_candidate": False,
        "invite_expiry_days": 7,
        "max_answer_seconds": 300,
    },
    "retention": {"audio_days": 90, "resume_days": 365, "interview_days": 365},
}

GENERAL_QUESTIONS = [
    {
        "text": "Please introduce yourself and walk us through your professional background and experience.",
        "is_self_introduction": True,
        "expected_points": [
            "current or most recent role",
            "years and areas of experience",
            "key skills and technologies",
            "notable accomplishments",
        ],
    },
    {
        "text": "Explain your current (or most recent) role and your key responsibilities.",
        "expected_points": ["role and scope", "day-to-day responsibilities", "tools and technologies used", "impact or outcomes"],
    },
    {
        "text": "Describe a challenging problem you solved. What was the situation, what did you do, and what was the result?",
        "expected_points": ["clear problem description", "specific actions taken", "reasoning behind choices", "measurable or concrete result"],
    },
    {
        "text": "Explain how you work with teams and how you handle deadlines.",
        "expected_points": ["collaboration practices", "communication", "prioritisation or planning", "handling pressure or conflict"],
    },
    {
        "text": "Why are you interested in this position, and what would you bring to it?",
        "expected_points": ["motivation tied to the role", "relevant strengths", "understanding of the job", "career goals"],
    },
]


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def get_org_settings(org):
    return deep_merge(DEFAULT_ORG_SETTINGS, getattr(org, "settings", None) or {})


def validate_weight_set(weights, name):
    if not isinstance(weights, dict) or not weights:
        raise ValueError(f"{name} must be an object of weights")
    total = 0
    for k, v in weights.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"{name}.{k} must be a non-negative number")
        total += v
    if abs(total - 100) > 0.01:
        raise ValueError(f"{name} weights must total 100 (got {total})")


def validate_org_settings(s):
    """Validate a merged settings dict; raises ValueError with a clear message."""
    validate_weight_set(s["screening_weights"], "screening_weights")
    validate_weight_set(s["final_weights"], "final_weights")
    for kind, weights in s["answer_weights"].items():
        validate_weight_set(weights, f"answer_weights.{kind}")
    mins = [b["min"] for b in s["bands"]]
    if not mins or mins != sorted(mins, reverse=True) or mins[-1] != 0:
        raise ValueError("bands must be ordered highest-first and end at 0")
    if s["ai"]["provider"] not in ("", "openai", "anthropic", "mock"):
        raise ValueError("ai.provider must be '', openai, anthropic or mock")
    return s


def band_for(score, org_settings):
    for band in org_settings["bands"]:
        if score >= band["min"]:
            return band["label"]
    return org_settings["bands"][-1]["label"]
