from app import models


def bump_minor_version(db, system_id: int):
    """Increment minor_version on the system; call before db.commit()."""
    system = db.query(models.System).filter(models.System.id == system_id).first()
    if system is not None:
        system.minor_version = (system.minor_version or 0) + 1
