(function () {
  const A = window.AprovaOS;

  async function loadExams() {
    const data = await A.api.get("/api/exams");
    renderExams(data);
  }

  function renderExams(data) {
    const list = A.qs("#exam-list");
    A.clear(list);
    if (!data.exams.length) {
      list.append(A.emptyState("Registre um simulado para acompanhar evolução."));
    } else {
      data.exams.forEach((exam) => {
        list.append(A.el("div", { className: "list-item" }, [
          A.el("strong", { text: `${exam.exam_type} · ${A.formatDate(exam.date)}` }),
          A.el("span", { text: `Nota total: ${exam.total_score ?? "sem nota"}` }),
          A.el("small", { text: `Motivo de erro: ${exam.error_reason || "não informado"}` }),
        ]));
      });
    }

    const analysis = A.qs("#exam-analysis");
    A.clear(analysis);
    if (!data.analysis.has_data) {
      analysis.append(A.emptyState(data.analysis.message));
    } else {
      analysis.append(A.el("p", { text: `Área mais fraca: ${data.analysis.weakest_area}` }));
      analysis.append(A.el("p", { text: `Área mais forte: ${data.analysis.strongest_area}` }));
      analysis.append(A.el("p", { text: `Última nota: ${data.analysis.latest_score ?? "sem nota total"}` }));
    }

    A.renderChart("exam-score-chart", "line", data.exams.map((exam) => A.formatDate(exam.date)), [
      { label: "Nota total", data: data.exams.map((exam) => exam.total_score || 0), borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,.18)", tension: 0.35 },
    ]);
  }

  function bindForm() {
    const form = A.qs("#exam-form");
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await A.api.post("/api/exams", A.formToObject(form));
      A.toast("Simulado registrado.");
      form.reset();
      await loadExams();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "exams") {
      bindForm();
      loadExams().catch((error) => A.toast(error.message, "error"));
    }
  });
})();

