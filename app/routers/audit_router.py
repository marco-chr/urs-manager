from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _user(request, db):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@router.get("/systems/{system_id}/audit", response_class=HTMLResponse)
def audit_log(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    entries = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.system_id == system_id)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(500)
        .all()
    )
    return templates.TemplateResponse("audit_log.html", {
        "request": request,
        "user": user,
        "system": system,
        "entries": entries,
    })


@router.get("/audit", response_class=HTMLResponse)
def audit_log_global(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login", status_code=302)
    if user.role != "admin":
        raise HTTPException(403)
    entries = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(1000)
        .all()
    )
    return templates.TemplateResponse("audit_log.html", {
        "request": request,
        "user": user,
        "system": None,
        "entries": entries,
    })
