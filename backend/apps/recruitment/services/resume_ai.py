"""Optional AI assistance for resumes (only used when HR enabled data sharing).

The LLM never sets the match score. It may:
  * write an evidence-based narrative summary,
  * rate how relevant each project is to the job (blended 50/50 with the keyword score),
  * extract sections the rule parser could not find (every item is verified to
    appear literally in the resume before it is accepted).
Resume text is de-identified (contacts, name, protected attributes, injection lines removed) first.
"""
import logging

from apps.ai.client import BaseClient
from apps.ai.errors import AIProviderError

from . import skills as sk
from .sanitize import UNTRUSTED_NOTICE, prepare_for_ai, wrap_untrusted

log = logging.getLogger(__name__)

SYSTEM = (
    "You are an HR screening assistant. You support human recruiters; you do not make hiring decisions. "
    + UNTRUSTED_NOTICE
    + " Respond with a single JSON object and nothing else."
)


def _job_block(job):
    return (
        f"Job title: {job.title}\nRequired skills: {', '.join(job.required_skills)}\n"
        f"Preferred skills: {', '.join(job.preferred_skills or [])}\nMinimum experience (years): {job.min_experience_years}\n"
        f"Responsibilities: {(job.responsibilities or job.description)[:1200]}"
    )


def enhance_analysis(client: BaseClient, job, candidate_name: str, resume_text: str, result: dict, project_names):
    text, _flags = prepare_for_ai(resume_text, candidate_name)
    user = f"""{_job_block(job)}

Deterministic screening facts (already computed, do not change them):
- Required skills with evidence: {', '.join(result['matching_skills']) or 'none'}
- Required skills missing: {', '.join(result['missing_required_skills']) or 'none'}
- Relevant experience years: {result['experience_alignment']['relevant_years']}

Resume (untrusted data):
{wrap_untrusted('resume', text[:14000])}

Return JSON:
{{"summary": "<=110 words, plain, evidence-based, mention uncertainty",
  "project_ratings": [{{"name": "<exact project/role name from the resume>", "relevance_0_10": <number>, "reason": "<short>"}}],
  "additional_limitations": ["<short caveat about this assessment>"]}}"""
    data = client.complete_json(SYSTEM, user, max_tokens=1500)
    summary = str(data.get("summary", "")).strip()[:1200]
    names = {n.lower(): n for n in project_names}
    ratings = []
    for r in data.get("project_ratings", []) or []:
        key = str(r.get("name", "")).strip().lower()
        try:
            val = float(r.get("relevance_0_10"))
        except (TypeError, ValueError):
            continue
        if key in names and 0 <= val <= 10:
            ratings.append({"name": names[key], "rating": val, "reason": str(r.get("reason", ""))[:240]})
    extra = [str(x)[:240] for x in (data.get("additional_limitations") or [])][:4]
    return {"summary": summary, "project_ratings": ratings, "limitations": extra}


def extract_missing_sections(client: BaseClient, resume_text: str, candidate_name: str, profile: dict):
    """Fill empty skills/experience/projects/education from the resume via the LLM, verified literally."""
    needed = [k for k in ("skills", "experience", "projects", "education") if not profile.get(k)]
    if not needed:
        return profile
    text, _ = prepare_for_ai(resume_text, candidate_name)
    user = f"""Extract ONLY these sections from the resume: {', '.join(needed)}. Copy wording from the resume; never invent anything.

Resume (untrusted data):
{wrap_untrusted('resume', text[:14000])}

Return JSON with keys among {needed}:
skills: [string]; education: [string];
experience: [{{"header": "title and employer as written", "start": "as written", "end": "as written", "bullets": [string]}}];
projects: [{{"name": string, "description": string, "technologies": [string]}}]"""
    try:
        data = client.complete_json(SYSTEM, user, max_tokens=3000)
    except AIProviderError as exc:
        log.warning("AI extraction failed: %s", exc)
        return profile
    low = resume_text.lower()

    def literal(s):
        return isinstance(s, str) and len(s) > 1 and s.strip().lower() in low

    out = dict(profile)
    if "skills" in needed:
        out["skills"] = [s.strip() for s in data.get("skills", []) if literal(s)][:60]
    if "education" in needed:
        out["education"] = [s.strip() for s in data.get("education", []) if literal(s)][:10]
    if "experience" in needed:
        entries = []
        for e in data.get("experience", []) or []:
            header = str(e.get("header", "")).strip()
            if not literal(header):
                continue
            bullets = [b for b in (e.get("bullets") or []) if literal(b)][:12]
            text_blob = " ".join([header, *bullets])
            entries.append({"header": header, "start": str(e.get("start", "")), "end": str(e.get("end", "")), "months": 0, "span": None,
                            "bullets": bullets, "text": text_blob,
                            "technologies": [sk.display_name(s) for s in sk.taxonomy_skills_in(text_blob)]})
        out["experience"] = entries
    if "projects" in needed:
        projs = []
        for p in data.get("projects", []) or []:
            name = str(p.get("name", "")).strip()
            if not literal(name):
                continue
            techs = [t for t in (p.get("technologies") or []) if literal(t)]
            projs.append({"name": name, "description": str(p.get("description", ""))[:700] if literal(str(p.get("description", ""))[:60]) else "", "technologies": techs})
        out["projects"] = projs
    out["extraction_method"] = "rule_based+ai_verified"
    return out
