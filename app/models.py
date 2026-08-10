from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False)
    full_name = Column(String(128))
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default="editor")  # admin, editor, viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    industry = Column(String(64))  # pharma, food, automotive, etc.
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    sections = relationship("TemplateSection", back_populates="template", cascade="all, delete-orphan")
    requirements = relationship("TemplateRequirement", back_populates="template", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])


class TemplateSection(Base):
    __tablename__ = "template_sections"
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    name = Column(String(256), nullable=False)
    order = Column(Integer, default=0)

    template = relationship("Template", back_populates="sections")


class TemplateRequirement(Base):
    __tablename__ = "template_requirements"
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    section_name = Column(String(256))
    req_id = Column(String(32))
    req_type = Column(String(32))
    description = Column(Text, nullable=False)
    must_have = Column(Boolean, default=True)
    gmp_flag = Column(String(8), default="GEP")  # "GMP" or "GEP"
    note = Column(Text)

    template = relationship("Template", back_populates="requirements")


class System(Base):
    __tablename__ = "systems"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    status = Column(String(16), default="draft")  # draft, review, approved
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sections = relationship("Section", back_populates="system", cascade="all, delete-orphan", order_by="Section.order")
    requirements = relationship("Requirement", back_populates="system", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])


class SystemCollaborator(Base):
    __tablename__ = "system_collaborators"
    id = Column(Integer, primary_key=True, index=True)
    system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    added_by = Column(Integer, ForeignKey("users.id"))
    added_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("system_id", "user_id"),)

    user = relationship("User", foreign_keys=[user_id])
    adder = relationship("User", foreign_keys=[added_by])


class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True, index=True)
    system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    name = Column(String(256), nullable=False)
    order = Column(Integer, default=0)

    system = relationship("System", back_populates="sections")
    requirements = relationship("Requirement", back_populates="section")


class Requirement(Base):
    __tablename__ = "requirements"
    id = Column(Integer, primary_key=True, index=True)
    system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    req_id = Column(String(32))
    req_type = Column(String(32), default="functional")
    description = Column(Text, nullable=False)
    must_have = Column(Boolean, default=True)
    gmp_flag = Column(String(8), default="GEP")  # "GMP" or "GEP"
    enabled = Column(Boolean, default=True)
    note = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    system = relationship("System", back_populates="requirements")
    section = relationship("Section", back_populates="requirements")
    creator = relationship("User", foreign_keys=[created_by])


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    username = Column(String(64))
    system_id = Column(Integer, nullable=True)
    table_name = Column(String(64))
    record_id = Column(Integer)
    action = Column(String(16))  # CREATE, UPDATE, DELETE
    old_value = Column(Text)
    new_value = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(64))

    user = relationship("User", foreign_keys=[user_id])
