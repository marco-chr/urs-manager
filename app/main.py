import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, SessionLocal
from app import models
from app.auth import seed_admin
from app.migrations import run_all as run_migrations
from app.routers import (
    auth_router, systems_router, sections_router,
    requirements_router, templates_router, export_router,
    audit_router, users_router, review_router,
)

models.Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_admin(db)
    run_migrations(db)

app = FastAPI(title="URS Manager")

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-urs-app-secret")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=28800)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router.router)
app.include_router(systems_router.router)
app.include_router(sections_router.router)
app.include_router(requirements_router.router)
app.include_router(templates_router.router)
app.include_router(export_router.router)
app.include_router(audit_router.router)
app.include_router(users_router.router)
app.include_router(review_router.router)
