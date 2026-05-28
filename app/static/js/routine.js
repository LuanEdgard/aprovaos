(function () {
  const A = window.AprovaOS;
  const days = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
  const typeColors = {
    school: "#60a5fa",
    course: "#34d399",
    study_window: "#f59e0b",
    transport: "#a78bfa",
    work: "#f87171",
    rest: "#94a3b8",
    personal: "#22d3ee",
    sleep: "#64748b",
    other: "#9ca3af",
  };

  let blocks = [];
  let plannerSuggestions = [];

  async function loadRoutine() {
    const data = await A.api.get("/api/routine");
    blocks = data.blocks || [];
    renderWeek();
    renderTable();
  }

  async function loadProfile() {
    const data = await A.api.get("/api/routine/profile");
    const form = A.qs("#routine-profile-form");
    if (form) A.fillForm(form, data.profile || {});
  }

  function renderWeek() {
    const board = A.qs("#routine-week");
    if (!board) return;
    A.clear(board);

    days.forEach((day, index) => {
      const column = A.el("div", { className: "week-day" }, [A.el("h3", { text: day })]);
      const dayBlocks = blocks.filter((block) => Number(block.weekday) === index);
      if (!dayBlocks.length) {
        column.append(A.emptyState("sem bloco"));
      }

      dayBlocks.forEach((block) => {
        const duration = formatDuration(block.start_time, block.end_time);
        const item = A.el("div", { className: "task-item" }, [
          A.el("strong", { text: block.title }),
          A.el("span", { text: `${block.start_time} às ${block.end_time} · ${duration}` }),
          A.el("small", { text: block.block_type }),
        ]);
        item.style.borderLeft = `4px solid ${typeColors[block.block_type] || typeColors.other}`;

        const actions = A.el("div", { className: "item-actions" });
        const edit = A.el("button", { className: "button ghost", text: "Editar", attrs: { type: "button" } });
        edit.addEventListener("click", () => fillRoutineForm(block));

        const duplicate = A.el("button", { className: "button ghost", text: "Duplicar", attrs: { type: "button" } });
        duplicate.addEventListener("click", () => duplicateBlock(block.id));

        const remove = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
        remove.addEventListener("click", () => removeBlock(block.id));

        actions.append(edit, duplicate, remove);
        item.append(actions);
        column.append(item);
      });
      board.append(column);
    });
  }

  function renderTable() {
    const body = A.qs("#routine-table-body");
    if (!body) return;
    A.clear(body);

    if (!blocks.length) {
      const row = A.el("tr", {}, [
        A.el("td", { attrs: { colspan: 7 } }, [A.emptyState("Cadastre blocos para montar a visão semanal.")]),
      ]);
      body.append(row);
      return;
    }

    blocks
      .slice()
      .sort((a, b) => Number(a.weekday) - Number(b.weekday) || String(a.start_time).localeCompare(String(b.start_time)))
      .forEach((block) => {
        const tr = document.createElement("tr");
        tr.append(
          cell(days[Number(block.weekday)] || "-"),
          cell(block.start_time),
          cell(block.end_time),
          cell(block.block_type),
          cell(block.title),
          cell(block.description || "-"),
          actionCell(block)
        );
        body.append(tr);
      });
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function actionCell(block) {
    const td = document.createElement("td");
    const wrap = A.el("div", { className: "item-actions" });

    const edit = A.el("button", { className: "button ghost", text: "Editar", attrs: { type: "button" } });
    edit.addEventListener("click", () => fillRoutineForm(block));

    const duplicate = A.el("button", { className: "button ghost", text: "Duplicar", attrs: { type: "button" } });
    duplicate.addEventListener("click", () => duplicateBlock(block.id));

    const remove = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
    remove.addEventListener("click", () => removeBlock(block.id));

    wrap.append(edit, duplicate, remove);
    td.append(wrap);
    return td;
  }

  function fillRoutineForm(block) {
    const form = A.qs("#routine-form");
    A.fillForm(form, block);
  }

  async function duplicateBlock(blockId) {
    const raw = window.prompt("Duplicar para quais dias? (0-6 separados por vírgula)", "1,2,3,4");
    if (!raw) return;
    const weekdays = raw
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((value) => Number.isInteger(value) && value >= 0 && value <= 6);

    if (!weekdays.length) {
      A.toast("Informe ao menos um dia válido entre 0 e 6.", "error");
      return;
    }

    await A.api.post(`/api/routine/blocks/${blockId}/duplicate`, { weekdays });
    A.toast("Bloco duplicado.");
    await loadRoutine();
  }

  async function removeBlock(id) {
    if (!window.confirm("Tem certeza que deseja excluir este bloco?")) return;
    await A.api.delete(`/api/routine/blocks/${id}`);
    A.toast("Bloco removido.");
    await loadRoutine();
  }

  function bindForm() {
    const form = A.qs("#routine-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = A.formToObject(form);
      const id = payload.id;
      delete payload.id;
      if (id) await A.api.put(`/api/routine/blocks/${id}`, payload);
      else await A.api.post("/api/routine", payload);
      form.reset();
      A.toast("Rotina salva.");
      await loadRoutine();
    });
  }

  function bindProfileForm() {
    const form = A.qs("#routine-profile-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.put("/api/routine/profile", A.formToObject(form));
      A.toast("Perfil de rotina salvo.");
      await loadProfile();
    });
  }

  function bindPlannerForm() {
    const form = A.qs("#routine-planner-form");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = A.formToObject(form);
      const result = await A.api.post("/api/routine/planner/preview", payload);
      plannerSuggestions = result.suggestions || [];
      renderPlannerPreview(result.message || "Sugestão gerada.");
    });

    A.qs("#routine-planner-confirm")?.addEventListener("click", async () => {
      if (!plannerSuggestions.length) return;
      await A.api.post("/api/routine/planner/confirm", { suggestions: plannerSuggestions });
      A.toast("Sugestão aplicada na rotina.");
      clearPlannerPreview();
      await loadRoutine();
    });

    A.qs("#routine-planner-cancel")?.addEventListener("click", clearPlannerPreview);
  }

  function renderPlannerPreview(message) {
    const root = A.qs("#routine-planner-preview");
    A.clear(root);

    if (!plannerSuggestions.length) {
      root.append(A.emptyState(message));
      togglePlannerButtons(false);
      return;
    }

    plannerSuggestions.forEach((item) => {
      root.append(
        A.el("div", { className: "task-item" }, [
          A.el("strong", { text: `${days[Number(item.weekday)]} · ${item.title}` }),
          A.el("span", { text: `${item.start_time} às ${item.end_time} · ${item.block_type}` }),
          A.el("small", { text: item.description || "" }),
        ])
      );
    });
    togglePlannerButtons(true);
  }

  function togglePlannerButtons(show) {
    A.qs("#routine-planner-confirm")?.classList.toggle("hidden", !show);
    A.qs("#routine-planner-cancel")?.classList.toggle("hidden", !show);
  }

  function clearPlannerPreview() {
    plannerSuggestions = [];
    const root = A.qs("#routine-planner-preview");
    if (root) A.clear(root);
    togglePlannerButtons(false);
  }

  function formatDuration(start, end) {
    if (!start || !end) return "";
    const [sh, sm] = String(start).split(":").map(Number);
    const [eh, em] = String(end).split(":").map(Number);
    const total = Math.max(0, (eh * 60 + em) - (sh * 60 + sm));
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    if (!hours) return `${minutes} min`;
    if (!minutes) return `${hours}h`;
    return `${hours}h${String(minutes).padStart(2, "0")}`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "routine") {
      bindForm();
      bindProfileForm();
      bindPlannerForm();
      loadRoutine().catch((error) => A.toast(error.message, "error"));
      loadProfile().catch((error) => A.toast(error.message, "error"));
    }
  });
})();

