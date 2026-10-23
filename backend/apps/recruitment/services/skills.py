"""Skill taxonomy and deterministic skill matching.

Matching is literal (word-boundary aware) so a skill is only "found" if the
resume text really contains it – nothing is inferred or invented.
"""
import re

# canonical name -> aliases (all lower case). Canonical is also an alias.
TAXONOMY = {
    "python": [],
    "django": [],
    "django rest framework": ["drf", "django-rest-framework", "django rest"],
    "flask": [],
    "fastapi": [],
    "react": ["react.js", "reactjs"],
    "redux": [],
    "next.js": ["nextjs"],
    "vue": ["vue.js", "vuejs"],
    "angular": ["angularjs"],
    "javascript": ["js", "es6", "ecmascript"],
    "typescript": [],
    "node.js": ["nodejs", "node"],
    "express": ["express.js", "expressjs"],
    "html": ["html5"],
    "css": ["css3"],
    "tailwind css": ["tailwind", "tailwindcss"],
    "bootstrap": [],
    "postgresql": ["postgres", "psql"],
    "mysql": [],
    "sql": [],
    "mongodb": ["mongo"],
    "sqlite": [],
    "redis": [],
    "elasticsearch": [],
    "rest apis": ["rest api", "restful", "restful apis", "restful api", "rest"],
    "graphql": [],
    "git": ["github", "gitlab", "bitbucket"],
    "docker": ["containerization", "containers"],
    "kubernetes": ["k8s"],
    "aws": ["amazon web services", "ec2", "s3", "lambda"],
    "azure": [],
    "gcp": ["google cloud"],
    "ci/cd": ["cicd", "ci cd", "github actions", "jenkins", "gitlab ci"],
    "linux": [],
    "jwt": ["json web token", "json web tokens"],
    "oauth": ["oauth2", "oauth 2.0"],
    "celery": [],
    "rabbitmq": [],
    "kafka": [],
    "pytest": ["unit testing", "unittest"],
    "java": [],
    "spring boot": ["spring"],
    "c#": ["csharp"],
    ".net": ["dotnet", "asp.net"],
    "c++": ["cpp"],
    "golang": [],
    "php": ["laravel"],
    "ruby": ["rails", "ruby on rails"],
    "pandas": [],
    "numpy": [],
    "scikit-learn": ["sklearn"],
    "tensorflow": [],
    "pytorch": [],
    "machine learning": ["ml"],
    "terraform": [],
    "nginx": [],
    "agile": ["scrum"],
    "microservices": [],
    "orm": [],
    "websockets": ["websocket"],
}

_ALIAS_TO_CANON = {}
for canon, aliases in TAXONOMY.items():
    _ALIAS_TO_CANON[canon] = canon
    for a in aliases:
        _ALIAS_TO_CANON[a] = canon

# Aliases too ambiguous to count as evidence on their own (e.g. "rest", "js", "node", "ml", "spring", "s3").
_WEAK_ALIASES = {"rest", "js", "node", "ml", "spring", "lambda", "containers", "express", "orm"}


def canonical(skill: str) -> str:
    s = skill.strip().lower()
    return _ALIAS_TO_CANON.get(s, s)


def aliases_for(skill: str):
    canon = canonical(skill)
    names = {canon}
    for a, c in _ALIAS_TO_CANON.items():
        if c == canon and a not in _WEAK_ALIASES:
            names.add(a)
    if canon in TAXONOMY and skill.strip().lower() in _WEAK_ALIASES:
        names.add(skill.strip().lower())
    return sorted(names, key=len, reverse=True)


def _alias_regex(alias: str):
    return re.compile(r"(?<![A-Za-z0-9+#.])" + re.escape(alias) + r"(?![A-Za-z0-9+#]|\.[A-Za-z0-9])", re.I)


_cache = {}


def skill_pattern(skill: str):
    key = canonical(skill)
    if key not in _cache:
        _cache[key] = [_alias_regex(a) for a in aliases_for(skill)]
    return _cache[key]


def find_in_text(skill: str, text: str):
    """Return the first matching line from `text` containing `skill`, or None."""
    pats = skill_pattern(skill)
    for line in text.splitlines():
        if any(p.search(line) for p in pats):
            return line.strip()
    return None


def contains(skill: str, text: str) -> bool:
    return any(p.search(text) for p in skill_pattern(skill))


def taxonomy_skills_in(text: str):
    """All canonical taxonomy skills literally present in text (strong aliases only)."""
    found = []
    for canon in TAXONOMY:
        if canon in _WEAK_ALIASES:
            continue
        if contains(canon, text):
            found.append(canon)
    return found


def display_name(canon: str) -> str:
    special = {
        "aws": "AWS", "gcp": "GCP", "jwt": "JWT", "sql": "SQL", "css": "CSS", "html": "HTML", "ci/cd": "CI/CD",
        "oauth": "OAuth", "rest apis": "REST APIs", "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
        "node.js": "Node.js", "next.js": "Next.js", "c#": "C#", "c++": "C++", ".net": ".NET", "javascript": "JavaScript",
        "typescript": "TypeScript", "graphql": "GraphQL", "django rest framework": "Django REST Framework",
        "tailwind css": "Tailwind CSS", "fastapi": "FastAPI", "rabbitmq": "RabbitMQ", "orm": "ORM", "kafka": "Kafka",
        "scikit-learn": "scikit-learn", "pytorch": "PyTorch", "tensorflow": "TensorFlow", "nginx": "Nginx",
    }
    return special.get(canon, canon.title() if " " in canon or canon.isalpha() else canon)
