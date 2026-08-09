from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user, hash_password, require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _user(request, db):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@router.get("/users", response_class=HTMLResponse)
def list_users(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "admin":
        raise HTTPException(403)
    users = db.query(models.User).order_by(models.User.username).all()
    return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": users})


@router.post("/users/create")
def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(""),
    password: str = Form(...),
    role: str = Form("editor"),
    db: Session = Depends(get_db),
):
    user = _user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(403)
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(400, "Username already exists")
    new_user = models.User(
        username=username,
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/update")
def update_user(
    request: Request,
    user_id: int,
    full_name: str = Form(""),
    role: str = Form("editor"),
    is_active: str = Form("on"),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    current = _user(request, db)
    if not current or current.role != "admin":
        raise HTTPException(403)
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404)
    target.full_name = full_name
    target.role = role
    target.is_active = is_active == "on"
    if password:
        target.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/delete")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    current = _user(request, db)
    if not current or current.role != "admin":
        raise HTTPException(403)
    if current.id == user_id:
        raise HTTPException(400, "Cannot delete yourself")
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404)
    db.delete(target)
    db.commit()
    return RedirectResponse("/users", status_code=302)
