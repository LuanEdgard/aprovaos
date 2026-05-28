(function () {
  const A = window.AprovaOS;
  let materials = [];

  async function loadMaterials() {
    const data = await A.api.get("/api/materials");
    materials = data.materials;
    renderMaterials();
  }

  function renderMaterials() {
    const list = A.qs("#materials-list");
    A.clear(list);
    if (!materials.length) {
      list.append(A.emptyState("Envie um material ou cole um texto para começar."));
      return;
    }
    materials.forEach((material) => {
      const item = A.el("div", { className: "material-item" }, [
        A.el("strong", { text: material.title }),
        A.el("span", { text: `${material.material_type} · ${material.source_type} · ${material.subject || "geral"}` }),
        A.el("small", { text: `Situação: ${material.status} · ${A.formatDate(material.created_at)}` }),
      ]);
      if (material.summary) item.append(A.el("p", { className: "muted-text", text: material.summary }));
      const actions = A.el("div", { className: "item-actions" });
      const open = A.el("a", { className: "button secondary", text: "Abrir", attrs: { href: `/app/materials/${material.id}` } });
      actions.append(open);
      [
        ["Gerar resumo", "summarize"],
        ["Gerar pendências", "generate-tasks"],
        ["Gerar flashcards", "generate-flashcards"],
      ].forEach(([label, action]) => {
        const button = A.el("button", { className: "button ghost", text: label, attrs: { type: "button" } });
        button.addEventListener("click", () => runMaterialAction(material.id, action));
        actions.append(button);
      });
      const tutor = A.el("a", { className: "button ghost", text: "Perguntar ao Tutor IA", attrs: { href: "/app/tutor" } });
      actions.append(tutor);
      item.append(actions);
      list.append(item);
    });
  }

  async function loadMaterialDetail() {
    const root = A.qs("[data-material-id]");
    if (!root) return;
    const data = await A.api.get(`/api/materials/${root.dataset.materialId}`);
    const material = data.material;
    A.setText("#material-title", material.title);
    const meta = A.qs("#material-meta");
    A.clear(meta);
    [
      ["Tipo", material.type],
      ["Fonte", material.source],
      ["Matéria", material.subject || "geral"],
      ["Tópico", material.topic || "não identificado"],
      ["Subtópico", material.subtopic || "não identificado"],
      ["Tags", material.tags || "sem tags"],
    ].forEach(([label, value]) => meta.append(A.el("div", {}, [A.el("small", { text: label }), A.el("strong", { text: value })])));
    A.setText("#material-summary", material.ai_summary || material.summary || "Resumo ainda não gerado.");
    A.setText("#material-text", material.extracted_text || "Não há texto extraído para este material.");
    A.qsa("[data-material-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const result = await A.api.post(`/api/materials/${material.id}/${button.dataset.materialAction}`, {});
        A.toast(result.message || "Ação concluída.");
        await loadMaterialDetail();
      });
    });
    const questionForm = A.qs("#material-question-form");
    if (questionForm && !questionForm.dataset.bound) {
      questionForm.dataset.bound = "true";
      questionForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const result = await A.api.post(`/api/materials/${material.id}/ask`, A.formToObject(questionForm));
        A.setText("#material-answer", result.reply || "Sem resposta.");
        questionForm.reset();
      });
    }
  }

  async function runMaterialAction(id, action) {
    const result = await A.api.post(`/api/materials/${id}/${action}`, {});
    A.toast(result.message || "Ação concluída.");
    await loadMaterials();
  }

  function bindForms() {
    const uploadForm = A.qs("#material-upload-form");
    uploadForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const formData = new FormData(uploadForm);
        const result = await A.api.post("/api/materials/upload", formData);
        A.toast(result.message);
        uploadForm.reset();
        await loadMaterials();
      } catch (error) {
        A.toast(error.message, "error");
      }
    });

    const textForm = A.qs("#material-text-form");
    textForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const result = await A.api.post("/api/materials/text", A.formToObject(textForm));
        A.toast(result.message);
        textForm.reset();
        await loadMaterials();
      } catch (error) {
        A.toast(error.message, "error");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "materials") {
      bindForms();
      loadMaterials().catch((error) => A.toast(error.message, "error"));
      loadMaterialDetail().catch((error) => A.toast(error.message, "error"));
    }
  });
})();
