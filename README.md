# AI Resume Matcher

Compares a batch of resumes (PDF/DOCX) against a Job Description, scores each 0–100, ranks them, and explains every score.
**Stack:** Python · FastAPI · MongoDB (optional) · PyMuPDF / python-docx · Sentence Transformers (`all-MiniLM-L6-v2`) · scikit-learn · plain HTML/JS UI.

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload                      # run from the project root
```

Open http://127.0.0.1:8000 → click **Load sample JD** → **Analyze** → select all files in `samples/resumes/` (10 synthetic resumes, 5 PDF + 5 DOCX) → **Match resumes** → click a candidate.

- **MongoDB is optional.** If `MONGO_URI` (default `mongodb://localhost:27017`) is not reachable, the app falls back to in-memory storage and says so in the console.
- First start downloads the ~90 MB MiniLM model. If it cannot be downloaded, TF-IDF similarity is used instead (shown in the UI).
- API docs: `/docs`. Tests: `pip install pytest && pytest tests`. Regenerate samples: `pip install reportlab && python samples/make_samples.py`.

## Architecture

```
frontend/index.html ──HTTP──► backend/main.py (FastAPI routes + storage: MongoDB | memory)
                                   │
                                   └──► backend/matcher.py  (parsing + scoring; no web/DB code)
```

| Module | Where |
|---|---|
| 1. JD input (paste/upload, extract skills, years, education, key requirements) | `POST /api/jobs`, `analyze_jd()` |
| 2. Batch resume upload + extraction (name, email, phone, skills, experience, education) | `POST /api/jobs/{id}/resumes`, `extract_text()` |
| 3. Matching (score, matched/missing skills, experience, semantic) | `score_resume()` |
| 4. Ranking table | `GET /api/jobs/{id}/ranking` |
| 5. Candidate analysis | `GET /api/candidates/{id}` |

## Matching algorithm

`Match % = Σ(weight × component) / Σ(weights of components that apply)`

| Component | Weight | How it is computed |
|---|---|---|
| **Skills** | 50% | Skills are detected with an editable dictionary incl. aliases (`k8s`→Kubernetes, `postgres`→PostgreSQL). Exact match = full credit; a **related** skill (e.g. JD wants PostgreSQL, resume has MySQL) = **half credit**. Skills in "nice to have / preferred" lines count half as much as required ones. |
| **Semantic similarity** | 25% | The JD and resume are split into lines. Each JD requirement is embedded and compared (cosine) to every resume line; the **best match per requirement** is rescaled (0.15→0%, 0.60→100%) and averaged. This catches meaning that has no shared keyword (e.g. "deployed services to cloud" vs "ran workloads on AWS"). |
| **Experience** | 15% | `min(1, candidate_years / required_years)`. Candidate years = max(stated "N years of experience", **sum of job date ranges** with overlaps merged and study periods ignored). |
| **Education** | 10% | Highest level found (Diploma < Bachelor's < Master's < PhD) vs. the JD minimum; full credit if met, proportional otherwise. |

If the JD does not state experience or education, that component is dropped and the remaining weights are re-normalised, so a candidate is never penalised for something the JD didn't ask for. ≥75 = strong, ≥55 = moderate, otherwise weak.

Every candidate's detail view shows each component, matched / related / missing skills, experience & education vs. the JD, plain-English reasons, and the resume lines that best support the top JD requirements.

## Limitations (honest list)

- Skills come from a dictionary (~40 skills); anything outside it is only covered by the semantic component. Extend `SKILLS` / `_PAIRS` in `matcher.py`.
- Experience is **total** working time, not time spent in *relevant* roles.
- Name/education detection is heuristic; scanned PDFs (no text layer) need OCR and are rejected with a clear message.
- Score weights and the semantic rescaling range are hand-tuned, not learned from labelled data.
- Decision-support only — not an automated hiring decision. Use synthetic or licensed resumes only.
