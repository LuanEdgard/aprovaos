(function () {
  const A = window.AprovaOS;
  let due = [];
  let cards = [];
  let decks = [];
  let generatedDraftCards = [];
  let currentIndex = 0;
  let revealed = false;

  async function loadFlashcards() {
    const params = buildFilterParams();
    const query = new URLSearchParams(params).toString();
    const data = await A.api.get(`/api/flashcards${query ? `?${query}` : ""}`);

    due = data.due || [];
    cards = data.cards || [];
    decks = data.decks || [];
    currentIndex = 0;
    revealed = false;

    renderDeckSummary();
    renderReview();
    renderList();
    fillDeckFilter();
  }

  function buildFilterParams() {
    const params = {};
    const deckId = A.qs("#filter-deck")?.value;
    const subjectId = A.qs("#filter-subject")?.value;
    const frontId = A.qs("#filter-front")?.value;
    const topicId = A.qs("#filter-topic")?.value;
    const tag = A.qs("#filter-tag")?.value?.trim();
    const dueToday = A.qs("#filter-due-today")?.checked;

    if (deckId) params.deck_id = deckId;
    if (subjectId) params.subject_id = subjectId;
    if (frontId) params.front_id = frontId;
    if (topicId) params.topic_id = topicId;
    if (tag) params.tag = tag;
    if (dueToday) params.due_today = "true";
    return params;
  }

  function renderDeckSummary() {
    const root = A.qs("#deck-summary");
    if (!root) return;
    A.clear(root);

    if (!decks.length) {
      root.append(A.el("article", { className: "card summary-item" }, [A.el("small", { text: "Baralhos" }), A.el("strong", { text: "0" })]));
      return;
    }

    decks.slice(0, 6).forEach((deck) => {
      root.append(
        A.el("article", { className: "card summary-item" }, [
          A.el("small", { text: deck.name || deck.title }),
          A.el("strong", { text: `${deck.total_cards || 0} cartões` }),
          A.el("span", { className: "muted-text", text: `${deck.due_cards || 0} vencidos · ${deck.new_cards || 0} novos` }),
        ])
      );
    });
  }

  function renderReview() {
    A.setText("#due-count", `${due.length} cartões`);
    const area = A.qs("#review-area");
    if (!area) return;
    A.clear(area);

    const card = due[currentIndex];
    if (!card) {
      area.append(A.emptyState("Nenhum flashcard vencido agora. Crie cartões ou volte depois da próxima revisão."));
      return;
    }

    area.append(A.el("p", { className: "review-question", text: revealed ? card.back : card.front }));
    area.append(A.el("small", { text: `${card.subject || "geral"} · ${card.topic || "sem assunto"}` }));

    const actions = A.el("div", { className: "answer-actions" });
    if (!revealed) {
      const reveal = A.el("button", { className: "button primary", text: "Mostrar resposta", attrs: { type: "button" } });
      reveal.addEventListener("click", () => {
        revealed = true;
        renderReview();
      });
      actions.append(reveal);
    } else {
      ["Errei", "Difícil", "Médio", "Fácil"].forEach((quality) => {
        const button = A.el("button", { className: "button secondary", text: quality, attrs: { type: "button" } });
        button.addEventListener("click", () => submitReview(card.id, quality));
        actions.append(button);
      });
    }
    area.append(actions);
  }

  async function submitReview(id, answer_quality) {
    await A.api.post(`/api/flashcards/${id}/review`, { answer_quality });
    A.toast("Revisão registrada.");
    await loadFlashcards();
  }

  function renderList() {
    const list = A.qs("#flashcard-list");
    if (!list) return;
    A.clear(list);

    if (!cards.length) {
      list.append(A.emptyState("Nenhum flashcard criado."));
      return;
    }

    cards.forEach((card) => {
      const item = A.el("div", { className: "list-item" }, [
        A.el("strong", { text: card.front }),
        A.el("span", { text: card.back }),
        A.el("small", { text: `${card.tag || card.subject || "sem tag"} · próxima revisão: ${A.formatDate(card.next_review_at)} · repetições: ${card.repetitions || 0}` }),
      ]);

      const actions = A.el("div", { className: "item-actions" });
      const remove = A.el("button", { className: "button ghost", text: "Excluir", attrs: { type: "button" } });
      remove.addEventListener("click", () => deleteCard(card.id));
      actions.append(remove);

      item.append(actions);
      list.append(item);
    });
  }

  async function deleteCard(cardId) {
    if (!window.confirm("Excluir este flashcard?")) return;
    await A.api.delete(`/api/flashcards/${cardId}`);
    A.toast("Flashcard removido.");
    await loadFlashcards();
  }

  function bindForm() {
    const form = A.qs("#flashcard-form");
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.post("/api/flashcards", A.formToObject(form));
      A.toast("Flashcard criado.");
      form.reset();
      await loadFlashcards();
    });

    const uploadForm = A.qs("#flashcard-upload-form");
    uploadForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(uploadForm);
      const result = await A.api.post("/api/flashcards/upload", data);
      A.toast(result.message || "Flashcards gerados.");
      uploadForm.reset();
      await loadFlashcards();
    });

    const textForm = A.qs("#flashcard-text-generator-form");
    textForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = A.formToObject(textForm);
      generatedDraftCards = generateDraftCardsFromText(payload.text || "");
      renderGeneratedDraft(generatedDraftCards);
    });

    loadSubjects().catch(() => {});
    bindFilters();
  }

  function bindFilters() {
    A.qsa("#filter-deck, #filter-subject, #filter-front, #filter-topic").forEach((node) => {
      node.addEventListener("change", async () => {
        if (node.id === "filter-subject") {
          await fillFrontAndTopicFilters(node.value);
        }
        await loadFlashcards();
      });
    });

    A.qs("#filter-tag")?.addEventListener("input", debounce(loadFlashcards, 250));
    A.qs("#filter-due-today")?.addEventListener("change", loadFlashcards);

    A.qs("#flashcard-subject-select")?.addEventListener("change", async (event) => {
      await fillFrontTopicSelectors(event.target.value);
    });
  }

  function fillDeckFilter() {
    const select = A.qs("#filter-deck");
    if (!select) return;
    const current = select.value;
    A.clear(select);
    select.append(A.el("option", { text: "Todos os baralhos", attrs: { value: "" } }));
    decks.forEach((deck) => {
      select.append(A.el("option", { text: `${deck.name || deck.title} (${deck.total_cards || 0})`, attrs: { value: deck.id } }));
    });
    if (current) select.value = current;
  }

  async function loadSubjects() {
    const data = await A.api.get("/api/subjects");
    fillSubjectSelect("#flashcard-subject-select", data.subjects, "Sem matéria vinculada");
    fillSubjectSelect("#filter-subject", data.subjects, "Todas as matérias");
  }

  function fillSubjectSelect(selector, subjects, emptyLabel) {
    const select = A.qs(selector);
    if (!select) return;
    const current = select.value;
    A.clear(select);
    select.append(A.el("option", { text: emptyLabel, attrs: { value: "" } }));
    subjects.forEach((subject) => {
      select.append(A.el("option", { text: subject.name, attrs: { value: subject.id } }));
    });
    if (current) select.value = current;
  }

  async function fillFrontTopicSelectors(subjectId) {
    const frontSelect = A.qs("#flashcard-front-select");
    const topicSelect = A.qs("#flashcard-topic-select");
    if (!frontSelect || !topicSelect) return;

    A.clear(frontSelect);
    A.clear(topicSelect);
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
  }

  async function fillFrontAndTopicFilters(subjectId) {
    const frontFilter = A.qs("#filter-front");
    const topicFilter = A.qs("#filter-topic");
    if (!frontFilter || !topicFilter) return;

    A.clear(frontFilter);
    A.clear(topicFilter);
    frontFilter.append(A.el("option", { text: "Todas as frentes", attrs: { value: "" } }));
    topicFilter.append(A.el("option", { text: "Todos os assuntos", attrs: { value: "" } }));

    if (!subjectId) return;
    const data = await A.api.get(`/api/subjects/${subjectId}`);
    (data.subject.fronts || []).forEach((front) => {
      frontFilter.append(A.el("option", { text: front.name, attrs: { value: front.id } }));
    });
    (data.subject.topics || []).forEach((topic) => {
      topicFilter.append(A.el("option", { text: topic.name, attrs: { value: topic.id } }));
    });
  }

  function generateDraftCardsFromText(text) {
    const lines = String(text || "")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 8);

    const draft = [];
    lines.forEach((line) => {
      if (line.includes(":")) {
        const [left, ...rest] = line.split(":");
        const front = `O que significa: ${left.trim()}?`;
        const back = rest.join(":").trim();
        if (back.length > 4) draft.push({ front, back, tag: "gerado::texto" });
      } else if (line.endsWith("?")) {
        draft.push({ front: line, back: "Responder com base no material." , tag: "gerado::pergunta" });
      } else {
        draft.push({ front: `Explique: ${line.slice(0, 80)}`, back: line, tag: "gerado::frase" });
      }
    });

    return draft.slice(0, 20);
  }

  function renderGeneratedDraft(draftCards) {
    const root = A.qs("#flashcard-text-preview");
    if (!root) return;
    A.clear(root);

    if (!draftCards.length) {
      root.append(A.emptyState("Não foi possível gerar cards com esse texto."));
      return;
    }

    draftCards.forEach((card, index) => {
      const wrapper = A.el("div", { className: "task-item" });
      const front = document.createElement("textarea");
      front.value = card.front;
      front.rows = 2;
      front.addEventListener("input", () => {
        generatedDraftCards[index].front = front.value;
      });

      const back = document.createElement("textarea");
      back.value = card.back;
      back.rows = 3;
      back.addEventListener("input", () => {
        generatedDraftCards[index].back = back.value;
      });

      wrapper.append(A.el("small", { text: `Card ${index + 1}` }), front, back);
      root.append(wrapper);
    });

    const saveButton = A.el("button", { className: "button primary", text: "Salvar cards gerados", attrs: { type: "button" } });
    saveButton.addEventListener("click", saveGeneratedDraftCards);
    root.append(saveButton);
  }

  async function saveGeneratedDraftCards() {
    const subjectId = A.qs("#flashcard-subject-select")?.value || null;
    const frontId = A.qs("#flashcard-front-select")?.value || null;
    const topicId = A.qs("#flashcard-topic-select")?.value || null;
    const deckTitle = "Gerados por material";

    const valid = generatedDraftCards.filter((item) => (item.front || "").trim().length > 5 && (item.back || "").trim().length > 5);
    if (!valid.length) {
      A.toast("Nenhum card válido para salvar.", "error");
      return;
    }

    for (const card of valid) {
      await A.api.post("/api/flashcards", {
        deck_title: deckTitle,
        subject_id: subjectId ? Number(subjectId) : null,
        front_id: frontId ? Number(frontId) : null,
        topic_id: topicId ? Number(topicId) : null,
        front: card.front.trim(),
        back: card.back.trim(),
        tag: card.tag || "gerado::texto",
      });
    }

    A.toast(`${valid.length} flashcards salvos.`);
    generatedDraftCards = [];
    renderGeneratedDraft([]);
    await loadFlashcards();
  }

  function debounce(fn, delay) {
    let timer = null;
    return function debounced() {
      clearTimeout(timer);
      timer = setTimeout(() => fn(), delay);
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "flashcards") {
      bindForm();
      loadFlashcards().catch((error) => A.toast(error.message, "error"));
    }
  });
})();
