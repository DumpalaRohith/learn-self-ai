import os
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx


@dataclass
class TutorContext:
    lesson_title: str | None = None
    lesson_summary: str | None = None
    overall_percent_complete: float = 0.0
    history: list[dict] = field(default_factory=list)  # [{"role": "user"/"assistant", "content": str}]


@dataclass
class TutorReply:
    content: str
    follow_ups: list[str] = field(default_factory=list)


SYSTEM_PROMPT_TEMPLATE = """You are a friendly, encouraging AI tutor inside a learning platform \
called LearnSelfAI. The student is learning programming fundamentals.

{lesson_line}
The student has completed {percent:.0f}% of the course so far.

Answer the student's question clearly and concisely. Use short examples where helpful, \
and use fenced code blocks for actual code. Avoid decorative markdown like bold section \
headers - write in plain, direct prose. Never use em dashes (—) or curly quotes; use \
commas, periods, or straight quotes instead. If the question is unrelated to the current \
lesson, still answer it helpfully. Keep replies focused - a few short paragraphs or a \
small code snippet at most. If the student asks for an exercise or to be quizzed, give \
ONE concrete small practice problem (not the answer).

After your answer, on its own final line, suggest 2-3 short natural follow-up questions \
the student might want to ask next, formatted EXACTLY like this with no extra text after:
FOLLOWUPS: question one? | question two? | question three?"""

_FOLLOWUPS_RE = re.compile(r"\n?FOLLOWUPS:\s*(.+)\s*$", re.IGNORECASE)


def _build_system_prompt(context: TutorContext) -> str:
    lesson_line = (
        f"The student is currently on the lesson '{context.lesson_title}': "
        f"{context.lesson_summary}"
        if context.lesson_title
        else "The student has not selected a specific lesson."
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        lesson_line=lesson_line, percent=context.overall_percent_complete
    )


def _parse_reply(raw_text: str) -> TutorReply:
    match = _FOLLOWUPS_RE.search(raw_text.strip())
    if not match:
        return TutorReply(content=raw_text.strip())

    content = raw_text[: match.start()].strip()
    follow_ups = [q.strip(" ?") + "?" for q in match.group(1).split("|") if q.strip()]
    return TutorReply(content=content, follow_ups=follow_ups[:3])


class AIProvider(ABC):
    name: str

    @abstractmethod
    def reply(self, message: str, context: TutorContext) -> TutorReply: ...


class AnthropicProvider(AIProvider):
    """Paid API (anthropic.com) - used only if ANTHROPIC_API_KEY is set."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def reply(self, message: str, context: TutorContext) -> TutorReply:
        messages = [
            {"role": m["role"], "content": m["content"]} for m in context.history
        ]
        messages.append({"role": "user", "content": message})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=600,
            system=_build_system_prompt(context),
            messages=messages,
        )
        raw = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return _parse_reply(raw)


class GeminiProvider(AIProvider):
    """Free-tier API via Google AI Studio - used if GEMINI_API_KEY is set."""

    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self._api_key = api_key
        self._model = model

    def reply(self, message: str, context: TutorContext) -> TutorReply:
        contents = []
        for m in context.history:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": message}]})

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent"
        )
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": _build_system_prompt(context)}]},
            "generationConfig": {"maxOutputTokens": 600},
        }
        resp = httpx.post(
            url,
            params={"key": self._api_key},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        raw = "".join(p.get("text", "") for p in parts).strip()
        return _parse_reply(raw)


class GroqProvider(AIProvider):
    """Free-tier API via console.groq.com - used if GROQ_API_KEY is set."""

    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self._api_key = api_key
        self._model = model

    def reply(self, message: str, context: TutorContext) -> TutorReply:
        messages = [{"role": "system", "content": _build_system_prompt(context)}]
        messages += [{"role": m["role"], "content": m["content"]} for m in context.history]
        messages.append({"role": "user", "content": message})

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": messages, "max_tokens": 600},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip()
        return _parse_reply(raw)


class MockProvider(AIProvider):
    """Deterministic, context-aware fallback used when no AI API key is configured
    (or when a configured provider errors out, e.g. a free-tier quota is exhausted)."""

    name = "mock"

    _OPENERS = [
        "Good question!",
        "Let's break that down.",
        "Happy to help with that.",
    ]

    def reply(self, message: str, context: TutorContext) -> TutorReply:
        opener = random.choice(self._OPENERS)
        lower = message.lower()
        topic = context.lesson_title or "this topic"

        if context.lesson_title:
            focus = (
                f"Since you're working through {context.lesson_title}, here's a "
                f"pointer grounded in that topic: {context.lesson_summary}"
            )
        else:
            focus = "Pick a lesson from the sidebar and I can tailor my answer to it."

        if any(k in lower for k in ("exercise", "practice", "quiz", "test me")):
            body = (
                f"{opener} Here's a quick practice problem on {topic}: try writing a "
                f"short snippet that puts today's idea to use, then run it and see if "
                f"the output matches what you expected. {focus}"
            )
        elif "?" in message:
            body = (
                f"{opener} Here's a starting point on '{message.strip()}': "
                f"break the problem into small steps, try a tiny example in a Python "
                f"shell, and check the result matches what you expect. {focus}"
            )
        elif any(k in lower for k in ("stuck", "confused", "don't understand", "help")):
            body = (
                f"{opener} It's normal to feel stuck here. {focus} Try re-reading the "
                "summary above, then write a 3-line example yourself before moving on."
            )
        else:
            body = f"{opener} {focus} Let me know what part you'd like to dig into."

        body += (
            "\n\n(This is an offline demo reply. Configure a free AI API key to get "
            "real AI-generated answers.)"
        )

        follow_ups = [
            f"Can you show a small example for {topic}?",
            "What's a common mistake beginners make here?",
            f"Give me a short exercise on {topic}",
        ]
        return TutorReply(content=body, follow_ups=follow_ups)


def get_provider() -> AIProvider:
    """Picks the first configured provider, in order: Anthropic, Gemini, Groq, else
    the offline mock. All three real providers are free-tier friendly except
    Anthropic (paid), which is only used if explicitly configured."""
    if api_key := os.getenv("ANTHROPIC_API_KEY"):
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        return AnthropicProvider(api_key=api_key, model=model)
    if api_key := os.getenv("GEMINI_API_KEY"):
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        return GeminiProvider(api_key=api_key, model=model)
    if api_key := os.getenv("GROQ_API_KEY"):
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        return GroqProvider(api_key=api_key, model=model)
    return MockProvider()
