(function () {
  const A = window.AprovaOS;

  async function loadSubjects() {
    const data = await A.api.get("/api/subjects");
    const list = A.qs("#subjects-list");
    if (!list) return;
    A.clear(list);

    if (!data.subjects.length) {
      list.append(A.emptyState("Nenhuma matéria cadastrada ainda."));
      return;
    }

    data.subjects.forEach((subject) => {
      const card = A.el("a", { className: "subject-card", attrs: { href: `/app/subjects/${subject.id}` } }, [
        A.el("span", { className: "subject-dot", attrs: { style: `background:${subject.color}` } }),
        A.el("strong", { text: subject.name }),
        A.el("small", { text: `${subject.area} · ${subject.material_count} materiais · ${subject.task_count} pendências` }),
      ]);
      list.append(card);
    });
  }

  async function loadSubjectDetail() {
    const root = A.qs("[data-subject-id]");
    if (!root) return;

    const data = await A.api.get(`/api/subjects/${root.dataset.subjectId}`);
    const subject = data.subject;

    renderOverview(subject);
    renderFrontsAndTopics(subject);
    fillTopicFrontSelect(subject.fronts || []);
    fillList("#subject-materials", subject.materials, (item) => `${item.title} · ${item.topic || "sem tópico"} · ${item.source || "sem origem"}`);
    fillList("#subject-decks", subject.decks, (item) => `${item.name || item.title}`);
    fillList("#subject-tasks", subject.tasks, (item) => `${item.title} · ${item.status} · ${item.priority}`);

    const progress = subject.progress || {};
    A.setText(
      "#subject-progress",
      `Assuntos concluídos: ${progress.completed_topics || 0}/${progress.total_topics || 0} (${progress.topic_progress || 0}%). Pendências concluídas: ${progress.completed_tasks || 0}/${progress.total_tasks || 0} (${progress.task_progress || 0}%). Flashcards vinculados: ${progress.flashcards || 0}.`
    );
    A.setText("#subject-insight", subject.ai_insight || "Sem recomendação no momento.");
  }

  function renderOverview(subject) {
    const overview = A.qs("#subject-overview");
    if (!overview) return;
    A.clear(overview);
    overview.append(
      A.el("span", { className: "subject-dot large", attrs: { style: `background:${subject.color}` } }),
      A.el("div", {}, [
        A.el("p", { className: "eyebrow", text: subject.area }),
        A.el("h2", { text: subject.name }),
        A.el("p", { className: "muted-text", text: subject.description || "Organize materiais, flashcards e pendências desta matéria." }),
      ])
    );
  }

  function renderFrontsAndTopics(subject) {
    const root = A.qs("#subject-fronts");
    if (!root) return;
    A.clear(root);

    const fronts = subject.fronts || [];
    const topics = subject.topics || [];

    if (!fronts.length && !topics.length) {
      root.append(A.emptyState("Cadastre frentes e assuntos para destravar recomendações melhores."));
      return;
    }

    fronts.forEach((front) => {
      const card = A.el("div", { className: "list-item" }, [
        A.el("strong", { text: front.name }),
        A.el("small", { text: front.description || "Sem descrição" }),
      ]);

      const frontActions = A.el("div", { className: "item-actions" });
      const editFront = A.el("button", { className: "button ghost", text: "Editar", attrs: { type: "button" } });
      editFront.addEventListener("click", () => editFrontPrompt(subject.id, front));

      const deleteFront = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
      deleteFront.addEventListener("click", () => deleteFrontById(subject.id, front.id));

      frontActions.append(editFront, deleteFront);
      card.append(frontActions);

      const frontTopics = topics.filter((topic) => Number(topic.front_id || 0) === Number(front.id));
      if (!frontTopics.length) {
        card.append(A.emptyState("Sem assuntos nesta frente."));
      } else {
        frontTopics.forEach((topic) => {
          const topicItem = A.el("div", { className: "task-item" }, [
            A.el("strong", { text: topic.name }),
            A.el("small", { text: `${topic.status} · dificuldade ${topic.difficulty}` }),
          ]);
          const topicActions = A.el("div", { className: "item-actions" });
          const editTopic = A.el("button", { className: "button ghost", text: "Editar", attrs: { type: "button" } });
          editTopic.addEventListener("click", () => editTopicPrompt(subject.id, topic));
          const deleteTopic = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
          deleteTopic.addEventListener("click", () => deleteTopicById(subject.id, topic.id));
          topicActions.append(editTopic, deleteTopic);
          topicItem.append(topicActions);
          card.append(topicItem);
        });
      }

      root.append(card);
    });

    const detachedTopics = topics.filter((topic) => !topic.front_id);
    if (detachedTopics.length) {
      const freeCard = A.el("div", { className: "list-item" }, [A.el("strong", { text: "Assuntos sem frente" })]);
      detachedTopics.forEach((topic) => freeCard.append(A.el("small", { text: `${topic.name} · ${topic.status} · ${topic.difficulty}` })));
      root.append(freeCard);
    }
  }

  function fillTopicFrontSelect(fronts) {
    const select = A.qs("#topic-front-select");
    if (!select) return;
    A.clear(select);
    select.append(A.el("option", { text: "Sem frente", attrs: { value: "" } }));
    fronts.forEach((front) => {
      select.append(A.el("option", { text: front.name, attrs: { value: front.id } }));
    });
  }

  function fillList(selector, items, formatter) {
    const list = A.qs(selector);
    if (!list) return;
    A.clear(list);
    if (!items.length) {
      list.append(A.emptyState("Nada conectado ainda."));
      return;
    }
    items.forEach((item) => list.append(A.el("div", { className: "list-item" }, [A.el("span", { text: formatter(item) })])));
  }

  function bindSubjectForm() {
    const form = A.qs("#subject-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.post("/api/subjects", A.formToObject(form));
      A.toast("Matéria salva.");
      form.reset();
      await loadSubjects();
    });

    A.qs("#seed-subjects")?.addEventListener("click", async () => {
      await loadSubjects();
      A.toast("Matérias padrão verificadas.");
    });
  }

  function bindDetailForms() {
    const root = A.qs("[data-subject-id]");
    if (!root) return;
    const subjectId = root.dataset.subjectId;

    const frontForm = A.qs("#front-form");
    frontForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.post(`/api/subjects/${subjectId}/fronts`, A.formToObject(frontForm));
      A.toast("Frente cadastrada.");
      frontForm.reset();
      await loadSubjectDetail();
    });

    const topicForm = A.qs("#topic-form");
    topicForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.post(`/api/subjects/${subjectId}/topics`, A.formToObject(topicForm));
      A.toast("Assunto cadastrado.");
      topicForm.reset();
      await loadSubjectDetail();
    });
  }

  async function editFrontPrompt(subjectId, front) {
    const name = window.prompt("Novo nome da frente:", front.name);
    if (!name) return;
    const description = window.prompt("Descrição da frente:", front.description || "") || "";
    await A.api.put(`/api/subjects/${subjectId}/fronts/${front.id}`, {
      name,
      description,
      order: Number(front.order || 0),
    });
    A.toast("Frente atualizada.");
    await loadSubjectDetail();
  }

  async function deleteFrontById(subjectId, frontId) {
    if (!window.confirm("Excluir esta frente e os assuntos vinculados?")) return;
    await A.api.delete(`/api/subjects/${subjectId}/fronts/${frontId}`);
    A.toast("Frente removida.");
    await loadSubjectDetail();
  }

  async function editTopicPrompt(subjectId, topic) {
    const name = window.prompt("Novo nome do assunto:", topic.name);
    if (!name) return;
    const status = window.prompt("Status (nao_iniciado, em_andamento, concluido, revisar):", topic.status || "nao_iniciado") || "nao_iniciado";
    const difficulty = window.prompt("Dificuldade (baixa, media, alta):", topic.difficulty || "media") || "media";
    await A.api.put(`/api/subjects/${subjectId}/topics/${topic.id}`, {
      name,
      front_id: topic.front_id,
      description: topic.description || "",
      status,
      difficulty,
      order: Number(topic.order || 0),
    });
    A.toast("Assunto atualizado.");
    await loadSubjectDetail();
  }

  async function deleteTopicById(subjectId, topicId) {
    if (!window.confirm("Excluir este assunto?")) return;
    await A.api.delete(`/api/subjects/${subjectId}/topics/${topicId}`);
    A.toast("Assunto removido.");
    await loadSubjectDetail();
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "subjects") {
      bindSubjectForm();
      bindDetailForms();
      loadSubjects().catch((error) => A.toast(error.message, "error"));
      loadSubjectDetail().catch((error) => A.toast(error.message, "error"));
    }
  });
})();
