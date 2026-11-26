"""FastAPI app: upload books, review issues, approve fixes, chat with the assistant."""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm, store
from .checks import run_all, summarize
from .fixes import FixError, apply_fix, export_csv, now_iso
from .importers import ImportError_, load_csvs

BASE = Path(__file__).parent
SAMPLE_DIR = BASE.parent / "sample_data"
MAX_UPLOAD = 5 * 1024 * 1024

app = FastAPI(title="Ledger Checkup")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
store.init()


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Password-protect everything except /health when APP_PASSWORD is set."""
    password = os.environ.get("APP_PASSWORD")
    if password and request.url.path != "/health":
        header = request.headers.get("authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(given, password)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Ledger Checkup"'})
    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(BASE / "templates" / "index.html")


def _scan_or_404(scan_id: str) -> store.Scan:
    scan = store.get(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


def _payload(scan: store.Scan) -> dict:
    return {"id": scan.id, "name": scan.name, "created_at": scan.created_at,
            "summary": summarize(scan.dataset, scan.issues),
            "issues": [i.to_dict() for i in scan.issues], "audit": scan.audit, "chat": scan.chat,
            "llm": {"configured": llm.is_configured(), "model": llm.config()["model"]}}


@app.get("/api/scans")
def list_scans():
    return store.list_scans()


async def _read(f: UploadFile | None) -> str | None:
    if f is None or not f.filename:
        return None
    data = await f.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"{f.filename} is larger than 5 MB")
    return data.decode("utf-8-sig", errors="replace")


@app.post("/api/scans")
async def create_scan(name: str = Form("My business"), bank: UploadFile | None = File(None),
                      ledger: UploadFile | None = File(None), invoices: UploadFile | None = File(None)):
    try:
        ds = load_csvs(await _read(bank), await _read(ledger), await _read(invoices))
    except ImportError_ as e:
        raise HTTPException(400, str(e))
    scan = store.create(name.strip() or "My business", now_iso(), ds, run_all(ds))
    return _payload(scan)


@app.post("/api/scans/sample")
def create_sample_scan():
    read = lambda n: (SAMPLE_DIR / n).read_text()
    ds = load_csvs(read("bank.csv"), read("ledger.csv"), read("invoices.csv"))
    scan = store.create("Sample: Bright Bean Coffee Co.", now_iso(), ds, run_all(ds))
    return _payload(scan)


@app.get("/api/scans/{scan_id}")
def get_scan(scan_id: str):
    return _payload(_scan_or_404(scan_id))


@app.delete("/api/scans/{scan_id}")
def delete_scan(scan_id: str):
    store.delete(scan_id)
    return {"ok": True}


class Decision(BaseModel):
    decision: Literal["approve", "reject"]


@app.post("/api/scans/{scan_id}/issues/{issue_id}/decision")
def decide(scan_id: str, issue_id: str, body: Decision):
    scan = _scan_or_404(scan_id)
    issue = scan.issue(issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")
    if issue.status != "open":
        raise HTTPException(409, f"Issue already {issue.status}")
    if body.decision == "approve":
        try:
            note = apply_fix(scan.dataset, issue)
        except FixError as e:
            raise HTTPException(409, str(e))
        issue.status = "approved"
    else:
        note = f"Rejected proposed fix: {issue.fix.summary}"
        issue.status = "rejected"
    scan.audit.append({"time": now_iso(), "issue_id": issue.id, "decision": body.decision, "note": note})
    store.save(scan)
    return _payload(scan)


@app.post("/api/scans/{scan_id}/rescan")
def rescan(scan_id: str):
    """Re-run the checks on the corrected data. Previously rejected issues stay rejected."""
    scan = _scan_or_404(scan_id)
    rejected = {(i.check, tuple(i.records)) for i in scan.issues if i.status == "rejected"}
    scan.issues = run_all(scan.dataset)
    for i in scan.issues:
        if (i.check, tuple(i.records)) in rejected:
            i.status = "rejected"
    scan.audit.append({"time": now_iso(), "issue_id": "", "decision": "rescan",
                       "note": f"Re-ran checks: {sum(i.status == 'open' for i in scan.issues)} open issues"})
    store.save(scan)
    return _payload(scan)


@app.get("/api/scans/{scan_id}/export/{kind}")
def export(scan_id: str, kind: Literal["bank", "ledger", "invoices", "audit"]):
    scan = _scan_or_404(scan_id)
    return PlainTextResponse(export_csv(scan.dataset, kind, scan.audit), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{kind}-corrected.csv"'})


class ChatIn(BaseModel):
    message: str


@app.post("/api/scans/{scan_id}/chat")
async def chat(scan_id: str, body: ChatIn):
    scan = _scan_or_404(scan_id)
    message = body.message.strip()[:2000]
    if not message:
        raise HTTPException(400, "Empty message")
    answer = await llm.chat(message, scan.chat, summarize(scan.dataset, scan.issues), scan.issues)
    scan.chat += [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
    scan.chat = scan.chat[-40:]
    store.save(scan)
    return JSONResponse({"answer": answer, "chat": scan.chat})
