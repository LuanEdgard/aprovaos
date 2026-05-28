(function () {
  const A = window.AprovaOS;
  if (!A) return;

  const MODE_META = {
    organizador: { label: "Organizador", placeholder: "Pergunte o que estudar hoje…" },
    analista: { label: "Analista", placeholder: "Peça uma análise do seu desempenho…" },
    tutor_fontes: { label: "Tutor com fontes", placeholder: "Pergunte sobre um material…" },
    flashcards: { label: "Criador de flashcards", placeholder: "Peça cards sobre um conteúdo…" },
    recuperacao: { label: "Recuperação", placeholder: "Diga o que atrasou…" },
    priorizador: { label: "Priorizador", placeholder: "Peça para priorizar suas pendências…" },
  };

  const state = {
    mode: "organizador",
    activeConversationId: null,
    conversations: [],
    materials: [],
    selectedMaterialId: null,
    sending: false,
    loadingNode: null,
  };

  const ui = {};

  function initRefs() {
    ui.conversationList = A.qs("#ai-conversation-list");
    ui.messages = A.qs("#ai-messages");
    ui.emptyState = A.qs("#ai-empty-state");
    ui.form = A.qs("#ai-form");
    ui.input = A.qs("#ai-input");
    ui.send = A.qs("#ai-send");
    ui.modeBadge = A.qs("#ai-active-mode");
    ui.modeButtons = A.qsa(".tutor-mode-button");
    ui.newConversation = A.qs("#ai-new-conversation");
    ui.warning = A.qs("#ai-warning-banner");
    ui.materialSelect = A.qs("#ai-material-select");
    ui.quickButtons = A.qsa("[data-quick-message]");
    ui.generateFlashcardsButton = A.qs("#ai-generate-flashcards");
    ui.reorganizeWeekButton = A.qs("#ai-reorganize-week");
  }

  function setMode(mode) {
    if (!MODE_META[mode]) return;
    state.mode = mode;
    ui.modeButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.aiMode === mode);
    });
    ui.modeBadge.textContent = MODE_META[mode].label;
    ui.input.placeholder = MODE_META[mode].placeholder;
    ui.reorganizeWeekButton.classList.toggle("hidden", mode !== "recuperacao");
  }

  function setWarning(text) {
    if (!text) {
      ui.warning.classList.add("hidden");
      ui.warning.textContent = "";
      return;
    }
    ui.warning.textContent = text;
    ui.warning.classList.remove("hidden");
  }

  function setLoading(loading) {
    state.sending = loading;
    if (ui.send) ui.send.disabled = loading;
    if (ui.input) ui.input.disabled = loading;
    if (loading) {
      state.loadingNode = createLoadingMessage();
      ui.messages.append(state.loadingNode);
      scrollToBottom();
      return;
    }
    if (state.loadingNode) {
      state.loadingNode.remove();
      state.loadingNode = null;
    }
  }

  function createLoadingMessage() {
    const wrapper = A.el("article", { className: "tutor-message assistant" });
    const bubble = A.el("div", { className: "tutor-message-bubble" });
    const loading = A.el("div", { className: "tutor-loading" });
    loading.append(
      A.el("span"),
      A.el("span"),
      A.el("span"),
      A.el("small", { text: "Pensando…" })
    );
    bubble.append(loading);
    wrapper.append(bubble);
    return wrapper;
  }

  function scrollToBottom() {
    ui.messages.scrollTop = ui.messages.scrollHeight;
  }

  function autosizeInput() {
    ui.input.style.height = "auto";
    ui.input.style.height = `${Math.min(ui.input.scrollHeight, 220)}px`;
  }

  function toggleEmptyState() {
    const hasMessages = ui.messages.children.length > 0;
    ui.emptyState.classList.toggle("hidden", hasMessages);
  }

  function renderConversations() {
    A.clear(ui.conversationList);
    if (!state.conversations.length) {
      ui.conversationList.append(A.emptyState("Nenhuma conversa salva ainda."));
      return;
    }
    state.conversations.forEach((item) => {
      const button = A.el(
        "button",
        {
          className: `tutor-conversation-item ${item.id === state.activeConversationId ? "active" : ""}`,
          attrs: { type: "button", "data-conversation-id": item.id },
        },
      );
      button.append(
        A.el("strong", { text: item.title || "Nova conversa" }),
        A.el("small", { text: formatRelativeDate(item.updated_at || item.created_at) }),
      );
      button.addEventListener("click", () => openConversation(item.id));
      ui.conversationList.append(button);
    });
  }

  function formatRelativeDate(value) {
    if (!value) return "agora";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "agora";
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
  }

  async function loadConversations() {
    const data = await A.api.get("/api/ai/conversations");
    state.conversations = data.conversations || [];
    renderConversations();
  }

  async function openConversation(conversationId) {
    const data = await A.api.get(`/api/ai/conversations/${conversationId}`);
    state.activeConversationId = conversationId;
    const messages = data.conversation?.messages || [];
    A.clear(ui.messages);
    messages.forEach((message) => renderMessage(message));
    renderConversations();
    toggleEmptyState();
    scrollToBottom();
  }

  async function loadMaterials() {
    const data = await A.api.get("/api/ai/materials");
    state.materials = data.materials || [];
    const select = ui.materialSelect;
    A.clear(select);
    select.append(A.el("option", { text: "Sem material selecionado", attrs: { value: "" } }));
    state.materials.forEach((material) => {
      select.append(
        A.el("option", {
          text: material.title,
          attrs: { value: material.id },
        }),
      );
    });
  }

  function renderMessage(message) {
    const role = message.role === "user" ? "user" : "assistant";
    const wrapper = A.el("article", { className: `tutor-message ${role}` });
    const bubble = A.el("div", { className: "tutor-message-bubble" });

    if (role === "assistant") {
      const meta = A.el("div", { className: "tutor-message-meta" });
      const left = A.el("div", { className: "check-row" });
      left.append(A.el("span", { className: "tutor-avatar", text: "A" }), A.el("strong", { text: "AprovaOS" }));
      const copy = A.el("button", { className: "button ghost", text: "Copiar", attrs: { type: "button" } });
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(message.content || "");
          A.toast("Resposta copiada.");
        } catch (error) {
          A.toast("Não consegui copiar agora.", "error");
        }
      });
      meta.append(left, copy);
      bubble.append(meta);
    }

    const body = A.el("div", { className: "tutor-message-text" });
    renderMarkdownSafe(message.content || "", body);
    bubble.append(body);

    const metadata = message.metadata || {};
    if (metadata.warning) {
      bubble.append(A.el("p", { className: "muted-text", text: metadata.warning }));
    }
    if (metadata.used_context && typeof metadata.used_context === "object") {
      const summary = metadata.used_context;
      bubble.append(
        A.el("p", {
          className: "muted-text",
          text: `Contexto usado: tarefas ${summary.tasks || 0}, materiais ${summary.materials || 0}, simulados ${summary.simulados || 0}, redações ${summary.redacoes || 0}.`,
        }),
      );
    }
    if (Array.isArray(metadata.sources) && metadata.sources.length) {
      bubble.append(renderSources(metadata.sources));
    }
    if (Array.isArray(metadata.actions) && metadata.actions.length) {
      bubble.append(renderActions(metadata.actions));
    }

    wrapper.append(bubble);
    ui.messages.append(wrapper);
    toggleEmptyState();
  }

  function renderSources(sources) {
    const section = A.el("section", { className: "tutor-source-list" });
    section.append(A.el("h4", { text: "Fontes usadas" }));
    sources.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const label = `${item.type || "dado"} · ${item.title || "sem título"}`;
      section.append(A.el("div", { className: "tutor-source-item", text: label }));
    });
    return section;
  }

  function renderActions(actions) {
    const section = A.el("section", { className: "tutor-action-list" });
    actions.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const card = A.el("article", { className: "tutor-action-card" });
      card.append(A.el("strong", { text: item.label || "Ação sugerida" }));
      const button = A.el("button", {
        className: "button secondary",
        text: "Aplicar",
        attrs: { type: "button" },
      });
      button.addEventListener("click", () => runAction(item.action, item.payload || {}));
      card.append(button);
      section.append(card);
    });
    return section;
  }

  function renderMarkdownSafe(text, container) {
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    let list = null;
    let listKind = "";
    let inCode = false;
    let codeLines = [];

    function closeList() {
      if (list) container.append(list);
      list = null;
      listKind = "";
    }

    function closeCode() {
      if (!inCode) return;
      const pre = A.el("pre");
      const code = A.el("code");
      code.textContent = codeLines.join("\n");
      pre.append(code);
      container.append(pre);
      inCode = false;
      codeLines = [];
    }

    lines.forEach((rawLine) => {
      const line = rawLine || "";
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        closeList();
        if (inCode) {
          closeCode();
        } else {
          inCode = true;
          codeLines = [];
        }
        return;
      }
      if (inCode) {
        codeLines.push(line);
        return;
      }
      if (!trimmed) {
        closeList();
        return;
      }

      const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (headingMatch) {
        closeList();
        const level = Math.min(4, headingMatch[1].length) + 2;
        const tag = level > 6 ? "h6" : `h${level}`;
        container.append(A.el(tag, { text: headingMatch[2] }));
        return;
      }

      const blockMatch = trimmed.match(/^>\s+(.+)$/);
      if (blockMatch) {
        closeList();
        container.append(A.el("blockquote", { text: blockMatch[1] }));
        return;
      }

      const ulMatch = trimmed.match(/^[-*]\s+(.+)$/);
      if (ulMatch) {
        if (listKind !== "ul") {
          closeList();
          listKind = "ul";
          list = A.el("ul");
        }
        list.append(A.el("li", { text: ulMatch[1] }));
        return;
      }

      const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
      if (olMatch) {
        if (listKind !== "ol") {
          closeList();
          listKind = "ol";
          list = A.el("ol");
        }
        list.append(A.el("li", { text: olMatch[1] }));
        return;
      }

      closeList();
      container.append(A.el("p", { text: trimmed }));
    });

    closeList();
    closeCode();
  }

  async function sendChatMessage(text) {
    if (state.sending) return;
    const message = (text || ui.input.value || "").trim();
    if (!message) return;

    const userMessage = { role: "user", content: message, metadata: {} };
    renderMessage(userMessage);
    ui.input.value = "";
    autosizeInput();
    setWarning(null);
    setLoading(true);

    try {
      const result = await A.api.post("/api/ai/chat", {
        message,
        mode: state.mode,
        conversation_id: state.activeConversationId,
        material_id: state.selectedMaterialId || null,
      });
      state.activeConversationId = result.conversation?.id || state.activeConversationId;
      const assistantMessage = result.assistant_message || {
        role: "assistant",
        content: result.answer || "Sem resposta disponível.",
        metadata: {
          sources: result.sources || [],
          actions: result.actions || [],
          warning: result.warning,
          used_context: result.used_context,
        },
      };
      renderMessage(assistantMessage);
      setWarning(result.warning || null);
      await loadConversations();
      scrollToBottom();
    } catch (error) {
      const textError = error?.message || "Não consegui responder agora.";
      renderMessage({ role: "assistant", content: textError, metadata: {} });
      setWarning(textError);
      A.toast(textError, "error");
    } finally {
      setLoading(false);
    }
  }

  async function runAction(action, payload) {
    if (!action) return;
    setLoading(true);
    try {
      if (action === "prepare_flashcards_from_material") {
        const id = payload.material_id || state.selectedMaterialId;
        if (!id) throw new Error("Selecione um material primeiro.");
        const result = await A.api.post(`/api/ai/materials/${id}/generate-flashcards`, {});
        renderMessage({
          role: "assistant",
          content: result.answer,
          metadata: { sources: result.sources, actions: result.actions, warning: result.warning, used_context: result.used_context },
        });
      } else if (action === "prepare_tasks_from_material") {
        const id = payload.material_id || state.selectedMaterialId;
        if (!id) throw new Error("Selecione um material primeiro.");
        const result = await A.api.post(`/api/ai/materials/${id}/generate-tasks`, {});
        renderMessage({
          role: "assistant",
          content: result.answer,
          metadata: { sources: result.sources, actions: result.actions, warning: result.warning, used_context: result.used_context },
        });
      } else if (action === "run_reorganize_week") {
        const result = await A.api.post("/api/ai/reorganize-week", {});
        renderMessage({
          role: "assistant",
          content: result.answer,
          metadata: { sources: result.sources, actions: result.actions, warning: result.warning, used_context: result.used_context },
        });
      } else if (action === "run_prioritize_tasks") {
        const result = await A.api.post("/api/ai/prioritize-tasks", {});
        renderMessage({
          role: "assistant",
          content: result.answer,
          metadata: { sources: result.sources, actions: result.actions, warning: result.warning, used_context: result.used_context },
        });
      } else if (action === "run_weekly_insights") {
        const result = await A.api.post("/api/ai/reports/weekly-insights", {});
        renderMessage({
          role: "assistant",
          content: result.answer,
          metadata: { sources: result.sources, actions: result.actions, warning: result.warning, used_context: result.used_context },
        });
      } else if (action === "create_flashcards" || action === "create_tasks" || action === "apply_reorganize_week") {
        const result = await A.api.post("/api/ai/actions/apply", { action, payload });
        renderMessage({ role: "assistant", content: result.message || "Sugestão aplicada.", metadata: {} });
        A.toast(result.message || "Sugestão aplicada.");
      } else {
        throw new Error("Ação ainda não suportada nesta versão.");
      }
      scrollToBottom();
    } catch (error) {
      const message = error?.message || "Não consegui aplicar a ação agora.";
      A.toast(message, "error");
      setWarning(message);
    } finally {
      setLoading(false);
    }
  }

  function bindEvents() {
    ui.modeButtons.forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.aiMode));
    });

    ui.newConversation?.addEventListener("click", () => {
      state.activeConversationId = null;
      A.clear(ui.messages);
      toggleEmptyState();
      setWarning(null);
      renderConversations();
    });

    ui.quickButtons.forEach((button) => {
      button.addEventListener("click", () => sendChatMessage(button.dataset.quickMessage));
    });

    ui.materialSelect?.addEventListener("change", () => {
      const value = ui.materialSelect.value;
      state.selectedMaterialId = value ? Number(value) : null;
    });

    ui.generateFlashcardsButton?.addEventListener("click", () => {
      if (!state.selectedMaterialId) {
        setWarning("Selecione um material para gerar flashcards.");
        return;
      }
      runAction("prepare_flashcards_from_material", { material_id: state.selectedMaterialId });
    });

    ui.reorganizeWeekButton?.addEventListener("click", () => runAction("run_reorganize_week", {}));

    ui.input?.addEventListener("input", autosizeInput);
    ui.input?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        ui.form.requestSubmit();
      }
    });

    ui.form?.addEventListener("submit", (event) => {
      event.preventDefault();
      sendChatMessage();
    });
  }

  async function boot() {
    initRefs();
    setMode(state.mode);
    bindEvents();
    toggleEmptyState();
    autosizeInput();
    try {
      const modes = await A.api.get("/api/ai/modes");
      (modes.modes || []).forEach((item) => {
        if (!item || !item.key) return;
        MODE_META[item.key] = {
          label: item.label || MODE_META[item.key]?.label || item.key,
          placeholder: item.placeholder || MODE_META[item.key]?.placeholder || "Pergunte…",
        };
      });
      setMode(state.mode);
    } catch (error) {
      // silêncio: fallback local de modos já existe
    }
    try {
      await Promise.all([loadMaterials(), loadConversations()]);
      if (!state.conversations.length) {
        renderMessage({
          role: "assistant",
          content:
            "Escolha um modo e faça sua pergunta. Eu uso seus dados reais do AprovaOS quando eles existirem.",
          metadata: {},
        });
      }
    } catch (error) {
      const message = error?.message || "Não consegui iniciar o Tutor IA.";
      setWarning(message);
      A.toast(message, "error");
    } finally {
      toggleEmptyState();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page !== "tutor") return;
    boot();
  });
})();
