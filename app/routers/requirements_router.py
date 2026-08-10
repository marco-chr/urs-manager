from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, audit
from app.auth import get_current_user, can_edit_system
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api")

REQ_TYPES = ["functional", "non_functional", "regulatory", "interface", "environmental", "ehs"]


class RequirementIn(BaseModel):
    section_id: Optional[int] = None
    req_id: Optional[str] = ""
    req_type: str = "functional"
    description: str
    must_have: bool = True
    gmp_flag: str = "GEP"  # "GMP" or "GEP"
    note: Optional[str] = ""


class FindReplaceIn(BaseModel):
    find: str
    replace: str
    fields: list[str] = ["description", "note"]
    section_id: Optional[int] = None


def _user(request, db):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@router.get("/systems/{system_id}/requirements")
def list_requirements(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    reqs = (
        db.query(models.Requirement)
        .filter(models.Requirement.system_id == system_id)
        .order_by(models.Requirement.section_id, models.Requirement.req_id)
        .all()
    )
    return [_serialize(r, db) for r in reqs]


@router.post("/systems/{system_id}/requirements")
def create_requirement(request: Request, system_id: int, body: RequirementIn, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    if not can_edit_system(user, system_id, db):
        raise HTTPException(403)
    req = models.Requirement(
        system_id=system_id,
        section_id=body.section_id or None,
        req_id=body.req_id,
        req_type=body.req_type,
        description=body.description,
        must_have=body.must_have,
        gmp_flag=body.gmp_flag,
        note=body.note,
        created_by=user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    audit.log(db, user, "requirements", req.id, "CREATE", new_value=audit.serialize_requirement(req), system_id=system_id)
    return _serialize(req, db)


@router.put("/requirements/{req_id}")
def update_requirement(request: Request, req_id: int, body: RequirementIn, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    req = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404)
    if not can_edit_system(user, req.system_id, db):
        raise HTTPException(403)
    old = audit.serialize_requirement(req)
    req.section_id = body.section_id or None
    req.req_id = body.req_id
    req.req_type = body.req_type
    req.description = body.description
    req.must_have = body.must_have
    req.gmp_flag = body.gmp_flag
    req.note = body.note
    req.updated_at = datetime.utcnow()
    db.commit()
    audit.log(db, user, "requirements", req.id, "UPDATE", old_value=old, new_value=audit.serialize_requirement(req), system_id=req.system_id)
    return _serialize(req, db)


@router.delete("/requirements/{req_id}")
def delete_requirement(request: Request, req_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    req = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404)
    if not can_edit_system(user, req.system_id, db):
        raise HTTPException(403)
    old = audit.serialize_requirement(req)
    system_id = req.system_id
    db.delete(req)
    db.commit()
    audit.log(db, user, "requirements", req_id, "DELETE", old_value=old, system_id=system_id)
    return {"ok": True}


@router.post("/systems/{system_id}/requirements/find-replace")
def find_replace(request: Request, system_id: int, body: FindReplaceIn, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    if not can_edit_system(user, system_id, db):
        raise HTTPException(403)
    query = db.query(models.Requirement).filter(models.Requirement.system_id == system_id)
    if body.section_id:
        query = query.filter(models.Requirement.section_id == body.section_id)
    reqs = query.all()
    count = 0
    for req in reqs:
        changed = False
        old = audit.serialize_requirement(req)
        if "description" in body.fields and req.description and body.find in req.description:
            req.description = req.description.replace(body.find, body.replace)
            changed = True
        if "note" in body.fields and req.note and body.find in req.note:
            req.note = req.note.replace(body.find, body.replace)
            changed = True
        if changed:
            req.updated_at = datetime.utcnow()
            db.flush()
            audit.log(db, user, "requirements", req.id, "UPDATE", old_value=old, new_value=audit.serialize_requirement(req), system_id=system_id)
            count += 1
    db.commit()
    return {"replaced": count}


def _serialize(req: models.Requirement, db: Session) -> dict:
    section_name = ""
    if req.section_id:
        sec = db.query(models.Section).filter(models.Section.id == req.section_id).first()
        section_name = sec.name if sec else ""
    return {
        "id": req.id,
        "section_id": req.section_id,
        "section_name": section_name,
        "req_id": req.req_id or "",
        "req_type": req.req_type or "functional",
        "description": req.description,
        "must_have": req.must_have,
        "gmp_flag": req.gmp_flag,
        "note": req.note or "",
        "created_at": req.created_at.isoformat() if req.created_at else "",
        "updated_at": req.updated_at.isoformat() if req.updated_at else "",
    }
