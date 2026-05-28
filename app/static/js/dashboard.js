(function () {
  const A = window.AprovaOS;
  let dashboardData = null;
  let todayView = "list";

  async function loadDashboard() {
    dashboardData = await A.api.get("/api/dashboard/summary");
    renderSummary(dashboardData);
  }

  function renderSummary(data) {
    A.setText("#weekly-priority", data.weekly_priority);
    A.setText("#pending-count", data.pending_count);
    A.setText("#overdue-count", `${data.overdue_count} atrasadas`);
    A.setText("#revision-count", data.revision_count);
    A.setText("#next-exam", data.next_exam ? data.next_exam.title : "Sem evento");
    A.setText("#next-essay", data.next_essay ? data.next_essay.theme : "Sem registro");
    A.setText("#next-focus", data.next_focus);
    A.setText("#overload-warning", data.overload.warning);

    renderList(data.today_plan || []);
    renderKanban(data.kanban || {});
    renderTimeline(data.timeline || []);
    renderUpcoming(data.upcoming_tasks || []);
    renderDueFlashcards(data.due_flashcards || []);

    const progress = data.week_progress.total ? Math.round((data.week_progress.completed / data.week_progress.total) * 100) : 0;
    const bar = A.qs("#week-progress-bar");
    if (bar) bar.style.width = `${Math.min(progress, 100)}%`;
    A.setText("#week-progress-text", `${data.week_progress.completed} de ${data.week_progress.total} tarefas concluídas`);

    const subjects = A.qs("#risk-subjects");
    A.clear(subjects);
    if (!data.risk_subjects.length) {
      subjects.append(A.emptyState("Sem matéria em risco detectada ainda."));
    } else {
      data.risk_subjects.forEach((subject) => subjects.append(A.el("span", { className: "badge", text: subject })));
    }

    A.renderChart("study-load-chart", "bar", ["Planejada", "Realizada"], [
      {
        label: "Minutos",
        data: [data.study_load.planned_minutes, data.study_load.completed_minutes],
        backgroundColor: ["#3b82f6", "#2dd4bf"],
      },
    ]);
  }

  function renderList(tasks) {
    const plan = A.qs("#today-plan");
    if (!plan) return;
    A.clear(plan);
    if (!tasks.length) {
      plan.append(A.emptyState("Cadastre pendências para montar o foco do dia."));
      return;
    }
    tasks.forEach((task) => plan.append(taskItem(task, true)));
  }

  function renderKanban(kanban) {
    fillKanbanColumn("#kanban-today", kanban.today || []);
    fillKanbanColumn("#kanban-progress", kanban.in_progress || []);
    fillKanbanColumn("#kanban-overdue", kanban.overdue || []);
    fillKanbanColumn("#kanban-done", kanban.completed || []);
  }

  function fillKanbanColumn(selector, tasks) {
    const list = A.qs(selector);
    if (!list) return;
    A.clear(list);
    if (!tasks.length) {
      list.append(A.emptyState("Sem itens"));
      return;
    }
    tasks.forEach((task) => list.append(taskItem(task, false)));
  }

  function renderTimeline(items) {
    const root = A.qs("#today-timeline");
    if (!root) return;
    A.clear(root);
    if (!items.length) {
      root.append(A.emptyState("Sem linha do tempo para hoje."));
      return;
    }
    items.forEach((item) => {
      root.append(
        A.el("div", { className: "timeline-item" }, [
          A.el("strong", { text: `${item.start_time || "--:--"} - ${item.end_time || "--:--"}` }),
          A.el("span", { text: item.title }),
          A.el("small", { text: item.kind === "free" ? "janela livre" : item.type || "estudo" }),
        ])
      );
    });
  }

  function renderUpcoming(tasks) {
    const root = A.qs("#upcoming-tasks");
    if (!root) return;
    A.clear(root);
    if (!tasks.length) {
      root.append(A.emptyState("Sem próximas pendências na semana."));
      return;
    }
    tasks.forEach((task) => {
      root.append(
        A.el("div", { className: "list-item" }, [
          A.el("strong", { text: task.title }),
          A.el("small", { text: `${task.subject || "geral"} · prazo ${A.formatDate(task.deadline)}` }),
        ])
      );
    });
  }

  function renderDueFlashcards(cards) {
    const root = A.qs("#due-flashcards");
    if (!root) return;
    A.clear(root);
    if (!cards.length) {
      root.append(A.emptyState("Nenhuma revisão vencida agora."));
      return;
    }
    cards.forEach((card) => {
      root.append(
        A.el("div", { className: "list-item" }, [
          A.el("strong", { text: card.front }),
          A.el("small", { text: `${card.subject || "geral"} · ${card.topic || "sem assunto"}` }),
        ])
      );
    });
  }

  function taskItem(task, showDescription) {
    const container = A.el("div", { className: "task-item" }, [
      A.el("strong", { text: task.title }),
      A.el("span", { text: `${task.subject || "geral"} · ${task.front || "sem frente"} · ${task.topic || "sem assunto"}` }),
      A.el("small", { text: `Prazo: ${A.formatDate(task.deadline)} · Prioridade: ${task.priority}` }),
    ]);

    if (showDescription && task.description) {
      container.append(A.el("p", { className: "muted-text", text: task.description }));
    }

    const actions = A.el("div", { className: "item-actions" });
    const statusSelect = A.el("select", { attrs: { "aria-label": "Mudar status" } });
    [
      ["pending", "Pendente"],
      ["rescheduled", "Em andamento"],
      ["late", "Atrasado"],
      ["completed", "Concluído"],
    ].forEach(([value, label]) => {
      statusSelect.append(A.el("option", { text: label, attrs: { value } }));
    });
    statusSelect.value = normalizeStatus(task.status);
    statusSelect.addEventListener("change", () => changeStatus(task.id, statusSelect.value));

    const doneButton = A.el("button", { className: "button secondary", text: "Concluir", attrs: { type: "button" } });
    doneButton.addEventListener("click", () => changeStatus(task.id, "completed"));

    actions.append(statusSelect, doneButton);
    container.append(actions);
    return container;
  }

  function normalizeStatus(status) {
    const value = String(status || "pending").toLowerCase();
    if (["completed", "concluída"].includes(value)) return "completed";
    if (["late", "atrasada"].includes(value)) return "late";
    if (["rescheduled", "reagendada"].includes(value)) return "rescheduled";
    return "pending";
  }

  async function changeStatus(taskId, status) {
    try {
      await A.api.post(`/api/tasks/${taskId}/status`, { status });
      await loadDashboard();
    } catch (error) {
      A.toast(error.message, "error");
    }
  }

  function bindViewToggle() {
    A.qsa("[data-today-view]").forEach((button) => {
      button.addEventListener("click", () => {
        todayView = button.dataset.todayView;
        A.qsa("[data-today-view]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        switchView(todayView);
      });
    });
    switchView(todayView);
  }

  function switchView(view) {
    const list = A.qs("#today-plan");
    const kanban = A.qs("#today-kanban");
    const timeline = A.qs("#today-timeline");
    if (list) list.classList.toggle("hidden", view !== "list");
    if (kanban) kanban.classList.toggle("hidden", view !== "kanban");
    if (timeline) timeline.classList.toggle("hidden", view !== "timeline");
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "dashboard") {
      bindViewToggle();
      loadDashboard().catch((error) => A.toast(error.message, "error"));
    }
  });
})();
