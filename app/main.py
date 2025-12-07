from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .db import Document, Share, get_session, init_db

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Secure PDF Reader")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class UploadResponse(BaseModel):
    document_id: int
    title: str
    filename: str


class ShareRequest(BaseModel):
    document_id: int
    mode: str  # preview | browse
    allowed_pages: Optional[int] = None
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    watermark_text: Optional[str] = None


class ShareResponse(BaseModel):
    token: str
    mode: str
    url: str
    verification_code: Optional[str] = None


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def admin_home(request: Request):
    with get_session() as session:
        documents = session.query(Document).order_by(Document.created_at.desc()).all()
        shares = session.query(Share).order_by(Share.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "documents": documents, "shares": shares},
    )


@app.post("/api/admin/upload", response_model=UploadResponse)
def upload_pdf(
    title: str = Form(...),
    uploaded_by: str = Form(...),
    file: UploadFile = File(...),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are allowed")

    token = secrets.token_hex(8)
    filename = f"{token}_{file.filename}"
    destination = UPLOAD_DIR / filename
    with destination.open("wb") as f:
        content = file.file.read()
        f.write(content)

    with get_session() as session:
        doc = Document(title=title, filename=filename, uploaded_by=uploaded_by)
        session.add(doc)
        session.commit()
        session.refresh(doc)

    return UploadResponse(document_id=doc.id, title=doc.title, filename=doc.filename)


@app.post("/api/admin/share", response_model=ShareResponse)
def create_share(payload: ShareRequest):
    if payload.mode not in {"preview", "browse"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    token = secrets.token_urlsafe(12)
    verification_code: Optional[str] = None
    if payload.mode == "browse":
        verification_code = secrets.token_hex(3)

    with get_session() as session:
        doc = session.get(Document, payload.document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        share = Share(
            document_id=doc.id,
            mode=payload.mode,
            allowed_pages=payload.allowed_pages,
            recipient_email=payload.recipient_email,
            recipient_name=payload.recipient_name,
            verification_code=verification_code,
            token=token,
            watermark_text=payload.watermark_text,
        )
        session.add(share)
        session.commit()

    url = f"/share/{token}"
    return ShareResponse(token=token, mode=payload.mode, url=url, verification_code=verification_code)


@app.get("/share/{token}", response_class=HTMLResponse)
def share_entry(token: str, request: Request):
    with get_session() as session:
        share = session.query(Share).filter_by(token=token).first()
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        document = session.get(Document, share.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document missing")

    if share.mode == "preview":
        return templates.TemplateResponse(
            "viewer.html",
            {
                "request": request,
                "token": token,
                "mode": share.mode,
                "title": document.title,
                "allowed_pages": share.allowed_pages,
                "watermark": share.watermark_text or "Preview only",
                "recipient_name": share.recipient_name or "Guest",
            },
        )

    # browse mode requires verification
    if not share.verified:
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "token": token,
                "recipient_email": share.recipient_email,
            },
        )

    return templates.TemplateResponse(
        "viewer.html",
        {
            "request": request,
            "token": token,
            "mode": share.mode,
            "title": document.title,
            "allowed_pages": None,
            "watermark": share.watermark_text or share.recipient_name or "Protected",
            "recipient_name": share.recipient_name or "Verified user",
        },
    )


class VerifyRequest(BaseModel):
    code: str
    name: Optional[str] = None
    email: Optional[str] = None


@app.post("/api/share/{token}/verify")
def verify_share(token: str, payload: VerifyRequest):
    with get_session() as session:
        share = session.query(Share).filter_by(token=token).first()
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        if share.mode != "browse":
            raise HTTPException(status_code=400, detail="Verification not required")
        if share.verification_code != payload.code:
            raise HTTPException(status_code=400, detail="Invalid verification code")

        share.verified = True
        if payload.name:
            share.recipient_name = payload.name
        if payload.email:
            share.recipient_email = payload.email
        session.commit()
    return {"status": "verified"}


@app.get("/api/share/{token}/meta")
def share_meta(token: str):
    with get_session() as session:
        share = session.query(Share).filter_by(token=token).first()
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        document = session.get(Document, share.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document missing")
    return {
        "mode": share.mode,
        "allowed_pages": share.allowed_pages,
        "watermark": share.watermark_text,
        "recipient_name": share.recipient_name,
        "title": document.title,
        "file": document.filename,
    }


@app.get("/api/share/{token}/file")
def download_pdf(token: str):
    with get_session() as session:
        share = session.query(Share).filter_by(token=token).first()
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        if share.mode == "browse" and not share.verified:
            raise HTTPException(status_code=403, detail="Verification required")
        document = session.get(Document, share.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document missing")

    file_path = UPLOAD_DIR / document.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="application/pdf", filename=document.filename)


@app.get("/health")
def health_check():
    return {"status": "ok"}
