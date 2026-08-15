const state = {
  courses: [],
  activeCourseId: null,
  activeLessonId: null,
};

const el = {
  themeToggle: document.getElementById("theme-toggle"),
  themeIcon: document.getElementById("theme-icon"),
  statRing: document.getElementById("stat-ring"),
  statRingText: document.getElementById("stat-ring-text"),
  statLessonsSub: document.getElementById("stat-lessons-sub"),
  statStreak: document.getElementById("stat-streak"),
  statCompleted: document.getElementById("stat-completed"),
  statInProgress: document.getElementById("stat-inprogress"),
  courseTabs: document.getElementById("course-tabs"),
  courseDesc: document.getElementById("course-desc"),
  lessonList: document.getElementById("lesson-list"),
  chatContext: document.getElementById("chat-context"),
  chatMessages: document.getElementById("chat-messages"),
  chatEmpty: document.getElementById("chat-empty"),
  quickActions: document.getElementById("quick-actions"),
  followUps: document.getElementById("follow-ups"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
};

// ---------- theme ----------

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  el.themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
  localStorage.setItem("learnselfai-theme", theme);
}

(function initTheme() {
  const saved = localStorage.getItem("learnselfai-theme");
  applyTheme(saved || "light");
})();

el.themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  applyTheme(current === "dark" ? "light" : "dark");
});

// ---------- minimal markdown -> safe HTML ----------

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderMarkdown(raw) {
  const escaped = escapeHtml(raw);
  const withFences = escaped.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) => {
    return `<pre><code>${code.trim()}</code></pre>`;
  });
  const withInlineCode = withFences.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  const withBold = withInlineCode.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  const withItalic = withBold.replace(/(?<![\w_])_([^_\n]+)_(?![\w_])/g, "<em>$1</em>");
  const paragraphs = withItalic
    .split(/\n{2,}/)
    .map((block) => `<p>${block.replace(/\n/g, "<br>")}</p>`)
    .join("");
  return paragraphs;
}

// ---------- data fetch ----------

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

async function loadSummary() {
  const summary = await fetchJSON("/api/progress/summary");
  el.statRing.style.setProperty("--pct", summary.overall_percent_complete);
  el.statRingText.textContent = `${Math.round(summary.overall_percent_complete)}%`;
  el.statLessonsSub.textContent = `${summary.completed_lessons} of ${summary.total_lessons} lessons`;
  el.statStreak.textContent = summary.current_streak_days;
  el.statCompleted.textContent = summary.completed_lessons;

  const inProgress = state.courses
    .flatMap((c) => c.lessons)
    .filter((l) => l.status === "in_progress").length;
  el.statInProgress.textContent = inProgress;
}

function coursePercent(course) {
  if (!course.lessons.length) return 0;
  const completed = course.lessons.filter((l) => l.status === "completed").length;
  return Math.round((completed / course.lessons.length) * 100);
}

function renderCourseTabs() {
  el.courseTabs.innerHTML = "";
  state.courses.forEach((course) => {
    const btn = document.createElement("button");
    btn.className = "course-tab" + (course.id === state.activeCourseId ? " active" : "");
    btn.innerHTML = `${escapeHtml(course.title)} <span class="course-tab-pct">${coursePercent(course)}%</span>`;
    btn.addEventListener("click", () => {
      state.activeCourseId = course.id;
      renderCourseTabs();
      resetChatToGeneral();
    });
    el.courseTabs.appendChild(btn);
  });
}

function renderLessons() {
  const course = state.courses.find((c) => c.id === state.activeCourseId);
  if (!course) return;

  el.courseDesc.textContent = course.description;
  el.lessonList.innerHTML = "";

  course.lessons.forEach((lesson) => {
    const li = document.createElement("li");
    li.className = `lesson-item status-${lesson.status}`;
    if (lesson.id === state.activeLessonId) li.classList.add("active");

    const check = document.createElement("div");
    check.className = "lesson-check";
    check.textContent = lesson.status === "completed" ? "✓" : "";

    const statusLabel = { not_started: "Not started", in_progress: "In progress", completed: "Completed" }[lesson.status];
    const chatNote = lesson.chat_message_count > 0
      ? ` <span class="lesson-chat-note">· 💬 ${lesson.chat_message_count} message${lesson.chat_message_count === 1 ? "" : "s"} (click to view)</span>`
      : "";

    const body = document.createElement("div");
    body.className = "lesson-body";
    body.innerHTML = `<div class="lesson-title">${lesson.title}</div><div class="lesson-summary">${lesson.content_summary}</div><div class="lesson-status-label">${statusLabel}${chatNote}</div>`;

    const completeBtn = document.createElement("button");
    completeBtn.type = "button";
    completeBtn.className = "lesson-complete-btn";
    completeBtn.textContent = lesson.status === "completed" ? "✓ Completed" : "Mark complete";
    completeBtn.title = lesson.status === "completed"
      ? "Click to mark as not completed"
      : "Click to mark this lesson complete";
    completeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleComplete(lesson.id);
    });

    li.appendChild(check);
    li.appendChild(body);
    li.appendChild(completeBtn);
    li.addEventListener("click", () => selectLesson(lesson));

    el.lessonList.appendChild(li);
  });
}

