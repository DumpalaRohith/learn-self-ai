import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatMessage, Course, Lesson, Progress, ProgressStatus, Student
from app.schemas import (
    CompleteLessonOut,
    CourseCreate,
    CourseOut,
    CourseProgressSummary,
    LessonCreate,
    LessonOut,
    ProgressSummaryOut,
)

router = APIRouter(prefix="/api", tags=["progress"])


def _get_demo_student(db: Session) -> Student:
    student = db.query(Student).first()
    if not student:
        raise HTTPException(status_code=500, detail="No student seeded")
    return student


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)):
    student = _get_demo_student(db)
    courses = db.query(Course).all()

    chat_counts = dict(
        db.query(ChatMessage.lesson_id, func.count(ChatMessage.id))
        .filter(
            ChatMessage.student_id == student.id, ChatMessage.lesson_id.isnot(None)
        )
        .group_by(ChatMessage.lesson_id)
        .all()
    )

    result = []
    for course in courses:
        lessons_out = []
        for lesson in course.lessons:
            progress = (
                db.query(Progress)
                .filter_by(student_id=student.id, lesson_id=lesson.id)
                .first()
            )
            status = progress.status if progress else ProgressStatus.not_started
            lessons_out.append(
                {
                    "id": lesson.id,
                    "title": lesson.title,
                    "order": lesson.order,
                    "content_summary": lesson.content_summary,
                    "status": status,
                    "chat_message_count": chat_counts.get(lesson.id, 0),
                }
            )
        result.append(
            {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "lessons": lessons_out,
            }
        )
    return result


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Subject title is required")

    course = Course(title=title, description=payload.description.strip())
    db.add(course)
    db.commit()
    db.refresh(course)

    return {"id": course.id, "title": course.title, "description": course.description, "lessons": []}


@router.post("/courses/{course_id}/lessons", response_model=LessonOut, status_code=201)
def create_lesson(course_id: int, payload: LessonCreate, db: Session = Depends(get_db)):
    student = _get_demo_student(db)
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Subject not found")

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Topic title is required")

    next_order = db.query(Lesson).filter_by(course_id=course_id).count()
    lesson = Lesson(
        course_id=course_id,
        title=title,
        order=next_order,
        content_summary=payload.content_summary.strip(),
    )
    db.add(lesson)
    db.flush()
    db.add(Progress(student_id=student.id, lesson_id=lesson.id))
    db.commit()
    db.refresh(lesson)

    return {
        "id": lesson.id,
        "title": lesson.title,
        "order": lesson.order,
        "content_summary": lesson.content_summary,
        "status": ProgressStatus.not_started,
        "chat_message_count": 0,
    }


def _compute_streak(db: Session, student_id: int) -> int:
    """Consecutive days (ending today or yesterday) with at least one completion."""
    dates = (
        db.query(func.date(Progress.completed_at))
        .filter(
            Progress.student_id == student_id,
            Progress.status == ProgressStatus.completed,
            Progress.completed_at.isnot(None),
        )
        .distinct()
        .all()
    )
    day_set = {datetime.date.fromisoformat(d[0]) for d in dates if d[0]}
    if not day_set:
        return 0

    today = datetime.date.today()
    cursor = today if today in day_set else today - datetime.timedelta(days=1)
    if cursor not in day_set:
        return 0

    streak = 0
    while cursor in day_set:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak


@router.get("/progress/summary", response_model=ProgressSummaryOut)
def progress_summary(db: Session = Depends(get_db)):
    student = _get_demo_student(db)
    courses = db.query(Course).all()

    course_summaries: list[CourseProgressSummary] = []
    total_lessons = 0
    total_completed = 0

    for course in courses:
        lesson_ids = [lesson.id for lesson in course.lessons]
        total = len(lesson_ids)
        completed = (
            db.query(Progress)
            .filter(
                Progress.student_id == student.id,
                Progress.lesson_id.in_(lesson_ids),
                Progress.status == ProgressStatus.completed,
            )
            .count()
            if lesson_ids
            else 0
        )
        total_lessons += total
        total_completed += completed
        course_summaries.append(
            CourseProgressSummary(
                course_id=course.id,
                title=course.title,
                percent_complete=round((completed / total * 100) if total else 0, 1),
                completed_lessons=completed,
                total_lessons=total,
            )
        )

    overall_percent = round((total_completed / total_lessons * 100) if total_lessons else 0, 1)

    return ProgressSummaryOut(
        overall_percent_complete=overall_percent,
        total_lessons=total_lessons,
        completed_lessons=total_completed,
        current_streak_days=_compute_streak(db, student.id),
        courses=course_summaries,
    )


@router.post("/progress/{lesson_id}/start", response_model=CompleteLessonOut)
def start_lesson(lesson_id: int, db: Session = Depends(get_db)):
    """Marks a lesson in_progress the first time a student opens it. No-ops if the
    lesson is already in_progress or completed."""
    student = _get_demo_student(db)
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    progress = (
        db.query(Progress)
        .filter_by(student_id=student.id, lesson_id=lesson_id)
        .first()
    )
    if not progress:
        progress = Progress(student_id=student.id, lesson_id=lesson_id)
        db.add(progress)

    if progress.status == ProgressStatus.not_started:
        progress.status = ProgressStatus.in_progress
        db.commit()
        db.refresh(progress)

    return CompleteLessonOut(
        lesson_id=lesson_id, status=progress.status, completed_at=progress.completed_at
    )


@router.post("/progress/{lesson_id}/complete", response_model=CompleteLessonOut)
def complete_lesson(lesson_id: int, db: Session = Depends(get_db)):
    student = _get_demo_student(db)
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    progress = (
        db.query(Progress)
        .filter_by(student_id=student.id, lesson_id=lesson_id)
        .first()
    )
    if not progress:
        progress = Progress(student_id=student.id, lesson_id=lesson_id)
        db.add(progress)

    if progress.status == ProgressStatus.completed:
        progress.status = ProgressStatus.not_started
        progress.completed_at = None
    else:
        progress.status = ProgressStatus.completed
        progress.completed_at = datetime.datetime.utcnow()

    db.commit()
    db.refresh(progress)

    return CompleteLessonOut(
        lesson_id=lesson_id, status=progress.status, completed_at=progress.completed_at
    )
