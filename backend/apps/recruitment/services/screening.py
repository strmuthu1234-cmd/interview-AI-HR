"""Deterministic, explainable resume-vs-job scoring.

Match score = weighted sum of five categories (weights configurable per org):
required skills 35, experience 25, projects 20, preferred skills 10, qualifications 10.

Rules that keep scoring fair and auditable:
* Only text that is literally in the resume can earn credit; each credit stores
  the supporting snippet.
* Lines about protected characteristics are removed before scoring.
* Categories that do not apply (e.g. a job with no preferred skills) are dropped
  and the remaining weights are renormalised – shown to HR in `category_scores`.
"""
import re

from . import skills as sk
from .resume_parser import _merge_months
from .sanitize import split_protected

LISTED_ONLY_CREDIT = 0.7  # skill appears in the resume but with no demonstrated use

DEGREE_GROUPS = [
    {"bachelor", "bachelors", "b.e", "b.tech", "btech", "bsc", "b.sc", "be", "bca", "b.sc.", "undergraduate", "degree", "graduate"},
    {"master", "masters", "m.e", "m.tech", "mtech", "msc", "m.sc", "mca", "mba", "postgraduate", "m.s"},
    {"phd", "ph.d", "doctorate", "doctoral"},
]
STOPWORDS = {"the", "and", "for", "with", "from", "any", "has", "have", "who", "minimum", "years", "year", "experience", "relevant",
             "field", "fields", "subject", "area", "discipline", "equivalent", "related", "similar", "such", "also", "must", "should", "required"}


def _tokens(s):
    return [t.replace("'s", "").strip(".,;:()") for t in re.findall(r"[A-Za-z][A-Za-z.+#']+", s.lower()) if len(t) >= 2]


def qualification_met(qual: str, text: str):
    """Return (met, snippet). Keyword-based check; HR verifies in review."""
    low = text.lower()
    toks = [t for t in _tokens(qual) if t not in STOPWORDS and t not in {"in", "of", "or", "an", "a", "to", "at", "on"}]
    degree_levels = []
    for t in toks:
        for grp in DEGREE_GROUPS:
            if t in grp and grp not in degree_levels:
                degree_levels.append(grp)
    flexible = bool(re.search(r"related|equivalent", qual, re.I))

    def present(t):
        return re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low) is not None

    def group_present(grp):
        return any(present(g) for g in grp)

    checks = []
    for t in toks:
        in_group = next((g for g in degree_levels if t in g), None)
        if in_group is not None:
            checks.append(group_present(in_group) or (t == "degree" and any(group_present(g) for g in DEGREE_GROUPS)))
        elif sk.canonical(t) in sk.TAXONOMY or len(t) > 3:
            checks.append(present(t) or sk.contains(t, text))
    if not checks:
        return False, None
    if flexible and degree_levels:
        degree_checks = [group_present(g) for g in degree_levels]
        met = all(degree_checks)
    else:
        met = sum(checks) / len(checks) >= 0.6
    snippet = None
    if met:
        for line in text.splitlines():
            ll = line.lower()
            if any(present_t in ll for present_t in toks[:6] if len(present_t) > 2):
                snippet = line.strip()[:200]
                break
    return met, snippet


def _skill_credit(skill, usage_text, listed_text):
    s = sk.find_in_text(skill, usage_text)
    if s:
        return 1.0, s, "demonstrated"
    s = sk.find_in_text(skill, listed_text)
    if s:
        return LISTED_ONLY_CREDIT, s, "listed_only"
    return 0.0, None, "missing"


def _score_skill_list(skill_list, usage_text, listed_text, category, evidence, matching):
    if not skill_list:
        return None, {}
    detail, total = {}, 0.0
    for s in skill_list:
        credit, snippet, kind = _skill_credit(s, usage_text, listed_text)
        total += credit
        detail[s] = {"status": kind, "credit": credit}
        if snippet:
            evidence.append({"category": category, "claim": s, "snippet": snippet[:240], "status": kind})
            matching.append(s)
    return round(100 * total / len(skill_list), 2), detail


