// ────────────────────────────────────────────────────────────────────────
// Couche d'acces a l'API Assurantia (backend FastAPI branche sur PostgreSQL)
// ────────────────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* pas de corps JSON */
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return null;
  return res.json();
}

const qs = (params = {}) => {
  const usable = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!usable.length) return "";
  return "?" + new URLSearchParams(usable).toString();
};

export const api = {
  health: () => request("/api/health"),
  meta: () => request("/api/meta"),

  dashboard: {
    stats: () => request("/api/dashboard/stats"),
  },

  clients: {
    list: (params) => request(`/api/clients${qs(params)}`),
    get: (id) => request(`/api/clients/${id}`),
    create: (data) => request("/api/clients", { method: "POST", body: JSON.stringify(data) }),
    update: (id, data) => request(`/api/clients/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    remove: (id) => request(`/api/clients/${id}`, { method: "DELETE" }),
  },

  contrats: {
    list: (params) => request(`/api/contrats${qs(params)}`),
    get: (id) => request(`/api/contrats/${id}`),
    create: (data) => request("/api/contrats", { method: "POST", body: JSON.stringify(data) }),
    update: (id, data) => request(`/api/contrats/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    remove: (id) => request(`/api/contrats/${id}`, { method: "DELETE" }),
  },

  sinistres: {
    list: (params) => request(`/api/sinistres${qs(params)}`),
    get: (id) => request(`/api/sinistres/${id}`),
    patch: (id, data) => request(`/api/sinistres/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    remove: (id) => request(`/api/sinistres/${id}`, { method: "DELETE" }),
    pdfUrl: (id, download = false) => `${BASE_URL}/api/sinistres/${id}/rapport.pdf${download ? "?download=true" : ""}`,
  },

  // Dashboard "Agent" — sinistres traites par l'agent email (mailconnector),
  // chronogramme metier de traitement + objets complets par etape + rapport
  // PDF genere automatiquement + confirmation/transmission au dashboard
  // principal.
  agent: {
    list: (params) => request(`/api/agent${qs(params)}`),
    get: (id) => request(`/api/agent/sinistres/${id}`),
    patch: (id, data) => request(`/api/agent/sinistres/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    confirm: (id) => request(`/api/agent/sinistres/${id}/confirm`, { method: "POST" }),
    stats: () => request("/api/agent/stats"),
    activity: () => request("/api/agent/activity"),
    pdfUrl: (id, download = false) => `${BASE_URL}/api/agent/sinistres/${id}/rapport.pdf${download ? "?download=true" : ""}`,

    // Pilotage (demarrer/arreter, intervalle de polling)
    getConfig: () => request("/api/agent/config"),
    patchConfig: (data) => request("/api/agent/config", { method: "PATCH", body: JSON.stringify(data) }),
    launch: () => request("/api/agent/launch", { method: "POST" }),

    // Bareme de responsabilite
    getBareme: () => request("/api/agent/bareme"),
    patchBareme: (cas, data) => request(`/api/agent/bareme/${encodeURIComponent(cas)}`, { method: "PATCH", body: JSON.stringify(data) }),
    resetBareme: (cas) => request(`/api/agent/bareme/${encodeURIComponent(cas)}`, { method: "DELETE" }),

    // Compagnies d'assurance reconnues par l'OCR
    getInsuranceCompanies: () => request("/api/agent/insurance-companies"),
    addInsuranceCompany: (nom) => request("/api/agent/insurance-companies", { method: "POST", body: JSON.stringify({ nom }) }),
    removeInsuranceCompany: (nom) => request(`/api/agent/insurance-companies/${encodeURIComponent(nom)}`, { method: "DELETE" }),

    // Correction du constat / ajout de photos avant confirmation
    correctOcr: (id, ocrJson) => request(`/api/agent/sinistres/${id}/ocr`, { method: "PATCH", body: JSON.stringify({ ocr_json: ocrJson }) }),
    addPhoto: async (id, file) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${BASE_URL}/api/agent/sinistres/${id}/photos`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${res.status}`);
      }
      return res.json();
    },
  },

  documents: {
    url: (gridfsId, download = false) => `${BASE_URL}/api/documents/${gridfsId}${download ? "?download=true" : ""}`,
  },
};

export { ApiError, BASE_URL };
