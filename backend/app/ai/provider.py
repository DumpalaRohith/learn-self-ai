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
    mode: str | None = None  # None (default), "simpler", "exercise", or "quiz"


@dataclass
class TutorReply:
    content: str
    follow_ups: list[str] = field(default_factory=list)


SYSTEM_PROMPT_TEMPLATE = """You are a friendly, encouraging AI tutor inside a learning platform \
called LearnSelfAI. The student is learning programming fundamentals.

{lesson_line}
The student has completed {percent:.0f}% of the course so far.

{mode_instructions}

Avoid decorative markdown like bold section headers - write in plain, direct prose, and \
use fenced code blocks only for actual code. Never use em dashes (—) or curly quotes; \
use commas, periods, or straight quotes instead. If the question is unrelated to the \
current lesson, still answer it helpfully.

After your answer, on its own final line, suggest 2-3 short natural follow-up questions \
the student might want to ask next, formatted EXACTLY like this with no extra text after:
FOLLOWUPS: question one? | question two? | question three?"""

MODE_INSTRUCTIONS = {
    None: (
        "Structure your answer in four short, clearly separated parts, in this order:\n"
        "1. A simple explanation of the topic the student is asking about.\n"
        "2. Key concepts, as a short bulleted list.\n"
        "3. One practical example (a short code snippet if the topic is code-related).\n"
        "4. 2 to 3 practice questions for the student to try on their own (do not answer "
        "them yourself).\n"
        "Keep every part brief. This is a quick study aid, not a textbook chapter."
    ),
    "simpler": (
        "The student found the normal explanation too hard and wants it SIMPLER. Give a "
        "short, plain-language explanation with a relatable everyday analogy. Skip the "
        "key concepts list and practice questions this time, just re-explain simply in a "
        "short paragraph."
    ),
    "exercise": (
        "The student asked for a practice exercise. Give ONE concrete, small practice "
        "problem on the current topic (not the answer). Keep it to a few sentences."
    ),
    "quiz": (
        "The student asked to be quizzed. Ask ONE quiz question about the current topic "
        "to test their understanding (not the answer). Keep it to one or two sentences."
    ),
}

_FOLLOWUPS_RE = re.compile(r"\n?FOLLOWUPS:\s*(.+)\s*$", re.IGNORECASE)


def _build_system_prompt(context: TutorContext) -> str:
    lesson_line = (
        f"The student is currently on the lesson '{context.lesson_title}': "
        f"{context.lesson_summary}"
        if context.lesson_title
        else "The student has not selected a specific lesson."
    )
    mode_instructions = MODE_INSTRUCTIONS.get(context.mode, MODE_INSTRUCTIONS[None])
    return SYSTEM_PROMPT_TEMPLATE.format(
        lesson_line=lesson_line,
        percent=context.overall_percent_complete,
        mode_instructions=mode_instructions,
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
        topic = context.lesson_title or "this topic"
        summary = context.lesson_summary or "the basics of what you're asking about"

        if context.mode == "exercise":
            body = (
                f"{opener} Here's a quick practice problem on {topic}: try writing a "
                f"short snippet that puts today's idea to use, then run it and check "
                f"the output matches what you expected."
            )
        elif context.mode == "quiz":
            body = f"Quick check: in your own words, what is the main idea behind {topic}?"
        elif context.mode == "simpler":
            body = (
                f"{opener} Think of {topic} like a everyday routine you already know: "
                f"you follow a few small, repeatable steps to get to the result. "
                f"{summary}"
            )
        else:
            body = (
                f"{opener}\n\n"
                f"Explanation: {summary}\n\n"
                f"Key concepts:\n"
                f"- The core idea behind {topic}\n"
                f"- How it fits with what you've already covered\n"
                f"- A common pitfall beginners run into\n\n"
                f"Example: try a small, self-contained snippet that only exercises "
                f"{topic}, run it, and compare the output to what you expected.\n\n"
                f"Practice questions:\n"
                f"1. In your own words, what problem does {topic} solve?\n"
                f"2. Can you write a 3-line example using {topic}?\n"
                f"3. What would happen if you got a key detail of {topic} wrong?"
            )

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
