(function () {
  const A = window.AprovaOS;
  const providerGrid = A.qs("#ai-provider-grid");
  const routingPanel = A.qs("#ai-routing-form");
  const usageBody = A.qs("#ai-usage-body");
  let state = null;

  function statusLabel(provider) {
    if (!provider.configured) return ["Não configurado", "warning"];
    if (!provider.enabled) return ["Desativado", "muted"];
    if (provider.last_test_status === "connected") return ["Conectado", "success"];
    if (provider.last_test_status === "error") return ["Erro", "danger"];
    return ["Chave interna", "info"];
  }

  function renderOverview() {
    const badge = A.qs("#ai-overview-badge");
    const text = A.qs("#ai-overview-text");
    const overview = state.overview;
    const configured = Boolean(overview.configured);
    badge.textContent = configured ? "Ensemble interno ativo" : "IA não configurada";
    badge.className = `badge ${configured ? "success" : "warning"}`;
    text.textContent = configured
      ? `Modo: ${overview.ensemble_enabled ? "mix das IAs configuradas" : "provedor único"}. Provedores ativos: ${overview.enabled_providers.join(", ")}.`
      : "Nenhuma chave interna foi configurada no servidor. Configure OPENAI_API_KEY, GEMINI_API_KEY e DEEPSEEK_API_KEY no ambiente do backend.";
  }

  function renderProviders() {
    A.clear(providerGrid);
    state.providers.forEach((provider) => {
      const [label, badgeClass] = statusLabel(provider);
      const card = A.el("article", { className: "card provider-card" });
      card.append(
        A.el("div", { className: "card-title" }, [
          A.el("span", { text: provider.label }),
          A.el("span", { className: `badge ${badgeClass}`, text: label }),
        ])
      );
      card.append(
        A.el("div", { className: "provider-meta" }, [
          A.el("span", { text: `Chave: ${provider.key_preview || "ausente no servidor"}` }),
          A.el("span", { text: `Modelo padrão: ${provider.default_model || "-"}` }),
          A.el("span", { text: `Último teste: ${provider.last_tested_at ? A.formatDateTime(provider.last_tested_at) : "não testado"}` }),
          A.el("span", { text: `Último sucesso: ${provider.last_successful_tested_at ? A.formatDateTime(provider.last_successful_tested_at) : "sem sucesso registrado"}` }),
          A.el("span", { text: provider.last_test_error ? `Erro: ${provider.last_test_error}` : "" }),
        ])
      );
      const testButton = A.el("button", { className: "button ghost", text: "Testar conexão", attrs: { type: "button" } });
      testButton.addEventListener("click", () => testProvider(provider.provider_name));
      card.append(A.el("div", { className: "provider-actions" }, [testButton]));
      providerGrid.append(card);
    });
  }

  async function testProvider(providerName) {
    try {
      const result = await A.api.post(`/api/settings/ai-integrations/${providerName}/test`, {});
      A.toast(result.message || "Teste concluído.", result.ok ? "success" : "error");
      await load();
    } catch (error) {
      A.toast(error.message, "error");
    }
  }

  function renderRouting() {
    A.clear(routingPanel);
    const note = state.overview.ensemble_enabled
      ? "O AprovaOS está configurado para consultar OpenAI, Gemini e DeepSeek quando as três chaves existem no servidor. As respostas são sintetizadas pelo gateway antes de chegar ao estudante."
      : "O AprovaOS está usando provedor único conforme configuração interna do backend.";
    routingPanel.append(A.el("p", { className: "muted-text", text: note }));
    state.routing.forEach((route) => {
      const item = A.el("div", { className: "routing-item" });
      item.append(A.el("strong", { text: route.label }));
      item.append(A.el("span", { text: `Ordem interna: ${[route.provider_name].concat(route.fallback_order || []).join(" + ")}` }));
      routingPanel.append(item);
    });
  }

  function renderUsage() {
    A.clear(usageBody);
    if (!state.usage.length) {
      const row = A.el("tr");
      row.append(A.el("td", { text: "Ainda não há uso registrado.", attrs: { colspan: "6" } }));
      usageBody.append(row);
      return;
    }
    state.usage.forEach((log) => {
      const row = A.el("tr");
      row.append(A.el("td", { text: log.provider_name }));
      row.append(A.el("td", { text: log.model || "-" }));
      row.append(A.el("td", { text: log.module_name }));
      row.append(A.el("td", { text: log.request_type }));
      row.append(A.el("td", { text: log.success ? "sucesso" : "erro" }));
      row.append(A.el("td", { text: A.formatDateTime(log.created_at) }));
      usageBody.append(row);
    });
  }

  async function load() {
    try {
      state = await A.api.get("/api/settings/ai-integrations");
      renderOverview();
      renderProviders();
      renderRouting();
      renderUsage();
      if (window.lucide) window.lucide.createIcons();
    } catch (error) {
      A.toast(error.message, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page !== "ai-integrations") return;
    load();
  });
})();
