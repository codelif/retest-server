from typing import List

from flask_login import UserMixin
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import db

__all__ = [
    "MyAakashSession",
    "Chapters",
    "Tests",
    "Questions",
    "Attempts",
]


class MyAakashSession(UserMixin, db.Model):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    psid: Mapped[str] = mapped_column(String(11), unique=True)
    name: Mapped[str]
    login: Mapped[float]
    tokens = mapped_column(JSON())
    config = mapped_column(JSON())
    is_in_sync: Mapped[bool] = mapped_column(Boolean(), default=False)
    sync_progress: Mapped[int] = mapped_column(Integer(), nullable=True)
    attempts: Mapped[List["Attempts"]] = relationship()

    def get_id(self):
        return self.psid


class Chapters(db.Model):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    subject: Mapped[str]
    questions: Mapped[List["Questions"]] = relationship()


class Tests(db.Model):
    __tablename__ = "tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str]
    short_code: Mapped[str]
    attempts: Mapped[List["Attempts"]] = relationship()


class Questions(db.Model):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    content = mapped_column(JSON())
    desc: Mapped[str]
    type: Mapped[str]
    pattern: Mapped[str]
    choices: Mapped[dict] = mapped_column(JSON(), nullable=True)
    marking_scheme: Mapped[str] = mapped_column(String(), nullable=True)
    answer: Mapped[list] = mapped_column(JSON(), nullable=True)
    solution: Mapped[str] = mapped_column(String(), nullable=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey(Chapters.id))
    attempts: Mapped[List["Attempts"]] = relationship()
    children_id = mapped_column(JSON())
    parent_id: Mapped[int] = mapped_column(Integer(), nullable=True)


class Attempts(db.Model):
    __tablename__ = "attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey(Questions.id))
    answer: Mapped[list] = mapped_column(JSON())
    correct: Mapped[bool] = mapped_column(Boolean, nullable=True)
    test_id: Mapped[int] = mapped_column(ForeignKey(Tests.id))
    account_psid: Mapped[str] = mapped_column(ForeignKey(MyAakashSession.psid))
