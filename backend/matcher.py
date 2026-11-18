"""Parsing + matching logic (no web / DB code here, so it is easy to test)."""
import io
import re
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------- skills ----
# canonical skill -> accepted spellings. Edit freely.
SKILLS = {
    "python": ["python"], "java": ["java"], "javascript": ["javascript", "js"],
    "typescript": ["typescript"], "react": ["react", "react.js", "reactjs"],
    "angular": ["angular"], "vue": ["vue", "vue.js"],
    "node.js": ["node.js", "nodejs"], "fastapi": ["fastapi"], "django": ["django"],
    "flask": ["flask"], "spring boot": ["spring boot", "springboot"],
    "sql": ["sql"], "postgresql": ["postgresql", "postgres"], "mysql": ["mysql"],
    "mongodb": ["mongodb", "mongo"], "redis": ["redis"],
    "aws": ["aws", "amazon web services"], "azure": ["azure"], "gcp": ["gcp", "google cloud"],
    "docker": ["docker"], "kubernetes": ["kubernetes", "k8s"], "ci/cd": ["ci/cd", "cicd", "jenkins"],
    "git": ["git", "github"], "linux": ["linux"], "rest api": ["rest api", "rest apis", "restful"],
    "microservices": ["microservices", "microservice"],
    "machine learning": ["machine learning"], "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"], "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"], "scikit-learn": ["scikit-learn", "sklearn"],
    "pandas": ["pandas"], "data analysis": ["data analysis", "data analytics"],
    "excel": ["excel"], "html": ["html", "html5"], "css": ["css", "css3"],
}
# Related skills give PARTIAL credit (semantic / transferable skill matching).
_PAIRS = [
    ("postgresql", "mysql"), ("postgresql", "sql"), ("mysql", "sql"),
    ("fastapi", "flask"), ("fastapi", "django"), ("flask", "django"),
    ("aws", "azure"), ("aws", "gcp"), ("azure", "gcp"),
    ("tensorflow", "pytorch"), ("machine learning", "deep learning"),
    ("machine learning", "scikit-learn"), ("deep learning", "tensorflow"),
    ("deep learning", "pytorch"), ("nlp", "machine learning"),
    ("react", "angular"), ("react", "vue"), ("angular", "vue"),
    ("kubernetes", "docker"), ("mongodb", "redis"), ("java", "spring boot"),
    ("javascript", "typescript"), ("node.js", "javascript"),
]
RELATED = {}
for _a, _b in _PAIRS:
    RELATED.setdefault(_a, set()).add(_b)
    RELATED.setdefault(_b, set()).add(_a)
RELATED_CREDIT = 0.5

_SKILL_RE = {
    name: re.compile(r"(?<![\w.])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![\w])", re.I)
    for name, aliases in SKILLS.items()
}


def find_skills(text):
    return sorted(name for name, rx in _SKILL_RE.items() if rx.search(text))