def _job_title_terms(title):
    return {t for t in _tokens(title) if len(t) > 3 and t not in {"senior", "junior", "lead", "associate", "intern", "engineer"}}


def score_resume(profile: dict, resume_text: str, job, weights: dict) -> dict:
    text, _removed = split_protected(resume_text)
    required = [s for s in (job.required_skills or []) if str(s).strip()]
    preferred = [s for s in (job.preferred_skills or []) if str(s).strip()]
    experience = profile.get("experience") or []
    projects = profile.get("projects") or []
    limitations, evidence, matching = [], [], []

    usage_text = "\n".join([e.get("text", "") for e in experience] + [f"{p.get('name', '')} {p.get('description', '')}" for p in projects])
    if not usage_text.strip():
        usage_text = text
        limitations.append("No work-experience or project sections could be identified; skills found anywhere in the resume were treated as demonstrated.")
    listed_text = text

    cats = {}
    # --- required skills
    req_score, req_detail = _score_skill_list(required, usage_text, listed_text, "required_skills", evidence, matching)
    cats["required_skills"] = {"score": req_score, "detail": req_detail}
    missing_required = [s for s, d in req_detail.items() if d["status"] == "missing"]
    listed_only = [s for s, d in req_detail.items() if d["status"] == "listed_only"]

    # --- preferred skills
    pref_matching = []
    pref_score, pref_detail = _score_skill_list(preferred, usage_text, listed_text, "preferred_skills", evidence, pref_matching)
    cats["preferred_skills"] = {"score": pref_score, "detail": pref_detail}
    matching += pref_matching

    # --- experience
    min_y = float(job.min_experience_years or 0)
    max_y = float(job.max_experience_years) if job.max_experience_years is not None else None
    skill_pool = required + preferred
    title_terms = _job_title_terms(job.title)
    relevant_spans, relevant_entries = [], []
    for e in experience:
        blob = e.get("text", "")
        hit_skill = any(sk.contains(s, blob) for s in skill_pool)
        hit_title = any(re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", blob.lower()) for t in title_terms)
        if hit_skill or hit_title:
            relevant_entries.append(e)
            if e.get("span"):
                relevant_spans.append(tuple(e["span"]))
            evidence.append({"category": "experience", "claim": f"Relevant role: {e.get('header', '')[:80]}",
                             "snippet": (e.get("header", "") + f" ({e.get('start', '')} – {e.get('end', '')})")[:240], "status": "demonstrated"})
    total_years = float(profile.get("total_experience_years") or 0)
    if profile.get("experience_years_source") == "dates":
        relevant_years = round(_merge_months(relevant_spans) / 12, 1)
    else:
        relevant_years = total_years
        if total_years:
            limitations.append("Years of experience are stated in the resume but could not be verified from dated roles.")
        else:
            limitations.append("No dated work experience could be identified.")
    if min_y > 0:
        exp_score = min(100.0, round(100 * relevant_years / min_y, 2))
    else:
        exp_score = 100.0 if (relevant_entries or total_years) else 0.0
    status = "meets requirement"
    if relevant_years < min_y:
        status = "below minimum"
    elif max_y is not None and relevant_years > max_y:
        status = "above stated range"
    experience_alignment = {"required_min_years": min_y, "required_max_years": max_y, "total_years": total_years,
                            "relevant_years": relevant_years, "relevant_roles": [e.get("header", "") for e in relevant_entries],
                            "years_source": profile.get("experience_years_source", "none"), "status": status}
    cats["experience"] = {"score": exp_score, "detail": experience_alignment}

    # --- projects (falls back to roles when no projects section exists)
    items = [{"name": p.get("name", ""), "text": f"{p.get('name', '')} {p.get('description', '')}", "kind": "project", "snippet": p.get("description", "")} for p in projects]
    if not items:
        items = [{"name": e.get("header", ""), "text": e.get("text", ""), "kind": "role", "snippet": "; ".join(e.get("bullets", [])[:2])} for e in experience]
        if items:
            limitations.append("No projects section found; work-experience entries were used to assess practical project relevance.")
    base = required or preferred
    rel_projects = []
    for it in items:
        matched = [s for s in (required + preferred) if sk.contains(s, it["text"])]
        denom = len(base) or 1
        rel = len([s for s in matched if s in base]) / denom
        if matched:
            rel_projects.append({"name": it["name"][:120], "kind": it["kind"], "matched_skills": matched, "relevance_pct": round(100 * rel),
                                 "snippet": it["snippet"][:240], "_rel": rel})
    rel_projects.sort(key=lambda p: p["_rel"], reverse=True)
    top = rel_projects[:3]
    proj_score = min(100.0, round(100 * sum(p["_rel"] for p in top), 2)) if base else None
    for p in top:
        evidence.append({"category": "projects", "claim": f"{p['kind'].title()}: {p['name']}", "snippet": p["snippet"] or ", ".join(p["matched_skills"]), "status": "demonstrated"})
    cats["projects"] = {"score": proj_score, "detail": {"considered": len(items), "top_relevant": [p["name"] for p in top]}}
    for p in rel_projects:
        p.pop("_rel")

    # --- qualifications
    quals = [q for q in (job.mandatory_qualifications or []) if str(q).strip()]
    qual_detail, met_count = {}, 0
    for q in quals:
        met, snip = qualification_met(q, text)
        qual_detail[q] = {"met": met}
        met_count += met
        if met:
            evidence.append({"category": "qualifications", "claim": q, "snippet": snip or "", "status": "demonstrated"})
    cats["qualifications"] = {"score": round(100 * met_count / len(quals), 2) if quals else None, "detail": qual_detail}
    if quals:
        limitations.append("Mandatory qualifications are checked by keyword matching; HR should verify credentials.")

    # --- weights (renormalised over applicable categories)
    applicable = {k: v for k, v in cats.items() if v["score"] is not None and weights.get(k, 0) > 0}
    wsum = sum(weights[k] for k in applicable) or 1
    total = 0.0
    for k, v in cats.items():
        v["weight"] = weights.get(k, 0)
        v["applicable"] = k in applicable
        v["effective_weight"] = round(100 * weights[k] / wsum, 2) if k in applicable else 0
        if k in applicable:
            total += v["score"] * weights[k] / wsum
    return {
        "match_score": round(min(100.0, max(0.0, total)), 2),
        "category_scores": cats,
        "matching_skills": list(dict.fromkeys(matching)),
        "missing_required_skills": missing_required,
        "listed_only_skills": listed_only,
        "relevant_projects": rel_projects[:6],
        "experience_alignment": experience_alignment,
        "evidence": evidence,
        "limitations": limitations,
    }


def build_summary(job, result) -> str:
    req_total = len(result["category_scores"]["required_skills"]["detail"])
    req_missing = result["missing_required_skills"]
    ea = result["experience_alignment"]
    bits = [f"Match score {result['match_score']:.0f}/100 for {job.title}."]
    if req_total:
        bits.append(f"Evidence found for {req_total - len(req_missing)} of {req_total} required skills"
                    + (f"; not found: {', '.join(req_missing)}." if req_missing else "."))
    if result.get("listed_only_skills"):
        bits.append(f"Listed without demonstrated use: {', '.join(result['listed_only_skills'])}.")
    bits.append(f"Relevant experience {ea['relevant_years']} yrs vs {ea['required_min_years']:g}+ required ({ea['status']}).")
    if result["relevant_projects"]:
        bits.append("Most relevant: " + "; ".join(p["name"] for p in result["relevant_projects"][:2]) + ".")
    return " ".join(bits)