async function toggleComplete(lessonId) {
  await fetchJSON(`/api/progress/${lessonId}/complete`, { method: "POST" });
  await refreshCourses();
  await loadSummary();
}

// ---------- remember last-open lesson across page reloads ----------
// Chat history itself always lives in the database (see /api/assistant/history);
// this only remembers *which* lesson to reopen so a refresh doesn't drop you back
// to "General help" and make already-saved history look like it vanished.

function saveSelection() {
  localStorage.setItem(
    "learnselfai-selection",
    JSON.stringify({ courseId: state.activeCourseId, lessonId: state.activeLessonId })
  );
}

function loadSavedSelection() {
  try {
    return JSON.parse(localStorage.getItem("learnselfai-selection") || "null");
  } catch {
    return null;
  }
}

function resetChatToGeneral() {
  state.activeLessonId = null;
  saveSelection();
  el.chatContext.textContent = "General help. Select a lesson to focus me on it.";
  renderLessons();
  loadHistory();
}

async function selectLesson(lesson) {
  state.activeLessonId = lesson.id;
  saveSelection();
  el.chatContext.textContent = `Focused on: ${lesson.title}`;
  renderLessons();

  if (lesson.status === "not_started") {
    await fetchJSON(`/api/progress/${lesson.id}/start`, { method: "POST" });
    await refreshCourses();
    await loadSummary();
  }

  loadHistory();
}

async function refreshCourses() {
  state.courses = await fetchJSON("/api/courses");
  if (!state.activeCourseId && state.courses.length) {
    state.activeCourseId = state.courses[0].id;
  }
  renderCourseTabs();
  renderLessons();
}

// ---------- chat ----------

function clearFollowUps() {
  el.followUps.innerHTML = "";
}

function renderFollowUps(followUps) {
  clearFollowUps();
  followUps.forEach((q) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "follow-up-chip";
    chip.textContent = q;
    chip.addEventListener("click", () => sendMessage(q));
    el.followUps.appendChild(chip);
  });
}

function appendMessage(role, content) {
  el.chatEmpty.style.display = "none";
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);
  el.chatMessages.appendChild(div);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
  return div;
}

async function loadHistory() {
  el.chatMessages.innerHTML = "";
  el.chatMessages.appendChild(el.chatEmpty);
  el.chatEmpty.style.display = "block";
  clearFollowUps();

  const qs = state.activeLessonId ? `?lesson_id=${state.activeLessonId}` : "";
  const history = await fetchJSON(`/api/assistant/history${qs}`);
  history.forEach((m) => appendMessage(m.role, m.content));
}

async function sendMessage(message) {
  if (!message) return;

  if (!state.activeLessonId) {
    appendMessage("user", message);
    appendMessage("assistant", "Please select a lesson from the list on the left first, so I know what to help you with.");
    return;
  }

  appendMessage("user", message);

  const submitBtn = el.chatForm.querySelector("button");
  submitBtn.disabled = true;
  clearFollowUps();
  const thinking = appendMessage("assistant", "…");
  thinking.classList.add("pending");

  try {
    const res = await fetchJSON("/api/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, lesson_id: state.activeLessonId }),
    });
    thinking.classList.remove("pending");
    thinking.innerHTML = renderMarkdown(res.reply.content);
    el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
    renderFollowUps(res.follow_ups || []);
  } catch (err) {
    thinking.classList.remove("pending");
    thinking.textContent = "Sorry, something went wrong reaching the tutor.";
  } finally {
    submitBtn.disabled = false;
  }
}

el.chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = el.chatInput.value.trim();
  if (!message) return;
  el.chatInput.value = "";
  sendMessage(message);
});

el.quickActions.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-prompt]");
  if (!btn) return;
  sendMessage(btn.dataset.prompt);
});

// ---------- init ----------

(async function init() {
  await refreshCourses();
  await loadSummary();

  const saved = loadSavedSelection();
  const savedCourse = saved && state.courses.find((c) => c.id === saved.courseId);
  const savedLesson = savedCourse && savedCourse.lessons.find((l) => l.id === saved.lessonId);

  if (savedCourse) {
    state.activeCourseId = savedCourse.id;
    renderCourseTabs();
  }

  if (savedLesson) {
    await selectLesson(savedLesson);
  } else {
    resetChatToGeneral();
  }
})();
