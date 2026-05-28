(function () {
  const A = window.AprovaOS;

  async function loadEssays() {
    const data = await A.api.get("/api/essays");
    renderEssays(data);
  }

  function renderEssays(data) {
    const list = A.qs("#essay-list");
    A.clear(list);
    if (!data.essays.length) {
      list.append(A.emptyState("Registre redações para acompanhar evolução."));
    } else {
      data.essays.forEach((essay) => {
        list.append(A.el("div", { className: "list-item" }, [
          A.el("strong", { text: essay.theme }),
          A.el("span", { text: `${A.formatDate(essay.date)} · nota estimada ${essay.total_score ?? "não informada"}` }),
          A.el("small", { text: essay.recurring_errors || "sem erros recorrentes registrados" }),
        ]));
      });
    }

    const analysis = A.qs("#essay-analysis");
    A.clear(analysis);
    if (!data.analysis.has_data) {
      analysis.append(A.emptyState(data.analysis.message));
    } else {
      analysis.append(A.el("p", { text: `Média estimada: ${data.analysis.average ?? "sem média"}` }));
      analysis.append(A.el("p", { text: `Competência mais fraca: ${data.analysis.weakest_competence}` }));
      analysis.append(A.el("p", { text: "Meta sugerida: escrever uma redação por semana e revisar o erro mais recorrente antes da próxima prática." }));
    }

    A.renderChart("essay-score-chart", "line", data.essays.map((essay) => A.formatDate(essay.date)), [
      { label: "Nota estimada", data: data.essays.map((essay) => essay.total_score || 0), borderColor: "#2dd4bf", backgroundColor: "rgba(45,212,191,.16)", tension: 0.35 },
    ]);
  }

  function bindForm() {
    const form = A.qs("#essay-form");
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.post("/api/essays", A.formToObject(form));
      A.toast("Redação registrada.");
      form.reset();
      await loadEssays();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "essays") {
      bindForm();
      loadEssays().catch((error) => A.toast(error.message, "error"));
    }
  });
})();

