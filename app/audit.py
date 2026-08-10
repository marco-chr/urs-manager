import json
from datetime import datetime
from sqlalchemy.orm import Session
from app import models


def log(
    db: Session,
    user: models.User,
    table_name: str,
    record_id: int,
    action: str,
    old_value=None,
    new_value=None,
    system_id: int = None,
    ip_address: str = None,
):
    entry = models.AuditLog(
        user_id=user.id,
        username=user.username,
        system_id=system_id,
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_value=json.dumps(old_value) if old_value is not None else None,
        new_value=json.dumps(new_value) if new_value is not None else None,
        timestamp=datetime.utcnow(),
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()


def serialize_requirement(req: models.Requirement) -> dict:
    return {
        "req_id": req.req_id,
        "req_type": req.req_type,
        "description": req.description,
        "must_have": req.must_have,
        "gmp_flag": req.gmp_flag,
        "enabled": req.enabled,
        "note": req.note,
        "section_id": req.section_id,
    }


def serialize_section(sec: models.Section) -> dict:
    return {"name": sec.name, "order": sec.order}


def serialize_system(sys: models.System) -> dict:
    return {
        "name": sys.name, "description": sys.description, "status": sys.status,
        "company_name": sys.company_name, "plant": sys.plant,
        "address": sys.address, "country": sys.country, "building": sys.building,
    }
