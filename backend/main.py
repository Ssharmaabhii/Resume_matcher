import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import matcher as m

app = FastAPI(title="AI Resume Matcher")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- storage ----
class Store:
    """MongoDB if reachable, otherwise a plain in-memory dict (handy for demos/tests)."""

    def __init__(self):
        self.jobs, self.cands, self.mongo = {}, {}, None
        try:
            from pymongo import MongoClient
            client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            self.mongo = client["resume_matcher"]
        except Exception:
            print("MongoDB not reachable -> using in-memory storage (data is lost on restart).")

    def save_job(self, doc):
        doc["_id"] = uuid4().hex
        if self.mongo is not None:
            self.mongo["jobs"].insert_one(doc)
        else:
            self.jobs[doc["_id"]] = doc
        return doc["_id"]

    def get_job(self, job_id):
        if self.mongo is not None:
            return self.mongo["jobs"].find_one({"_id": job_id})
        return self.jobs.get(job_id)

    def save_candidate(self, doc):
        doc["_id"] = uuid4().hex
        if self.mongo is not None:
            self.mongo["candidates"].insert_one(doc)
        else:
            self.cands[doc["_id"]] = doc
        return doc["_id"]

    def candidates(self, job_id):
        if self.mongo is not None:
            rows = list(self.mongo["candidates"].find({"job_id": job_id}))
        else:
            rows = [c for c in self.cands.values() if c["job_id"] == job_id]
        return sorted(rows, key=lambda c: -c["match"]["score"])

    def get_candidate(self, cid):
        if self.mongo is not None:
            return self.mongo["candidates"].find_one({"_id": cid})
        return self.cands.get(cid)

    def clear(self, job_id):
        if self.mongo is not None:
            return self.mongo["candidates"].delete_many({"job_id": job_id}).deleted_count
        ids = [k for k, c in self.cands.items() if c["job_id"] == job_id]
        for k in ids:
            del self.cands[k]
        return len(ids)


store = Store()


@app.on_event("startup")
def warm_up():
    print("Semantic backend:", m.semantic_backend())  # loads the model once, up front


def row(c):
    mt = c["match"]
    return {"id": c["_id"], "name": c["name"], "experience": mt["experience_years"], "score": mt["score"],
            "label": mt["label"], "matched_skills": mt["matched_skills"], "filename": c["filename"]}


# -------------------------------------------------------------------- API ----
@app.post("/api/jobs")
async def create_job(text: str = Form(""), file: UploadFile | None = File(None)):
    """Module 1: JD from pasted text OR an uploaded PDF/DOCX/TXT."""
    try:
        if file is not None and file.filename:
            text = m.extract_text(file.filename, await file.read())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if len(text.strip()) < 30:
        raise HTTPException(400, "Please paste or upload a longer job description.")
    jd = m.analyze_jd(text)
    job_id = store.save_job({"text": text, "jd": jd, "created_at": datetime.now(timezone.utc)})
    return {"job_id": job_id, "skills": jd["skills"], "optional_skills": jd["optional_skills"], "required_years": jd["required_years"],
            "required_education": jd["required_education"], "requirements": jd["requirements"],
            "semantic_backend": m.semantic_backend()}


@app.post("/api/jobs/{job_id}/resumes")
async def upload_resumes(job_id: str, files: list[UploadFile] = File(...)):
    """Modules 2-4: parse + score every resume in the batch, return the ranking."""
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job description not found.")
    added, errors = 0, []
    for f in files:
        try:
            text = m.extract_text(f.filename, await f.read())
            store.save_candidate({
                "job_id": job_id, "filename": f.filename,
                "name": m.candidate_name(text, f.filename),
                "email": m.candidate_email(text), "phone": m.candidate_phone(text),
                "skills": m.find_skills(text), "match": m.score_resume(job["jd"], text),
                "created_at": datetime.now(timezone.utc),
            })
            added += 1
        except Exception as exc:
            errors.append({"filename": f.filename, "error": str(exc)})
    return {"added": added, "errors": errors, "ranking": [row(c) for c in store.candidates(job_id)]}


@app.get("/api/jobs/{job_id}/ranking")
def get_ranking(job_id: str):
    return [row(c) for c in store.candidates(job_id)]


@app.get("/api/candidates/{candidate_id}")
def candidate_detail(candidate_id: str):
    c = store.get_candidate(candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found.")
    c = {k: v for k, v in c.items() if k != "created_at"}
    c["id"] = c.pop("_id")
    return c


@app.delete("/api/jobs/{job_id}/candidates")
def clear_candidates(job_id: str):
    return {"deleted": store.clear(job_id)}


@app.get("/api/health")
def health():
    return {"status": "ok", "storage": "mongodb" if store.mongo is not None else "memory"}


# Serve the web UI at http://127.0.0.1:8000
app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parents[1] / "frontend"), html=True), name="frontend")
