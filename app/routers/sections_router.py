from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, audit
from app.auth import get_current_user, can_edit_system
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class SectionIn(BaseModel):
    name: str
    order: int = 0


def _user(request, db):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@router.get("/systems/{system_id}/sections")
def list_sections(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    sections = db.query(models.Section).filter(models.Section.system_id == system_id).order_by(models.Section.order).all()
    return [{"id": s.id, "name": s.name, "order": s.order} for s in sections]


@router.post("/systems/{system_id}/sections")
def create_section(request: Request, system_id: int, body: SectionIn, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    if not can_edit_system(user, system_id, db):
        raise HTTPException(403)
    section = models.Section(system_id=system_id, name=body.name, order=body.order)
    db.add(section)
    db.commit()
    db.refresh(section)
    audit.log(db, user, "sections", section.id, "CREATE", new_value=audit.serialize_section(section), system_id=system_id)
    return {"id": section.id, "name": section.name, "order": section.order}


@router.put("/sections/{section_id}")
def update_section(request: Request, section_id: int, body: SectionIn, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not section:
        raise HTTPException(404)
    if not can_edit_system(user, section.system_id, db):
        raise HTTPException(403)
    old = audit.serialize_section(section)
    section.name = body.name
    section.order = body.order
    db.commit()
    audit.log(db, user, "sections", section.id, "UPDATE", old_value=old, new_value=audit.serialize_section(section), system_id=section.system_id)
    return {"id": section.id, "name": section.name, "order": section.order}


@router.delete("/sections/{section_id}")
def delete_section(request: Request, section_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        raise HTTPException(401)
    section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not section:
        raise HTTPException(404)
    if not can_edit_system(user, section.system_id, db):
        raise HTTPException(403)
    old = audit.serialize_section(section)
    system_id = section.system_id
    db.query(models.Requirement).filter(models.Requirement.section_id == section_id).update({"section_id": None})
    db.delete(section)
    db.commit()
    audit.log(db, user, "sections", section_id, "DELETE", old_value=old, system_id=system_id)
    return {"ok": True}