# ------------------------------------------------------------ experience ----
_NUM = r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?\s*\+?\s*(?:years?|yrs?)"
_EXPLICIT = [
    re.compile(_NUM + r"(?:\s+of)?(?:\s+[\w/.&+-]+){0,4}?\s+experience", re.I),
    re.compile(r"experience\s*(?:of|:|-)?\s*(?:at least\s*)?" + _NUM, re.I),
    re.compile(r"(?:minimum|at least|min\.?)\s*(?:of\s*)?" + _NUM, re.I),
]
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_RANGE = re.compile(
    rf"(?:({_MON})[\s,]+)?((?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*"
    rf"(?:(?:({_MON})[\s,]+)?((?:19|20)\d{{2}})|(present|current|now|till date|ongoing))", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_EDU_LINE = re.compile(r"\b(b\.?tech|m\.?tech|b\.?sc|m\.?sc|bca|mca|mba|bachelor|master|ph\.?d|diploma|"
                       r"university|college|school|institute|degree|cgpa|gpa|graduat)", re.I)


def explicit_years(text):
    vals = [float(m.group(1)) for rx in _EXPLICIT for m in rx.finditer(text)]
    return max(vals, default=0.0)


def date_range_years(text):
    """Total working time from 'Jan 2019 - Present' style ranges (overlaps merged)."""
    today = date.today()
    spans = []
    for line in text.splitlines():
        if _EDU_LINE.search(line):          # ignore study periods
            continue
        for m in _RANGE.finditer(line):
            sm, sy, em, ey, present = m.groups()
            start = int(sy) * 12 + (_MONTHS[sm[:3].lower()] if sm else 1)
            if present:
                end = today.year * 12 + today.month
            else:
                end = int(ey) * 12 + (_MONTHS[em[:3].lower()] if em else 12)
            end = min(end, today.year * 12 + today.month) + 1      # end month is inclusive
            if 0 < end - start <= 12 * 45 and int(sy) <= today.year:
                spans.append((start, end))
    spans.sort()
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return round(total / 12, 1)


def resume_years(text):
    return max(explicit_years(text), date_range_years(text))


# ------------------------------------------------------------- education ----
_LEVELS = [
    (4, "PhD", re.compile(r"\bph\.?d\b|doctorate", re.I)),
    (3, "Master's", re.compile(r"\bmaster'?s?\b|\bm\.?tech\b|\bm\.?sc\b|\bmba\b|\bmca\b", re.I)),
    (2, "Bachelor's", re.compile(r"\bbachelor'?s?\b|\bb\.?tech\b|\bb\.?sc\b|\bbca\b|\bundergraduate\b", re.I)),
    (1, "Diploma", re.compile(r"\bdiploma\b", re.I)),
]
LEVEL_NAME = {lvl: name for lvl, name, _ in _LEVELS}


def education_levels(text):
    return [lvl for lvl, _, rx in _LEVELS if rx.search(text)]


# --------------------------------------------------------------- details ----
_STOP = {"resume", "curriculum", "vitae", "cv", "profile", "summary", "contact", "email", "phone",
         "engineer", "developer", "analyst", "scientist", "manager", "experience", "education", "skills"}


def candidate_name(text, filename):
    for line in text.splitlines()[:8]:
        line = line.strip()
        words = line.split()
        if (2 <= len(words) <= 4 and re.fullmatch(r"[A-Za-z][A-Za-z.'\- ]+", line)
                and not {w.lower().strip(".") for w in words} & _STOP):
            return line.title() if line.isupper() else line
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


def candidate_phone(text):
    for m in re.finditer(r"\+?\d[\d \t().-]{8,16}\d", text):
        s = m.group(0).strip()
        if 10 <= len(re.sub(r"\D", "", s)) <= 13 and not re.match(r"(19|20)\d{2}\D+(19|20)\d{2}", s):
            return s
    return None


def candidate_email(text):
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    return m.group(0) if m else None


# --------------------------------------------------------- file reading ----
def extract_text(filename, data):
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        import fitz  # PyMuPDF
        with fitz.open(stream=data, filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
    elif ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
        for table in doc.tables:
            text += "\n" + "\n".join(" | ".join(c.text for c in row.cells) for row in table.rows)
    elif ext == ".txt":
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Only PDF and DOCX files are supported.")
    if len(text.strip()) < 30:
        raise ValueError("No readable text found (scanned PDFs need OCR).")
    return text


# ------------------------------------------------------------- semantics ----
_model = None  # None = not tried yet, False = unavailable, else the model


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _model = False
    return _model or None


def semantic_backend():
    return "sentence-transformers (all-MiniLM-L6-v2)" if _get_model() else "TF-IDF cosine (fallback)"


def split_lines(text, min_len=18, limit=200):
    out = []
    for raw in text.splitlines():
        for part in re.split(r"(?<=[.;])\s+", raw):
            part = re.sub(r"^\s*(?:[•\-*▪●·]|\d{1,2}[.)])\s*", "", part).strip()
            if len(part) >= min_len:
                out.append(part)
    return out[:limit]


def semantic_score(jd_lines, resume_lines):
    """For every JD requirement find the most similar resume line; average the best matches.

    Returns (score 0-100, list of (requirement, best_resume_line, similarity 0-1))."""
    if not jd_lines or not resume_lines:
        return 0.0, []
    model = _get_model()
    if model:
        import numpy as np
        vec = model.encode(jd_lines + resume_lines, normalize_embeddings=True)
        sims = np.asarray(vec[:len(jd_lines)] @ vec[len(jd_lines):].T)
        lo, hi = 0.15, 0.60        # MiniLM: <0.15 unrelated, >0.60 clearly same meaning
    else:
        from sklearn.feature_extraction.text import TfidfVectorizer
        mat = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform(jd_lines + resume_lines)
        sims = (mat[:len(jd_lines)] @ mat[len(jd_lines):].T).toarray()
        lo, hi = 0.05, 0.40
    best_idx, best = sims.argmax(axis=1), sims.max(axis=1)
    score = float(((best - lo) / (hi - lo)).clip(0, 1).mean() * 100)
    evidence = [(jd_lines[i], resume_lines[int(best_idx[i])], float(best[i])) for i in range(len(jd_lines))]
    return score, evidence


# ----------------------------------------------------------- JD analysis ----
_REQ_KEYS = re.compile(r"\b(must|required|requirement|experience|proficien|knowledge|familiar|degree|"
                       r"bachelor|master|skill|strong|ability|hands-on|expertise)", re.I)


_OPTIONAL = re.compile(r"nice to have|good to have|preferred|bonus|optional|a plus|is a plus|exposure to", re.I)
OPTIONAL_WEIGHT = 0.5   # 'nice to have' skills count half as much as required ones


def analyze_jd(text):
    levels = education_levels(text)
    optional_text = "\n".join(l for l in text.splitlines() if _OPTIONAL.search(l))
    required_text = "\n".join(l for l in text.splitlines() if not _OPTIONAL.search(l))
    optional = sorted(set(find_skills(optional_text)) - set(find_skills(required_text)))
    lines = split_lines(text, min_len=15, limit=40)
    return {
        "skills": find_skills(text), "optional_skills": optional,
        "required_years": explicit_years(text),
        "required_education_level": min(levels) if levels else 0,
        "required_education": LEVEL_NAME.get(min(levels)) if levels else None,
        "requirements": [l for l in lines if _REQ_KEYS.search(l)][:10],
        "lines": lines,
    }


# --------------------------------------------------------------- scoring ----
WEIGHTS = {"skills": 0.50, "semantic": 0.25, "experience": 0.15, "education": 0.10}


def score_resume(jd, text):
    """jd = output of analyze_jd(). Returns a fully explainable result dict."""
    r_skills = set(find_skills(text))
    jd_skills = jd["skills"]
    matched = sorted(set(jd_skills) & r_skills)
    related, missing = [], []
    for s in jd_skills:
        if s in r_skills:
            continue
        alt = sorted(RELATED.get(s, set()) & r_skills)
        (related if alt else missing).append({"skill": s, "has": alt} if alt else s)
    wt = lambda sk: OPTIONAL_WEIGHT if sk in jd.get("optional_skills", []) else 1.0
    earned = sum(wt(x) for x in matched) + RELATED_CREDIT * sum(wt(r["skill"]) for r in related)
    skill_score = earned / sum(wt(x) for x in jd_skills) * 100 if jd_skills else None

    sem, evidence = semantic_score(jd["lines"], split_lines(text))

    years, req_years = resume_years(text), jd["required_years"]
    exp_score = min(100.0, years / req_years * 100) if req_years else None

    levels = education_levels(text)
    cand_lvl, req_lvl = max(levels, default=0), jd["required_education_level"]
    edu_score = (100.0 if cand_lvl >= req_lvl else cand_lvl / req_lvl * 100) if req_lvl else None

    parts = {"skills": skill_score, "semantic": sem, "experience": exp_score, "education": edu_score}
    active = {k: v for k, v in parts.items() if v is not None}
    total_w = sum(WEIGHTS[k] for k in active)
    total = round(sum(v * WEIGHTS[k] for k, v in active.items()) / total_w, 1)

    # ---- human-readable reasons
    reasons = []
    if jd_skills:
        reasons.append(f"Skills: {len(matched)} of {len(jd_skills)} JD skills found directly"
                       + (f", plus {len(related)} covered by a related skill (half credit)" if related else "")
                       + f" → {skill_score:.0f}% (nice-to-have skills count half).")
    if req_years:
        verdict = "meets" if years >= req_years else "is below"
        reasons.append(f"Experience: {years:g} years {verdict} the {req_years:g} years required → {exp_score:.0f}%.")
    else:
        reasons.append(f"Experience: {years:g} years detected (JD gives no minimum, so not scored).")
    if req_lvl:
        reasons.append(f"Education: {LEVEL_NAME.get(cand_lvl, 'not detected')} vs required "
                       f"{LEVEL_NAME[req_lvl]} → {edu_score:.0f}%.")
    ranked = sorted(evidence, key=lambda e: -e[2])
    if ranked:
        top = ranked[0]
        reasons.append(f"Semantic fit {sem:.0f}%. Best-supported requirement: “{top[0][:80]}”.")
        weak = [e for e in ranked if e[2] < (0.25 if _get_model() else 0.08)]
        if weak:
            reasons.append(f"Weakest evidence for: “{weak[-1][0][:80]}”.")
    for r in related:
        reasons.append(f"Missing '{r['skill']}' but has related: {', '.join(r['has'])}.")
    if missing:
        reasons.append("Not found: " + ", ".join(missing) + ".")

    label = "Strong match" if total >= 75 else "Moderate match" if total >= 55 else "Weak match"
    return {
        "score": total, "label": label,
        "matched_skills": matched, "related_skills": related, "missing_skills": missing,
        "experience_years": years, "required_experience": req_years,
        "education": LEVEL_NAME.get(cand_lvl), "required_education": jd["required_education"],
        "components": {k: (round(v, 1) if v is not None else None) for k, v in parts.items()},
        "weights": WEIGHTS, "semantic_backend": semantic_backend(),
        "evidence": [{"requirement": a, "resume_line": b, "similarity": round(c, 2)} for a, b, c in ranked[:3]],
        "reasons": reasons,
        "extra_skills": sorted(r_skills - set(jd_skills)),
    }
