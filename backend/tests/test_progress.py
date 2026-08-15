def test_list_courses_seeded(client):
    res = client.get("/api/courses")
    assert res.status_code == 200
    courses = res.json()
    assert len(courses) == 2
    assert len(courses[0]["lessons"]) == 5
    assert len(courses[1]["lessons"]) == 4
    assert all(
        lesson["status"] == "not_started"
        for course in courses
        for lesson in course["lessons"]
    )


def test_progress_summary_starts_at_zero(client):
    res = client.get("/api/progress/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["overall_percent_complete"] == 0
    assert summary["completed_lessons"] == 0
    assert summary["total_lessons"] == 9
    assert len(summary["courses"]) == 2


def test_start_lesson_marks_in_progress(client):
    courses = client.get("/api/courses").json()
    lesson_id = courses[0]["lessons"][0]["id"]

    res = client.post(f"/api/progress/{lesson_id}/start")
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"

    courses = client.get("/api/courses").json()
    assert courses[0]["lessons"][0]["status"] == "in_progress"


def test_start_lesson_does_not_override_completed(client):
    courses = client.get("/api/courses").json()
    lesson_id = courses[1]["lessons"][0]["id"]

    client.post(f"/api/progress/{lesson_id}/complete")
    res = client.post(f"/api/progress/{lesson_id}/start")
    assert res.json()["status"] == "completed"


def test_complete_lesson_updates_summary(client):
    courses = client.get("/api/courses").json()
    lesson_id = courses[0]["lessons"][1]["id"]

    res = client.post(f"/api/progress/{lesson_id}/complete")
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    summary = client.get("/api/progress/summary").json()
    assert summary["current_streak_days"] == 1
    assert summary["completed_lessons"] >= 1


def test_toggle_lesson_back_to_not_started(client):
    courses = client.get("/api/courses").json()
    lesson_id = courses[0]["lessons"][2]["id"]

    client.post(f"/api/progress/{lesson_id}/complete")
    res = client.post(f"/api/progress/{lesson_id}/complete")
    assert res.json()["status"] == "not_started"
    assert res.json()["completed_at"] is None


def test_complete_unknown_lesson_404(client):
    res = client.post("/api/progress/9999/complete")
    assert res.status_code == 404


def test_start_unknown_lesson_404(client):
    res = client.post("/api/progress/9999/start")
    assert res.status_code == 404


def test_create_subject(client):
    res = client.post("/api/courses", json={"title": "Web Basics", "description": "HTML and CSS"})
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "Web Basics"
    assert body["lessons"] == []

    courses = client.get("/api/courses").json()
    assert len(courses) == 3
    assert courses[-1]["title"] == "Web Basics"


def test_create_subject_requires_title(client):
    res = client.post("/api/courses", json={"title": "   ", "description": "x"})
    assert res.status_code == 422


def test_create_topic_under_subject(client):
    course = client.post("/api/courses", json={"title": "Testing 101"}).json()

    res = client.post(
        f"/api/courses/{course['id']}/lessons",
        json={"title": "Writing your first test", "content_summary": "pytest basics"},
    )
    assert res.status_code == 201
    lesson = res.json()
    assert lesson["title"] == "Writing your first test"
    assert lesson["status"] == "not_started"
    assert lesson["order"] == 0

    second = client.post(
        f"/api/courses/{course['id']}/lessons", json={"title": "Fixtures"}
    ).json()
    assert second["order"] == 1

    courses = client.get("/api/courses").json()
    updated = next(c for c in courses if c["id"] == course["id"])
    assert len(updated["lessons"]) == 2

    summary = client.get("/api/progress/summary").json()
    assert summary["total_lessons"] >= 2


def test_create_topic_under_unknown_subject_404(client):
    res = client.post("/api/courses/9999/lessons", json={"title": "x"})
    assert res.status_code == 404


def test_create_topic_requires_title(client):
    course = client.post("/api/courses", json={"title": "Another Subject"}).json()
    res = client.post(f"/api/courses/{course['id']}/lessons", json={"title": " "})
    assert res.status_code == 422


def test_delete_subject_removes_it_and_its_topics(client):
    course = client.post("/api/courses", json={"title": "Temporary Subject"}).json()
    client.post(f"/api/courses/{course['id']}/lessons", json={"title": "Temp topic"})

    before = client.get("/api/progress/summary").json()["total_lessons"]

    res = client.delete(f"/api/courses/{course['id']}")
    assert res.status_code == 204

    courses = client.get("/api/courses").json()
    assert all(c["id"] != course["id"] for c in courses)

    after = client.get("/api/progress/summary").json()["total_lessons"]
    assert after == before - 1


def test_delete_unknown_subject_404(client):
    res = client.delete("/api/courses/9999")
    assert res.status_code == 404
