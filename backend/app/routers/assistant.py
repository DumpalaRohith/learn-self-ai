import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.provider import MockProvider, TutorContext, get_provider
from app.database import get_db
from app.models import ChatMessage, Lesson, Progress, ProgressStatus, Role, Student
from app.schemas import ChatMessageOut, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

_provider = get_provider()
_fallback_provider = MockProvider()

HISTORY_LIMIT = 10


def _get_demo_student(db: Session) -> Student:
    student = db.query(Student).first()
    if not student:
        raise HTTPException(status_code=500, detail="No student seeded")
    return student


def _overall_percent(db: Session, student_id: int) -> float:
    total = db.query(Progress).filter_by(student_id=student_id).count()
    if not total:
        return 0.0
    completed = (
        db.query(Progress)
        .filter_by(student_id=student_id, status=ProgressStatus.completed)
        .count()
    )
    return round(completed / total * 100, 1)


@router.get("/history", response_model=list[ChatMessageOut])
def get_history(lesson_id: int | None = None, db: Session = Depends(get_db)):
    """Returns chat history scoped to lesson_id - a lesson's id for lesson-focused
    chat, or omitted/null for the general (no lesson selected) conversation."""
    student = _get_demo_student(db)
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.student_id == student.id,
            ChatMessage.lesson_id == lesson_id,
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return messages


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    student = _get_demo_student(db)

    lesson = None
    if payload.lesson_id is not None:
        lesson = db.get(Lesson, payload.lesson_id)
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")

    recent = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.student_id == student.id,
            ChatMessage.lesson_id == payload.lesson_id,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    recent.reverse()

    context = TutorContext(
        lesson_title=lesson.title if lesson else None,
        lesson_summary=lesson.content_summary if lesson else None,
        overall_percent_complete=_overall_percent(db, student.id),
        history=[{"role": m.role.value, "content": m.content} for m in recent],
    )

    user_msg = ChatMessage(
        student_id=student.id,
        lesson_id=payload.lesson_id,
        role=Role.user,
        content=payload.message,
    )
    db.add(user_msg)
    db.commit()

    try:
        tutor_reply = _provider.reply(payload.message, context)
        provider_used = _provider.name
    except Exception:
        logger.exception("AI provider '%s' failed, falling back to mock", _provider.name)
        tutor_reply = _fallback_provider.reply(payload.message, context)
        provider_used = f"{_fallback_provider.name}-fallback"

    assistant_msg = ChatMessage(
        student_id=student.id,
        lesson_id=payload.lesson_id,
        role=Role.assistant,
        content=tutor_reply.content,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return ChatResponse(
        reply=assistant_msg, provider=provider_used, follow_ups=tutor_reply.follow_ups
    )
