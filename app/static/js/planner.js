(function () {
  const A = window.AprovaOS;
  const DAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  let tasks = [];
  let taskSummary = null;
  let events = [];
  let reschedulePreview = [];
  let calendarView = "week";

  function bindQuickActions() {
    A.qsa("[data-reschedule-preview]").forEach((button) => {
      button.addEventListener("click", runReschedulePreview);
    });

    A.qs("#confirm-reschedule")?.addEventListener("click", confirmReschedulePreview);
    A.qs("#cancel-reschedule")?.addEventListener("click", cancelReschedulePreview);

    A.qsa("[data-priority]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await A.api.post("/api/planner/priority", { weekly_priority: button.dataset.priority });
          A.toast(`Prioridade ajustada para ${button.dataset.priority}.`);
          window.location.reload();
        } catch (error) {
          A.toast(error.message, "error");
        }
      });
    });
  }

  async function runReschedulePreview() {
    try {
      const result = await A.api.post("/api/tasks/reschedule/preview", { mode: "Recuperação" });
      reschedulePreview = result.preview || [];
      renderReschedulePreview(result.message || "Preview gerado.");
    } catch (error) {
      A.toast(error.message, "error");
    }
  }

  function renderReschedulePreview(message) {
    const card = A.qs("#reschedule-preview");
    const list = A.qs("#reschedule-preview-list");
    if (!card || !list) return;

    card.classList.remove("hidden");
    A.clear(list);

    if (!reschedulePreview.length) {
      list.append(A.emptyState(message || "Sem atrasos para reorganizar."));
      A.qs("#confirm-reschedule")?.classList.add("hidden");
      A.qs("#cancel-reschedule")?.classList.remove("hidden");
      return;
    }

    reschedulePreview.forEach((item) => {
      list.append(
        A.el("div", { className: "task-item" }, [
          A.el("strong", { text: item.title }),
          A.el("span", { text: `Antes: ${A.formatDate(item.old_deadline)} · Novo prazo: ${A.formatDate(item.new_deadline)}` }),
          A.el("small", { text: item.window ? `${item.window.date} ${item.window.start_time}-${item.window.end_time}` : "Sem janela livre, reagendado por fallback" }),
        ])
      );
    });

    A.qs("#confirm-reschedule")?.classList.remove("hidden");
    A.qs("#cancel-reschedule")?.classList.remove("hidden");
  }

  async function confirmReschedulePreview() {
    if (!reschedulePreview.length) return;
    try {
      const result = await A.api.post("/api/tasks/reschedule/confirm", { preview: reschedulePreview });
      A.toast(result.message || "Reorganização confirmada.");
      cancelReschedulePreview();
      if (document.body.dataset.page === "pending") await loadTasks();
      if (document.body.dataset.page === "dashboard") window.location.reload();
    } catch (error) {
      A.toast(error.message, "error");
    }
  }

  function cancelReschedulePreview() {
    reschedulePreview = [];
    const card = A.qs("#reschedule-preview");
    if (card) card.classList.add("hidden");
  }

  async function loadTasks() {
    const data = await A.api.get("/api/tasks");
    tasks = data.tasks || [];
    taskSummary = data.summary || null;
    renderTaskSummary();
    renderTasks();
  }

  function renderTaskSummary() {
    if (!taskSummary) return;
    A.setText("#sum-overdue", taskSummary.overdue ?? 0);
    A.setText("#sum-today", taskSummary.today ?? 0);
    A.setText("#sum-week", taskSummary.next_7_days ?? 0);
    A.setText("#sum-high", taskSummary.high_priority ?? 0);

    const reviewsNode = A.qs("#sum-reviews");
    if (reviewsNode) {
      A.api
        .get("/api/flashcards")
        .then((result) => A.setText("#sum-reviews", (result.due || []).length))
        .catch(() => A.setText("#sum-reviews", "0"));
    }
  }

  function renderTasks() {
    const list = A.qs("#tasks-list");
    if (!list) return;
    A.clear(list);

    const filtered = applyTaskFilters(tasks);
    const grouped = groupTasks(filtered);

    if (!filtered.length) {
      list.append(A.emptyState("Nenhuma pendência nesse filtro."));
      return;
    }

    Object.entries(grouped).forEach(([groupName, items]) => {
      if (!items.length) return;
      list.append(A.el("h3", { className: "list-group-title", text: groupName }));
      items.forEach((task) => list.append(renderTask(task)));
    });
  }

  function applyTaskFilters(sourceTasks) {
    const source = A.qs("#task-source-filter")?.value || "";
    const category = A.qs("#task-category-filter")?.value || "";
    const status = A.qs("#task-status-filter")?.value || "";
    const priority = A.qs("#task-priority-filter")?.value || "";
    const subject = A.qs("#task-subject-filter")?.value || "";
    const search = (A.qs("#task-search")?.value || "").toLowerCase().trim();
    const order = A.qs("#task-order")?.value || "deadline";

    const filtered = sourceTasks.filter((task) => {
      const haystack = `${task.title || ""} ${task.description || ""} ${task.subject || ""} ${task.topic || ""}`.toLowerCase();
      return (
        (!source || task.source === source || task.source_type === source || task.origin === source) &&
        (!category || task.task_category === category) &&
        (!status || normalizeTaskStatus(task.status) === status) &&
        (!priority || task.priority === priority) &&
        (!subject || String(task.subject_id || "") === subject) &&
        (!search || haystack.includes(search))
      );
    });

    filtered.sort((a, b) => compareTasks(a, b, order));
    return filtered;
  }

  function compareTasks(a, b, order) {
    if (order === "priority") {
      const rank = { urgente: 0, alta: 1, média: 2, baixa: 3 };
      return (rank[a.priority] ?? 9) - (rank[b.priority] ?? 9);
    }
    if (order === "duration") {
      return (b.estimated_minutes || 0) - (a.estimated_minutes || 0);
    }

    const ad = parseDateValue(a.deadline || a.due_date);
    const bd = parseDateValue(b.deadline || b.due_date);
    if (!ad && !bd) return 0;
    if (!ad) return 1;
    if (!bd) return -1;
    return ad - bd;
  }

  function groupTasks(filtered) {
    const today = startOfDay(new Date());
    const groups = {
      "Atrasadas": [],
      "Para hoje": [],
      "Próximos dias": [],
      "Concluídas": [],
      "Sem prazo": [],
    };

    filtered.forEach((task) => {
      const status = normalizeTaskStatus(task.status);
      if (status === "completed") {
        groups["Concluídas"].push(task);
        return;
      }
      const due = parseDateValue(task.deadline || task.due_date);
      if (!due) {
        groups["Sem prazo"].push(task);
        return;
      }
      if (due < today) groups["Atrasadas"].push(task);
      else if (sameDay(due, today)) groups["Para hoje"].push(task);
      else groups["Próximos dias"].push(task);
    });

    return groups;
  }

  function renderTask(task) {
    const status = normalizeTaskStatus(task.status);
    const item = A.el("div", { className: "task-item" }, [
      A.el("strong", { text: task.title }),
      A.el("span", { text: `${task.subject || "geral"} · ${task.front || "sem frente"} · ${task.topic || "sem assunto"}` }),
      A.el("small", { text: `Prazo: ${A.formatDate(task.deadline)} · ${task.estimated_minutes} min · ${task.priority} · ${status}` }),
    ]);
    if (task.description) item.append(A.el("p", { className: "muted-text", text: task.description }));

    const actions = A.el("div", { className: "item-actions" });

    const edit = A.el("button", { className: "button ghost", text: "Editar", attrs: { type: "button" } });
    edit.addEventListener("click", () => fillTaskForm(task));

    const complete = A.el("button", { className: "button secondary", text: "Concluir", attrs: { type: "button" } });
    complete.addEventListener("click", () => updateTaskStatus(task.id, "completed"));

    const reschedule = A.el("button", { className: "button ghost", text: "Reagendar", attrs: { type: "button" } });
    reschedule.addEventListener("click", async () => {
      const newDate = window.prompt("Nova data (AAAA-MM-DD):", task.deadline || "");
      if (!newDate) return;
      try {
        await A.api.post(`/api/tasks/${task.id}/reschedule`, { deadline: newDate });
        A.toast("Pendência reagendada.");
        await loadTasks();
      } catch (error) {
        A.toast(error.message, "error");
      }
    });

    const remove = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
    remove.addEventListener("click", async () => {
      if (!window.confirm("Tem certeza que deseja excluir esta pendência?")) return;
      try {
        await A.api.delete(`/api/tasks/${task.id}`);
        A.toast("Pendência removida.");
        await loadTasks();
      } catch (error) {
        A.toast(error.message, "error");
      }
    });

    actions.append(edit, complete, reschedule, remove);
    item.append(actions);
    return item;
  }

  function fillTaskForm(task) {
    const form = A.qs("#task-form");
    A.fillForm(form, task);
    loadFrontsForSubject(task.subject_id, task.front_id, task.topic_id).catch(() => {});
  }

  async function updateTaskStatus(taskId, status) {
    await A.api.post(`/api/tasks/${taskId}/status`, { status });
    A.toast("Status atualizado.");
    await loadTasks();
  }

  function bindTaskForm() {
    const form = A.qs("#task-form");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = A.formToObject(form);
      const id = payload.id;
      delete payload.id;
      if (id) await A.api.put(`/api/tasks/${id}`, payload);
      else await A.api.post("/api/tasks", payload);
      form.reset();
      A.toast("Pendência salva.");
      await loadTasks();
    });

    A.qs("#task-form-reset")?.addEventListener("click", () => {
      form.reset();
      A.qs("input[name='id']", form).value = "";
    });

    A.qsa("#task-source-filter, #task-category-filter, #task-status-filter, #task-priority-filter, #task-subject-filter, #task-order").forEach((filter) => filter.addEventListener("change", renderTasks));
    A.qs("#task-search")?.addEventListener("input", renderTasks);

    A.qs("#task-subject-select")?.addEventListener("change", async (event) => {
      const value = event.target.value;
      await loadFrontsForSubject(value, null, null);
    });

    loadTaskSubjects().catch(() => {});
  }

  async function loadTaskSubjects() {
    const select = A.qs("#task-subject-select");
    const filterSelect = A.qs("#task-subject-filter");
    const data = await A.api.get("/api/subjects");

    if (select) {
      select.innerHTML = "";
      select.append(A.el("option", { text: "Sem matéria vinculada", attrs: { value: "" } }));
    }
    if (filterSelect) {
      filterSelect.innerHTML = "";
      filterSelect.append(A.el("option", { text: "Todas as matérias", attrs: { value: "" } }));
    }

    data.subjects.forEach((subject) => {
      if (select) select.append(A.el("option", { text: subject.name, attrs: { value: subject.id } }));
      if (filterSelect) filterSelect.append(A.el("option", { text: subject.name, attrs: { value: subject.id } }));
    });
  }

  async function loadFrontsForSubject(subjectId, selectedFront, selectedTopic) {
    const frontSelect = A.qs("#task-front-select");
    const topicSelect = A.qs("#task-topic-select");
    if (!frontSelect || !topicSelect) return;

    frontSelect.innerHTML = "";
    topicSelect.innerHTML = "";
    frontSelect.append(A.el("option", { text: "Sem frente", attrs: { value: "" } }));
    topicSelect.append(A.el("option", { text: "Sem assunto", attrs: { value: "" } }));

    if (!subjectId) return;

    const data = await A.api.get(`/api/subjects/${subjectId}`);
    (data.subject.fronts || []).forEach((front) => {
      frontSelect.append(A.el("option", { text: front.name, attrs: { value: front.id } }));
    });

    (data.subject.topics || []).forEach((topic) => {
      topicSelect.append(A.el("option", { text: topic.name, attrs: { value: topic.id } }));
    });

    if (selectedFront) frontSelect.value = String(selectedFront);
    if (selectedTopic) topicSelect.value = String(selectedTopic);
  }

  async function loadCalendar() {
    const data = await A.api.get("/api/calendar");
    events = data.items || data.events || [];
    renderCalendar();
    const google = A.qs("#google-calendar-status");
    if (google && data.google) A.setText("#google-calendar-status", data.google.message);
  }

  function renderCalendar() {
    const list = A.qs("#calendar-list");
    if (!list) return;
    A.clear(list);

    const filter = A.qs("#calendar-filter")?.value || "";
    const filtered = events.filter((event) => !filter || event.event_type === filter);

    const groups = calendarView === "week" ? groupEventsByWeekday(filtered) : groupEventsByMonthDay(filtered);
    if (!groups.length) {
      list.append(A.emptyState("Nenhum evento cadastrado."));
      return;
    }

    groups.forEach((group) => {
      list.append(A.el("h3", { className: "list-group-title", text: group.label }));
      group.items.forEach((event) => {
        const item = A.el("div", { className: "timeline-item" }, [
          A.el("strong", { text: event.title }),
          A.el("span", { text: `${event.event_type} · ${A.formatDateTime(event.start_datetime)}` }),
          A.el("small", { text: event.status || "pendente" }),
        ]);
        const actions = A.el("div", { className: "item-actions" });
        const edit = A.el("button", { className: "button ghost", text: "Editar", attrs: { type: "button" } });
        edit.addEventListener("click", () => fillCalendarForm(event));
        actions.append(edit);

        if (event.source === "calendar" || typeof event.id === "number") {
          const remove = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
          remove.addEventListener("click", () => deleteCalendarEvent(event.id));
          actions.append(remove);
        }

        item.append(actions);
        list.append(item);
      });
    });
  }

  function groupEventsByWeekday(items) {
    const map = new Map();
    items.forEach((item) => {
      const d = new Date(item.start_datetime);
      const weekday = Number.isNaN(d.getTime()) ? -1 : ((d.getDay() + 6) % 7);
      const label = weekday >= 0 ? DAY_LABELS[weekday] : "Sem data";
      if (!map.has(label)) map.set(label, []);
      map.get(label).push(item);
    });
    return Array.from(map.entries()).map(([label, list]) => ({ label, items: list.sort((a, b) => (a.start_datetime || "").localeCompare(b.start_datetime || "")) }));
  }

  function groupEventsByMonthDay(items) {
    const map = new Map();
    items.forEach((item) => {
      const date = A.formatDate(item.start_datetime);
      if (!map.has(date)) map.set(date, []);
      map.get(date).push(item);
    });
    return Array.from(map.entries()).map(([label, list]) => ({ label, items: list.sort((a, b) => (a.start_datetime || "").localeCompare(b.start_datetime || "")) }));
  }

  function fillCalendarForm(event) {
    const form = A.qs("#calendar-form");
    const data = { ...event };
    data.start_datetime = event.start_datetime ? event.start_datetime.slice(0, 16) : "";
    data.end_datetime = event.end_datetime ? event.end_datetime.slice(0, 16) : "";
    A.fillForm(form, data);
  }

  async function deleteCalendarEvent(id) {
    if (!window.confirm("Tem certeza que deseja excluir este evento?")) return;
    await A.api.delete(`/api/calendar/${id}`);
    A.toast("Evento removido.");
    await loadCalendar();
  }

  function bindCalendarForm() {
    const form = A.qs("#calendar-form");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = A.formToObject(form);
      const id = payload.id;
      delete payload.id;
      if (id) await A.api.put(`/api/calendar/${id}`, payload);
      else await A.api.post("/api/calendar", payload);
      form.reset();
      A.toast("Evento salvo.");
      await loadCalendar();
    });

    A.qs("#calendar-filter")?.addEventListener("change", renderCalendar);

    A.qsa("[data-calendar-view]").forEach((button) => {
      button.addEventListener("click", () => {
        calendarView = button.dataset.calendarView;
        A.qsa("[data-calendar-view]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        renderCalendar();
      });
    });
  }

  async function loadReport() {
    const report = await A.api.get("/api/reports/weekly");
    renderReport(report);
  }

  function renderReport(report) {
    const grid = A.qs("#weekly-report");
    if (!grid) return;
    A.clear(grid);
    const items = [
      ["Tarefas concluídas", report.completed_tasks],
      ["Tarefas atrasadas", report.delayed_tasks],
      ["Horas planejadas", Math.round(report.planned_minutes / 60)],
      ["Horas realizadas", Math.round(report.completed_minutes / 60)],
      ["Matéria mais estudada", report.most_studied_subject],
      ["Matéria com mais pendências", report.weakest_subjects.length ? report.weakest_subjects[0] : "sem sinal suficiente"],
      ["Revisões concluídas", report.revision_total],
      ["Evolução de redação", report.essay_count],
      ["Evolução de simulados", report.exam_count],
      ["Risco de sobrecarga", report.overload.level],
      ["Foco recomendado", report.recommended_focus],
    ];
    items.forEach(([label, value]) => {
      grid.append(A.el("div", { className: "report-metric" }, [A.el("small", { text: label }), A.el("strong", { text: String(value) })]));
    });
  }

  function bindReports() {
    A.qs("#generate-report")?.addEventListener("click", async () => {
      const result = await A.api.post("/api/reports/generate", {});
      A.toast(result.message);
      renderReport(result.report);
    });
    A.qs("#print-report")?.addEventListener("click", () => window.print());
  }

  function normalizeTaskStatus(value) {
    const status = String(value || "").toLowerCase();
    if (["completed", "concluída"].includes(status)) return "completed";
    if (["late", "atrasada"].includes(status)) return "late";
    if (["rescheduled", "reagendada"].includes(status)) return "rescheduled";
    return "pending";
  }

  function parseDateValue(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return startOfDay(date);
  }

  function startOfDay(date) {
    const d = new Date(date.getTime());
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindQuickActions();
    const page = document.body.dataset.page;

    if (page === "pending") {
      bindTaskForm();
      loadTasks().catch((error) => A.toast(error.message, "error"));
    }

    if (page === "calendar") {
      bindCalendarForm();
      loadCalendar().catch((error) => A.toast(error.message, "error"));
    }

    if (page === "reports") {
      bindReports();
      loadReport().catch((error) => A.toast(error.message, "error"));
    }
  });
})();
