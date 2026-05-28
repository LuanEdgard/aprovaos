(function () {
  const A = window.AprovaOS;

  async function loadSettings() {
    const form = A.qs("#settings-form");
    if (!form) return;
    const data = await A.api.get("/api/settings");
    form.elements.theme.value = data.settings.theme || "escuro";
    form.elements.notify_reviews.checked = Boolean(data.settings.notify_reviews);
    form.elements.notify_weekly_summary.checked = Boolean(data.settings.notify_weekly_summary);
  }

  function bindSettingsForm() {
    const form = A.qs("#settings-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const payload = {
          theme: form.elements.theme.value,
          notify_reviews: form.elements.notify_reviews.checked,
          notify_weekly_summary: form.elements.notify_weekly_summary.checked,
        };
        const result = await A.api.post("/api/settings", payload);
        document.documentElement.setAttribute("data-theme", payload.theme === "claro" ? "light" : "dark");
        localStorage.setItem("aprovaos-theme", payload.theme === "claro" ? "light" : "dark");
        A.toast(result.message || "Preferências salvas.");
      } catch (error) {
        A.toast(error.message, "error");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "settings") {
      bindSettingsForm();
      loadSettings().catch((error) => A.toast(error.message, "error"));
    }
  });
})();
