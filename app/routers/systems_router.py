from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, audit
from app.auth import get_current_user, is_system_owner, can_edit_system
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _current_user(request: Request, db: Session):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    systems = db.query(models.System).order_by(models.System.updated_at.desc()).all()
    templates_list = db.query(models.Template).order_by(models.Template.name).all()
    editable_ids = {s.id for s in systems if can_edit_system(user, s.id, db)}
    owner_ids = {s.id for s in systems if is_system_owner(user, s)}
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "systems": systems,
        "templates_list": templates_list,
        "editable_ids": editable_ids,
        "owner_ids": owner_ids,
    })


@router.post("/systems/create")
def create_system(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    company_name: str = Form(""),
    plant: str = Form(""),
    address: str = Form(""),
    country: str = Form(""),
    building: str = Form(""),
    template_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    system = models.System(
        name=name, description=description,
        company_name=company_name or None, plant=plant or None,
        address=address or None, country=country or None, building=building or None,
        created_by=user.id,
    )
    db.add(system)
    db.flush()

    if template_id:
        tpl = db.query(models.Template).filter(models.Template.id == int(template_id)).first()
        if tpl:
            section_map = {}
            for ts in tpl.sections:
                sec = models.Section(system_id=system.id, name=ts.name, order=ts.order)
                db.add(sec)
                db.flush()
                section_map[ts.name] = sec.id
            for tr in tpl.requirements:
                sec_id = section_map.get(tr.section_name)
                req = models.Requirement(
                    system_id=system.id,
                    section_id=sec_id,
                    req_id=tr.req_id,
                    req_type=tr.req_type,
                    description=tr.description,
                    must_have=tr.must_have,
                    gmp_flag=tr.gmp_flag,
                    note=tr.note,
                    created_by=user.id,
                )
                db.add(req)

    db.commit()
    audit.log(db, user, "systems", system.id, "CREATE", new_value=audit.serialize_system(system), system_id=system.id)
    return RedirectResponse(f"/systems/{system.id}", status_code=302)


@router.post("/systems/{system_id}/update")
def update_system(
    request: Request,
    system_id: int,
    name: str = Form(...),
    description: str = Form(""),
    company_name: str = Form(""),
    plant: str = Form(""),
    address: str = Form(""),
    country: str = Form(""),
    building: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if not is_system_owner(user, system):
        raise HTTPException(403, "Only the system owner can change settings")
    old = audit.serialize_system(system)
    system.name = name
    system.description = description
    system.company_name = company_name or None
    system.plant = plant or None
    system.address = address or None
    system.country = country or None
    system.building = building or None
    system.updated_at = datetime.utcnow()
    db.commit()
    audit.log(db, user, "systems", system.id, "UPDATE", old_value=old, new_value=audit.serialize_system(system), system_id=system.id)
    return RedirectResponse(f"/systems/{system_id}", status_code=302)


@router.post("/systems/{system_id}/delete")
def delete_system(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if not is_system_owner(user, system):
        raise HTTPException(403, "Only the system owner can delete this system")
    old = audit.serialize_system(system)
    db.delete(system)
    db.commit()
    audit.log(db, user, "systems", system_id, "DELETE", old_value=old, system_id=system_id)
    return RedirectResponse("/", status_code=302)


@router.get("/systems/{system_id}", response_class=HTMLResponse)
def system_editor(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    sections = db.query(models.Section).filter(models.Section.system_id == system_id).order_by(models.Section.order).all()
    sections_json = [{"id": s.id, "name": s.name, "order": s.order} for s in sections]
    req_types = ["functional", "non_functional", "regulatory", "interface", "environmental", "ehs"]
    collaborators = (
        db.query(models.SystemCollaborator)
        .filter(models.SystemCollaborator.system_id == system_id)
        .all()
    )
    all_editors = db.query(models.User).filter(
        models.User.role.in_(["editor", "admin"]),
        models.User.is_active == True,
        models.User.id != system.created_by,
    ).order_by(models.User.username).all()
    collaborator_ids = {c.user_id for c in collaborators}
    return templates.TemplateResponse("system_editor.html", {
        "request": request,
        "user": user,
        "system": system,
        "sections": sections,
        "sections_json": sections_json,
        "req_types": req_types,
        "is_owner": is_system_owner(user, system),
        "can_edit": can_edit_system(user, system_id, db),
        "collaborators": collaborators,
        "all_editors": all_editors,
        "collaborator_ids": collaborator_ids,
    })


# ── Collaborator management API ──────────────────────────────────────────────

class CollaboratorIn(BaseModel):
    user_id: int


@router.get("/api/systems/{system_id}/collaborators")
def list_collaborators(request: Request, system_id: int, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401)
    collabs = (
        db.query(models.SystemCollaborator)
        .filter(models.SystemCollaborator.system_id == system_id)
        .all()
    )
    return [{"user_id": c.user_id, "username": c.user.username, "full_name": c.user.full_name} for c in collabs]


@router.post("/api/systems/{system_id}/collaborators")
def add_collaborator(request: Request, system_id: int, body: CollaboratorIn, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if not is_system_owner(user, system):
        raise HTTPException(403)
    existing = db.query(models.SystemCollaborator).filter(
        models.SystemCollaborator.system_id == system_id,
        models.SystemCollaborator.user_id == body.user_id,
    ).first()
    if existing:
        return {"ok": True, "already": True}
    collab = models.SystemCollaborator(system_id=system_id, user_id=body.user_id, added_by=user.id)
    db.add(collab)
    db.commit()
    return {"ok": True}


@router.delete("/api/systems/{system_id}/collaborators/{target_user_id}")
def remove_collaborator(request: Request, system_id: int, target_user_id: int, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        raise HTTPException(401)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)
    if not is_system_owner(user, system):
        raise HTTPException(403)
    db.query(models.SystemCollaborator).filter(
        models.SystemCollaborator.system_id == system_id,
        models.SystemCollaborator.user_id == target_user_id,
    ).delete()
    db.commit()
    return {"ok": True}
