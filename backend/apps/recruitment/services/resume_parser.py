"""Deterministic rule-based resume parser.

Everything returned is traceable to text in the resume: skills carry the source
line (`evidence`), nothing is inferred or invented, and missing information is
left empty.
"""
import re
from datetime import date

from . import skills as sk
from .sanitize import EMAIL_RE, PHONE_RE, YEAR_RANGE_RE

SECTION_HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "professional profile", "objective", "career objective", "about me", "about"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technologies", "tech stack", "skills & tools", "skills and tools", "technical proficiency"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "employment", "work history", "internship", "internships", "relevant experience"],
    "education": ["education", "academic background", "academics", "educational qualification", "educational qualifications", "academic qualifications"],
    "certifications": ["certifications", "certification", "certificates", "licenses", "courses", "training", "licenses & certifications"],
    "projects": ["projects", "personal projects", "academic projects", "key projects", "project experience", "selected projects"],
    "achievements": ["achievements", "awards", "accomplishments", "honors", "awards & achievements"],
}
_HEADING_LOOKUP = {h: sec for sec, hs in SECTION_HEADINGS.items() for h in hs}

BULLET_RE = re.compile(r"^\s*(?:[••●▪◦‣\-*–·>]|\d+[.)])\s+")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE = r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*,?\s*)?(?:19|20)\d{2}"
RANGE_RE = re.compile(rf"({_DATE})\s*(?:-|–|—|\bto\b)\s*({_DATE}|present|current|now|till\s+date|ongoing)", re.I)
STATED_YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:\w+\s+){0,3}?experience", re.I)
TECH_LABEL_RE = re.compile(r"(?:tech(?:nologies)?(?:\s+stack)?|tools?|stack|built\s+with|environment)\s*[:\-]\s*(.+)", re.I)


def _heading_of(line: str):
    s = re.sub(r"[:\-–_=*#|]+$", "", line.strip()).strip().lower()
    s = re.sub(r"^[#*\-–_=\s]+", "", s)
    if 2 < len(s) < 40:
        return _HEADING_LOOKUP.get(s)
    return None


def split_sections(text: str):
    sections = {"header": []}
    current = "header"
    for line in text.splitlines():
        sec = _heading_of(line)
        if sec:
            current = sec
            sections.setdefault(current, [])
            continue
        sections[current].append(line.rstrip())
    return sections


def _parse_date(s: str, end: bool):
    s = s.strip().lower()
    if re.match(r"present|current|now|till|ongoing", s):
        today = date.today()
        return today.year, today.month
    year = int(re.search(r"(?:19|20)\d{2}", s).group())
    m = re.match(r"([a-z]{3})", s)
    month = MONTHS.get(m.group(1)) if m else None
    return year, month or (12 if end else 1)


def _range_months(a: str, b: str):
    sy, sm = _parse_date(a, False)
    ey, em = _parse_date(b, True)
    months = (ey - sy) * 12 + (em - sm) + 1
    return (sy * 12 + sm, ey * 12 + em, months) if months > 0 else None


def _merge_months(ranges):
    """Total months across ranges without double counting overlaps."""
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(ranges):
        if cur_e is None or s > cur_e + 1:
            if cur_e is not None:
                total += cur_e - cur_s + 1
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s + 1
    return total


def _clean(s):
    return re.sub(r"\s+", " ", s).strip(" \t|-–—•·,")


def parse_name(header_lines):
    for line in header_lines[:8]:
        s = line.strip()
        if not s or EMAIL_RE.search(s) or re.search(r"\d", s) or _heading_of(s):
            continue
        if re.search(r"resume|curriculum|vitae|cv\b", s, re.I):
            continue
        words = s.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            return " ".join(w.capitalize() if w.isupper() else w for w in words)
    return ""


def parse_phone(text):
    for m in PHONE_RE.finditer(text):
        s = m.group().strip()
        if YEAR_RANGE_RE.match(s):
            continue
        digits = re.sub(r"\D", "", s)
        if 10 <= len(digits) <= 15:
            return _clean(s)
    return ""


def parse_experience(lines):
    entries, current, pending = [], None, None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = RANGE_RE.search(line)
        is_bullet = bool(BULLET_RE.match(line))
        if m and not is_bullet:
            rng = _range_months(m.group(1), m.group(2))
            rest = _clean(RANGE_RE.sub("", line).replace("()", "").replace("[]", ""))
            header = rest if len(rest) >= 3 else (pending or "")
            current = {"header": header, "start": m.group(1).strip(), "end": m.group(2).strip(), "months": rng[2] if rng else 0,
                       "span": (rng[0], rng[1]) if rng else None, "bullets": []}
            entries.append(current)
            pending = None
        elif current is None:
            if not is_bullet:
                pending = _clean(line)
        elif is_bullet:
            current["bullets"].append(BULLET_RE.sub("", line).strip())
        elif current["bullets"]:
            # A new non-bullet line after bullets starts the next block (its title precedes the date line).
            pending, current = _clean(line), None
        elif len(line) < 90:
            current["header"] = _clean(f"{current['header']} | {line}") if current["header"] else _clean(line)
        else:
            current["bullets"].append(line)
    for e in entries:
        e["text"] = " ".join([e["header"], *e["bullets"]])
        e["technologies"] = [sk.display_name(s) for s in sk.taxonomy_skills_in(e["text"])]
    return entries


