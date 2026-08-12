from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, audit
from app.auth import get_current_user, verify_password, is_system_owner
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EDITABLE_STATUSES = {"draft"}
SIGN_STATUS_ROLE = {"review": "reviewer", "in_approval": "approver"}


def _user(request, db):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


def _status_label(status: str) -> str:
    return {
        "draft": "Draft", "review": "In Review", "reviewed": "Reviewed",
        "in_approval": "In Approval", "approved": "Approved",
    }.get(status, status.title())


# ── Pages ──────────────────────────────────────────────────────────────────────

@router.get("/systems/{system_id}/review", response_class=HTMLResponse)
def review_page(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)

    reviewers = (
        db.query(models.SystemSignatory)
        .filter(models.SystemSignatory.system_id == system_id, models.SystemSignatory.role == "reviewer")
        .order_by(models.SystemSignatory.order)
        .all()
    )
    approvers = (
        db.query(models.SystemSignatory)
        .filter(models.SystemSignatory.system_id == system_id, models.SystemSignatory.role == "approver")
        .order_by(models.SystemSignatory.order)
        .all()
    )
    history = (
        db.query(models.SystemHistory)
        .filter(models.SystemHistory.system_id == system_id)
        .order_by(models.SystemHistory.id.desc())
        .all()
    )
    available_users = (
        db.query(models.User)
        .filter(models.User.is_active == True)
        .order_by(models.User.username)
        .all()
    )

    reviewer_ids = {s.user_id for s in reviewers}
    approver_ids = {s.user_id for s in approvers}

    # Which pending signature (if any) can the current user sign right now?
    pending_sig = None
    expected_role = SIGN_STATUS_ROLE.get(system.status)
    if expected_role:
        for sig in (reviewers if expected_role == "reviewer" else approvers):
            if sig.user_id == user.id and not sig.signed:
                pending_sig = sig
                break

    can_add_signatories = is_system_owner(user, system) and system.status == "draft"
    can_submit_review = (
        is_system_owner(user, system) and system.status == "draft" and len(reviewers) > 0
    )
    can_submit_approval = (
        is_system_owner(user, system) and system.status == "reviewed" and len(approvers) > 0
    )
    can_reopen = is_system_owner(user, system) and system.status not in ("draft",)

    return templates.TemplateResponse("review_approval.html", {
        "request": request,
        "user": user,
        "system": system,
        "reviewers": reviewers,
        "approvers": approvers,
        "history": history,
        "available_users": available_users,
        "reviewer_ids": reviewer_ids,
        "approver_ids": approver_ids,
        "pending_sig": pending_sig,
        "is_owner": is_system_owner(user, system),
        "can_add_signatories": can_add_signatories,
        "can_submit_review": can_submit_review,
        "can_submit_approval": can_submit_approval,
        "can_reopen": can_reopen,
        "status_label": _status_label(system.status),
    })


