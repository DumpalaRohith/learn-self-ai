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
