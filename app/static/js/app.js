(function () {
  const A = window.AprovaOS;

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("aprovaos-theme", theme);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(current === "dark" ? "light" : "dark");
  }

  async function submitJsonForm(form, endpoint, successFallback) {
    try {
      const payload = A.formToObject(form);
      const result = await A.api.post(endpoint, payload);
      A.toast(result.message || successFallback || "Ação concluída.");
      if (result.redirect && form.id !== "onboarding-form") {
        window.location.href = result.redirect;
      }
      return result;
    } catch (error) {
      A.toast(error.message, "error");
      return null;
    }
  }

  function bindAuthForms() {
    const loginForm = A.qs("#login-form");
    if (loginForm) {
      loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitJsonForm(loginForm, "/api/login", "Entrada realizada.");
      });
    }

    const signupForm = A.qs("#signup-form");
    if (signupForm) {
      signupForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitJsonForm(signupForm, "/api/signup", "Conta criada.");
      });
    }

    const onboardingForm = A.qs("#onboarding-form");
    if (onboardingForm) {
      onboardingForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const result = await submitJsonForm(onboardingForm, "/api/onboarding", "Perfil criado.");
        if (result && result.profile) renderOnboardingResult(result);
      });
    }
  }

  function renderOnboardingResult(result) {
    const panel = A.qs("#onboarding-result");
    if (!panel) return;
    A.clear(panel);
    panel.classList.remove("hidden");
    panel.append(A.el("h2", { text: "Perfil de estudo gerado" }));
    panel.append(A.el("p", { text: result.profile.perfil_do_estudante }));
    panel.append(A.el("p", { text: `Gargalo principal: ${result.profile.gargalo_principal}` }));
    panel.append(A.el("p", { text: `Risco de sobrecarga: ${result.profile.risco_de_sobrecarga}` }));
    panel.append(A.el("p", { text: `Prioridade da primeira semana: ${result.profile.prioridade_da_primeira_semana}` }));
    const list = A.el("div", { className: "task-list" });
    result.profile.plano_inicial_7_dias.forEach((item) => {
      list.append(A.el("div", { className: "task-item" }, [
        A.el("strong", { text: A.formatDate(item.dia) }),
        A.el("span", { text: item.foco }),
        A.el("small", { text: item.ação }),
      ]));
    });
    panel.append(list);
    const link = A.el("a", { className: "button primary", text: "Ir para o painel", attrs: { href: result.redirect || "/app/dashboard" } });
    panel.append(link);
  }

  function bindGlobalActions() {
    A.qsa("#theme-toggle, #settings-theme-toggle").forEach((button) => {
      button.addEventListener("click", toggleTheme);
    });

    const sidebarToggle = A.qs("#sidebar-toggle");
    if (sidebarToggle) {
      sidebarToggle.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
    }

    const logoutButton = A.qs("#logout-button");
    if (logoutButton) {
      logoutButton.addEventListener("click", async () => {
        try {
          const result = await A.api.post("/api/logout", {});
          window.location.href = result.redirect || "/";
        } catch (error) {
          A.toast(error.message, "error");
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(localStorage.getItem("aprovaos-theme") || "dark");
    bindGlobalActions();
    bindAuthForms();
    if (window.lucide) window.lucide.createIcons();
  });
})();

