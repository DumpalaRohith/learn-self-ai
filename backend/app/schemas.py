import datetime

from pydantic import BaseModel

from app.models import ProgressStatus, Role


class LessonOut(BaseModel):
    id: int
    title: str
    order: int
    content_summary: str
    status: ProgressStatus
    chat_message_count: int = 0

    class Config:
        from_attributes = True


class CourseOut(BaseModel):
    id: int
    title: str
    description: str
    lessons: list[LessonOut]

    class Config:
        from_attributes = True


class CourseProgressSummary(BaseModel):
    course_id: int
    title: str
    percent_complete: float
    completed_lessons: int
    total_lessons: int


class ProgressSummaryOut(BaseModel):
    overall_percent_complete: float
    total_lessons: int
    completed_lessons: int
    current_streak_days: int
    courses: list[CourseProgressSummary]


class CompleteLessonOut(BaseModel):
    lesson_id: int
    status: ProgressStatus
    completed_at: datetime.datetime | None


class ChatRequest(BaseModel):
    message: str
    lesson_id: int | None = None


class ChatMessageOut(BaseModel):
    id: int
    role: Role
    content: str
    created_at: datetime.datetime
    lesson_id: int | None

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    reply: ChatMessageOut
    provider: str
    follow_ups: list[str] = []
