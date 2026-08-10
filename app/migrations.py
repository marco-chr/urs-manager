from sqlalchemy import text
from sqlalchemy.orm import Session


def run_all(db: Session):
    _migrate_gmp_flag_to_string(db)


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