def parse_projects(lines):
    projects, current, prev_blank = [], None, True
    for raw in lines:
        line = raw.strip()
        if not line:
            prev_blank = True
            continue
        is_bullet = bool(BULLET_RE.match(line))
        starts_new = not is_bullet and (current is None or prev_blank or current["_lines"] and current["_bullet_seen"])
        if starts_new:
            title = _clean(re.split(r"\s[–—|]\s|:\s", line, maxsplit=1)[0])
            tail = line[len(title):].lstrip(" :–—|-").strip() if len(line) > len(title) else ""
            current = {"name": title[:120], "_lines": [tail] if tail else [], "_bullet_seen": False}
            projects.append(current)
        elif current is not None:
            current["_lines"].append(BULLET_RE.sub("", line).strip())
            current["_bullet_seen"] = current["_bullet_seen"] or is_bullet
        prev_blank = False
    out = []
    for p in projects:
        desc = " ".join(p["_lines"]).strip()
        text = f"{p['name']} {desc}"
        techs = {sk.canonical(s): sk.display_name(s) for s in sk.taxonomy_skills_in(text)}
        for m in TECH_LABEL_RE.finditer(text):
            for tok in re.split(r"[,;/|]", m.group(1)):
                tok = _clean(tok)
                if 1 < len(tok) <= 30:
                    techs.setdefault(sk.canonical(tok), tok)
        out.append({"name": p["name"], "description": desc[:700], "technologies": list(techs.values())})
    return out


def parse_skills(lines, full_text):
    found, evidence = {}, {}
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        body = re.sub(r"^[^:,]{1,30}:\s*", "", BULLET_RE.sub("", line)) if ":" in line else BULLET_RE.sub("", line)
        for tok in re.split(r"[,|;•·•/]|\s{2,}", body):
            tok = _clean(tok)
            if 1 < len(tok) <= 40 and not _heading_of(tok) and len(tok.split()) <= 4:
                key = sk.canonical(tok)
                found.setdefault(key, sk.display_name(key) if key in sk.TAXONOMY else tok)
                evidence.setdefault(key, line)
    for canon in sk.taxonomy_skills_in("\n".join(lines)):
        found.setdefault(canon, sk.display_name(canon))
        evidence.setdefault(canon, sk.find_in_text(canon, "\n".join(lines)) or "")
    return list(found.values()), {found[k]: v for k, v in evidence.items() if k in found}


def parse_resume(text: str) -> dict:
    sections = split_sections(text)
    header = sections.get("header", [])
    skills_list, skill_evidence = parse_skills(sections.get("skills", []), text)
    experience = parse_experience(sections.get("experience", []))
    projects = parse_projects(sections.get("projects", []))

    spans = [e["span"] for e in experience if e.get("span")]
    total_years, years_source = 0.0, "none"
    if spans:
        total_years, years_source = round(_merge_months(spans) / 12, 1), "dates"
    else:
        m = STATED_YEARS_RE.search(text)
        if m:
            total_years, years_source = float(m.group(1)), "stated_in_resume"

    tech = {sk.canonical(s): sk.display_name(s) for s in sk.taxonomy_skills_in(
        "\n".join(e["text"] for e in experience) + "\n" + "\n".join(f"{p['name']} {p['description']}" for p in projects))}
    for s in skills_list:
        tech.setdefault(sk.canonical(s), s)

    achievements = []
    for e in experience:
        for b in e["bullets"]:
            if re.search(r"\d+\s*%|\b\d+[kKmM]?\+?\s*(users|customers|requests|clients|records)|(reduced|improved|increased|led|delivered|saved)\b", b, re.I):
                achievements.append(b[:300])
    summary_lines = [l.strip() for l in sections.get("summary", []) if l.strip()]

    for e in experience:
        e["span"] = list(e["span"]) if e.get("span") else None
    return {
        "name": parse_name(header),
        "email": (EMAIL_RE.search(text).group() if EMAIL_RE.search(text) else ""),
        "phone": parse_phone("\n".join(header) or text[:600]),
        "summary": " ".join(summary_lines)[:800],
        "skills": skills_list,
        "technologies": list(tech.values()),
        "experience": experience,
        "total_experience_years": total_years,
        "experience_years_source": years_source,
        "education": [_clean(BULLET_RE.sub("", l)) for l in sections.get("education", []) if l.strip()][:10],
        "certifications": [_clean(BULLET_RE.sub("", l)) for l in sections.get("certifications", []) if l.strip()][:15],
        "projects": projects,
        "achievements": achievements[:8],
        "evidence": {"skills": skill_evidence},
        "extraction_method": "rule_based",
    }
