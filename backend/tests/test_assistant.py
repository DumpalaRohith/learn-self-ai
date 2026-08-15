def test_chat_uses_mock_provider_without_api_key(client):
    res = client.post("/api/assistant/chat", json={"message": "What is a variable?"})
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "mock"
    assert body["reply"]["role"] == "assistant"
    assert len(body["reply"]["content"]) > 0


def test_chat_grounds_reply_in_lesson_context(client):
    courses = client.get("/api/courses").json()
    lesson = courses[0]["lessons"][2]  # "Loops"

    res = client.post(
        "/api/assistant/chat",
        json={"message": "I'm stuck, can you help?", "lesson_id": lesson["id"]},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]["content"]
    assert lesson["title"] in reply


def test_chat_falls_back_to_mock_when_provider_errors(client, monkeypatch):
    import app.routers.assistant as assistant_module

    class BrokenProvider:
        name = "gemini"

        def reply(self, message, context):
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr(assistant_module, "_provider", BrokenProvider())

    res = client.post("/api/assistant/chat", json={"message": "hello"})
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "mock-fallback"
    assert len(body["reply"]["content"]) > 0


def test_history_persists_and_scopes_by_lesson(client):
    courses = client.get("/api/courses").json()
    lesson_id = courses[0]["lessons"][0]["id"]
    other_lesson_id = courses[0]["lessons"][1]["id"]

    client.post("/api/assistant/chat", json={"message": "hello", "lesson_id": lesson_id})

    history = client.get(f"/api/assistant/history?lesson_id={lesson_id}").json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    other_history = client.get(f"/api/assistant/history?lesson_id={other_lesson_id}").json()
    assert all(m["content"] != "hello" for m in other_history)
