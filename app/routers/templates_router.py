from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, audit
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _user(request, db):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@router.get("/templates", response_class=HTMLResponse)
def list_templates(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    tpls = db.query(models.Template).order_by(models.Template.name).all()
    return templates.TemplateResponse("templates_list.html", {"request": request, "user": user, "templates_list": tpls})


@router.post("/templates/create-from-system/{system_id}")
def create_template_from_system(
    request: Request,
    system_id: int,
    name: str = Form(...),
    description: str = Form(""),
    industry: str = Form("pharma"),
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        raise HTTPException(404)

    tpl = models.Template(name=name, description=description, industry=industry, created_by=user.id)
    db.add(tpl)
    db.flush()

    for sec in system.sections:
        ts = models.TemplateSection(template_id=tpl.id, name=sec.name, order=sec.order)
        db.add(ts)

    for req in system.requirements:
        sec_name = ""
        if req.section_id:
            sec = db.query(models.Section).filter(models.Section.id == req.section_id).first()
            sec_name = sec.name if sec else ""
        tr = models.TemplateRequirement(
            template_id=tpl.id,
            section_name=sec_name,
            req_id=req.req_id,
            req_type=req.req_type,
            description=req.description,
            must_have=req.must_have,
            gmp_flag=req.gmp_flag,
            note=req.note,
        )
        db.add(tr)

    db.commit()
    return RedirectResponse("/templates", status_code=302)


@router.post("/templates/{template_id}/delete")
def delete_template(request: Request, template_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    tpl = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not tpl:
        raise HTTPException(404)
    db.delete(tpl)
    db.commit()
    return RedirectResponse("/templates", status_code=302)