@router.get("/my-signatures", response_class=HTMLResponse)
def my_signatures(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    pending = (
        db.query(models.SystemSignatory)
        .filter(
            models.SystemSignatory.user_id == user.id,
            models.SystemSignatory.signed == False,
        )
        .all()
    )
    system_ids = list({s.system_id for s in pending})
    systems = {}
    if system_ids:
        for sys in db.query(models.System).filter(models.System.id.in_(system_ids)).all():
            systems[sys.id] = sys

    # Filter to only pending entries where the system is currently awaiting that role's signature
    actionable = [
        s for s in pending
        if systems.get(s.system_id) and
        SIGN_STATUS_ROLE.get(systems[s.system_id].status) == s.role
    ]

    return templates.TemplateResponse("my_signatures.html", {
        "request": request,
        "user": user,
        "actionable": actionable,
        "systems": systems,
    })


# ── API endpoints ──────────────────────────────────────────────────────────────

class SignatoryIn(BaseModel):
    user_id: int
    role: str
    function_text: Optional[str] = ""


@router.post("/api/systems/{system_id}/signatories")
def add_signatory(
    request: Request, system_id: int, body: SignatoryIn,
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if not is_system_owner(user, system):
        raise HTTPException(403)
    if system.status != "draft":
        raise HTTPException(400, detail="Signatories can only be modified in draft status")
    if body.role not in ("reviewer", "approver"):
        raise HTTPException(400, detail="Role must be 'reviewer' or 'approver'")

    existing = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system_id,
        models.SystemSignatory.user_id == body.user_id,
        models.SystemSignatory.role == body.role,
    ).first()
    if existing:
        raise HTTPException(400, detail="User already added in this role")

    count = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system_id,
        models.SystemSignatory.role == body.role,
    ).count()

    target_user = db.query(models.User).filter(models.User.id == body.user_id).first()
    if not target_user:
        raise HTTPException(404, detail="User not found")

    sig = models.SystemSignatory(
        system_id=system_id,
        user_id=body.user_id,
        role=body.role,
        function_text=body.function_text or "",
        order=count,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return {
        "id": sig.id,
        "user_id": sig.user_id,
        "username": target_user.username,
        "full_name": target_user.full_name or "",
        "role": sig.role,
        "function_text": sig.function_text,
        "signed": False,
    }


@router.delete("/api/systems/{system_id}/signatories/{sig_id}")
def remove_signatory(
    request: Request, system_id: int, sig_id: int,
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if not is_system_owner(user, system):
        raise HTTPException(403)
    if system.status != "draft":
        raise HTTPException(400, detail="Signatories can only be modified in draft status")
    sig = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.id == sig_id,
        models.SystemSignatory.system_id == system_id,
    ).first()
    if not sig:
        raise HTTPException(404)
    db.delete(sig)
    db.commit()
    return {"ok": True}


@router.post("/systems/{system_id}/submit-review")
def submit_review(
    request: Request, system_id: int,
    modification_note: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system or not is_system_owner(user, system):
        raise HTTPException(403)
    if system.status != "draft":
        raise HTTPException(400, detail="System must be in draft to submit for review")
    reviewer_count = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system_id,
        models.SystemSignatory.role == "reviewer",
    ).count()
    if reviewer_count == 0:
        raise HTTPException(400, detail="Add at least one reviewer before submitting")

    system.status = "review"
    if modification_note.strip():
        system.modification_note = modification_note.strip()
    db.commit()
    audit.log(db, user, "systems", system_id, "SUBMIT_REVIEW",
              new_value={"status": "review"}, system_id=system_id)
    return RedirectResponse(f"/systems/{system_id}/review", status_code=302)


@router.post("/systems/{system_id}/submit-approval")
def submit_approval(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system or not is_system_owner(user, system):
        raise HTTPException(403)
    if system.status != "reviewed":
        raise HTTPException(400, detail="System must be reviewed before submitting for approval")
    approver_count = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system_id,
        models.SystemSignatory.role == "approver",
    ).count()
    if approver_count == 0:
        raise HTTPException(400, detail="Add at least one approver before submitting")

    system.status = "in_approval"
    db.commit()
    audit.log(db, user, "systems", system_id, "SUBMIT_APPROVAL",
              new_value={"status": "in_approval"}, system_id=system_id)
    return RedirectResponse(f"/systems/{system_id}/review", status_code=302)


@router.post("/systems/{system_id}/reopen")
def reopen_system(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system or not is_system_owner(user, system):
        raise HTTPException(403)

    old_status = system.status
    system.status = "draft"
    # Reset all signatures so signatories can re-sign in the next cycle
    db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system_id,
    ).update({"signed": False, "signed_at": None})
    db.commit()
    audit.log(db, user, "systems", system_id, "REOPEN",
              old_value={"status": old_status}, new_value={"status": "draft"},
              system_id=system_id)
    return RedirectResponse(f"/systems/{system_id}/review", status_code=302)



class SignIn(BaseModel):
    password: str


@router.post("/api/systems/{system_id}/sign")
def sign_document(
    request: Request, system_id: int, body: SignIn,
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, detail="Incorrect password")

    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if system.status not in ("review", "in_approval"):
        raise HTTPException(400, detail="Document is not currently under review or approval")

    expected_role = SIGN_STATUS_ROLE[system.status]

    sig = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system_id,
        models.SystemSignatory.user_id == user.id,
        models.SystemSignatory.role == expected_role,
        models.SystemSignatory.signed == False,
    ).first()
    if not sig:
        raise HTTPException(400, detail="No pending signature found for your user in the current phase")

    sig.signed = True
    sig.signed_at = datetime.utcnow()
    db.commit()

    audit.log(db, user, "system_signatories", sig.id, "SIGN",
              new_value={"role": sig.role, "signed_at": sig.signed_at.isoformat()},
              system_id=system_id)

    _check_and_advance_status(db, system, expected_role, user)

    return {"ok": True, "role": expected_role}


def _check_and_advance_status(db, system, role: str, user):
    all_sigs = db.query(models.SystemSignatory).filter(
        models.SystemSignatory.system_id == system.id,
        models.SystemSignatory.role == role,
    ).all()

    if not all_sigs or not all(s.signed for s in all_sigs):
        return

    if role == "reviewer":
        system.status = "reviewed"
        db.commit()
        audit.log(db, user, "systems", system.id, "STATUS_CHANGE",
                  old_value={"status": "review"},
                  new_value={"status": "reviewed"},
                  system_id=system.id)

    elif role == "approver":
        major = system.major_version or 0
        minor = system.minor_version or 0
        history_entry = models.SystemHistory(
            system_id=system.id,
            version=f"{major}.{minor}",
            major_version=major,
            minor_version=minor,
            modification_text=system.modification_note or "",
            version_date=datetime.utcnow(),
            created_by=user.id,
        )
        db.add(history_entry)
        system.major_version = major + 1
        system.minor_version = 0
        system.modification_note = None
        system.status = "approved"
        db.commit()
        audit.log(db, user, "systems", system.id, "APPROVED",
                  old_value={"version": f"{major}.{minor}"},
                  new_value={"version": f"{major + 1}.0", "status": "approved"},
                  system_id=system.id)
