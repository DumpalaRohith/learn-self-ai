from sqlalchemy.orm import Session

from app.models import Course, Lesson, Progress, Student

COURSES = [
    (
        "Python Fundamentals",
        "A first course covering the core building blocks of Python.",
        [
            (
                "Variables & Data Types",
                "Storing values in named variables; int, float, str, bool, and how "
                "Python infers types automatically.",
            ),
            (
                "Conditionals",
                "Branching logic with if / elif / else, comparison and boolean "
                "operators.",
            ),
            (
                "Loops",
                "Repeating work with for and while loops, break/continue, and "
                "iterating over sequences.",
            ),
            (
                "Functions",
                "Defining reusable blocks with def, parameters, return values, and "
                "default arguments.",
            ),
            (
                "Lists & Dictionaries",
                "Storing collections with lists and key-value pairs with dicts, "
                "plus common operations like append, slicing, and lookup.",
            ),
        ],
    ),
    (
        "Data Structures Basics",
        "A second course going one level deeper into how data is organized.",
        [
            (
                "Sets & Tuples",
                "Unordered unique collections with sets, and immutable sequences "
                "with tuples.",
            ),
            (
                "Stacks & Queues",
                "LIFO and FIFO access patterns, and how to implement them with "
                "plain Python lists.",
            ),
            (
                "Dictionaries in Depth",
                "Nested dictionaries, iterating keys/values/items, and common "
                "lookup patterns.",
            ),
            (
                "Big-O Intuition",
                "A gentle first look at why some operations are fast and others "
                "get slow as data grows.",
            ),
        ],
    ),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Student).first():
        return

    student = Student(name="Demo Student")
    db.add(student)
    db.flush()

    for course_title, course_desc, lessons in COURSES:
        course = Course(title=course_title, description=course_desc)
        db.add(course)
        db.flush()

        for i, (title, summary) in enumerate(lessons):
            lesson = Lesson(
                course_id=course.id, title=title, order=i, content_summary=summary
            )
            db.add(lesson)
            db.flush()
            db.add(Progress(student_id=student.id, lesson_id=lesson.id))

    db.commit()
