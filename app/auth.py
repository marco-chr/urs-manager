import bcrypt
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from app import models


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_current_user(request: Request, db: Session) -> models.User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.query(models.User).filter(models.User.id == user_id, models.User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(request: Request, db: Session) -> models.User:
    user = get_current_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def is_system_owner(user: models.User, system: models.System) -> bool:
    """True if the user is admin or the creator of the system."""
    if user.role in ("viewer", "reviewer"):
        return False
    return user.role == "admin" or system.created_by == user.id


def can_edit_system(user: models.User, system_id: int, db: Session) -> bool:
    """True if the user may edit requirements/sections in this system."""
    if user.role == "admin":
        return True
    if user.role in ("viewer", "reviewer"):
        return False
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if not system:
        return False
    if system.created_by == user.id:
        return True
    collab = db.query(models.SystemCollaborator).filter(
        models.SystemCollaborator.system_id == system_id,
        models.SystemCollaborator.user_id == user.id,
    ).first()
    return collab is not None


def seed_admin(db: Session):
    """Create default admin user if no users exist."""
    if db.query(models.User).count() == 0:
        admin = models.User(
            username="admin",
            full_name="Administrator",
            password_hash=hash_password("admin123"),
            role="admin",
        )
        db.add(admin)
        db.commit()
