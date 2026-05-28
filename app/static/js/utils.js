(function () {
  const AprovaOS = (window.AprovaOS = window.AprovaOS || {});

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function clear(element) {
    if (element) element.replaceChildren();
  }

  function el(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text;
    if (options.attrs) {
      Object.entries(options.attrs).forEach(([key, value]) => {
        if (value !== undefined && value !== null) node.setAttribute(key, value);
      });
    }
    children.forEach((child) => node.append(child));
    return node;
  }

  function setText(selector, value, root = document) {
    const node = qs(selector, root);
    if (node) node.textContent = value ?? "";
  }

  function formToObject(form) {
    const data = {};
    new FormData(form).forEach((value, key) => {
      const input = form.elements[key];
      if (value === "") {
        data[key] = null;
        return;
      }
      if (input && input.type === "number") {
        data[key] = Number(value);
        return;
      }
      data[key] = value;
    });
    return data;
  }

  function fillForm(form, data) {
    if (!form) return;
    Object.entries(data).forEach(([key, value]) => {
      const field = form.elements[key];
      if (field) field.value = value ?? "";
    });
  }

  function formatDate(value) {
    if (!value) return "sem prazo";
    if (typeof value === "string") {
      const dateOnly = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (dateOnly) {
        const [, year, month, day] = dateOnly;
        const localDate = new Date(Number(year), Number(month) - 1, Number(day));
        return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(localDate);
      }
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(date);
  }

  function formatDateTime(value) {
    if (!value) return "sem horário";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
  }

  function toast(message, type = "success") {
    const region = qs("#toast-region");
    if (!region) return;
    const item = el("div", { className: `toast ${type}`, text: message });
    region.append(item);
    setTimeout(() => item.remove(), 4200);
  }

  function emptyState(text) {
    return el("p", { className: "muted-text", text });
  }

  AprovaOS.qs = qs;
  AprovaOS.qsa = qsa;
  AprovaOS.clear = clear;
  AprovaOS.el = el;
  AprovaOS.setText = setText;
  AprovaOS.formToObject = formToObject;
  AprovaOS.fillForm = fillForm;
  AprovaOS.formatDate = formatDate;
  AprovaOS.formatDateTime = formatDateTime;
  AprovaOS.toast = toast;
  AprovaOS.emptyState = emptyState;
})();
