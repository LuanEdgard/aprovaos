(function () {
  const AprovaOS = (window.AprovaOS = window.AprovaOS || {});

  async function request(path, options = {}) {
    const headers = options.headers ? { ...options.headers } : {};
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers,
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (error) {
      payload = {};
    }
    if (!response.ok) {
      const detail = payload.detail;
      const message = Array.isArray(detail) ? "Confira os campos e tente novamente." : detail || "Não foi possível concluir a ação.";
      throw new Error(message);
    }
    return payload;
  }

  AprovaOS.api = {
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body }),
    patch: (path, body) => request(path, { method: "PATCH", body }),
    put: (path, body) => request(path, { method: "PUT", body }),
    delete: (path) => request(path, { method: "DELETE" }),
  };
})();
