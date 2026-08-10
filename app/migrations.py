from sqlalchemy import text
from sqlalchemy.orm import Session


def run_all(db: Session):
    _migrate_gmp_flag_to_string(db)
    _migrate_add_enabled_column(db)
    _migrate_add_system_metadata(db)


def _migrate_add_enabled_column(db: Session):
    """Add enabled column to requirements; all existing rows default to True."""
    try:
        db.execute(text("ALTER TABLE requirements ADD COLUMN enabled BOOLEAN DEFAULT 1"))
        db.execute(text("UPDATE requirements SET enabled = 1 WHERE enabled IS NULL"))
        db.commit()
    except Exception:
        db.rollback()  # column already exists — safe to ignore


def _migrate_add_system_metadata(db: Session):
    """Add company_name, plant, address, country, building to systems."""
    for col in ("company_name VARCHAR(256)", "plant VARCHAR(256)",
                "address VARCHAR(512)", "country VARCHAR(128)", "building VARCHAR(256)"):
        try:
            db.execute(text(f"ALTER TABLE systems ADD COLUMN {col}"))
            db.commit()
        except Exception:
            db.rollback()


def _migrate_gmp_flag_to_string(db: Session):
    """Convert boolean gmp_flag (stored as 0/1) to 'GMP'/'GEP' string."""
    for table in ("requirements", "template_requirements"):
        db.execute(text(f"""
            UPDATE {table}
            SET gmp_flag = CASE
                WHEN gmp_flag IN ('1', 'True', 'true', 'GMP') THEN 'GMP'
                ELSE 'GEP'
            END
            WHERE gmp_flag NOT IN ('GMP', 'GEP')
               OR gmp_flag IS NULL
        """))
    db.commit()
