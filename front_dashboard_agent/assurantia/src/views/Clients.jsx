import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { T, Spinner, ErrorBanner, EmptyState, Button, ConfirmDialog, useToast } from "../ui.jsx";
import ClientForm from "./ClientForm.jsx";

export default function Clients({ query }) {
  const notify = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [formId, setFormId] = useState(undefined);
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.clients.list({ q: query }).then(setRows).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [query]);

  useEffect(load, [load]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.clients.remove(toDelete.client_id);
      notify(`${toDelete.nom} supprimé.`);
      setToDelete(null);
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="f-display text-2xl" style={{ fontWeight: 600 }}>Clients</h1>
          <p className="text-sm mt-1" style={{ color: T.muted }}>
            {rows.length} client{rows.length > 1 ? "s" : ""} dans le portefeuille
          </p>
        </div>
        <Button onClick={() => setFormId(null)}>
          <Plus size={15} /> Nouveau client
        </Button>
      </div>

      {loading && <Spinner label="Chargement des clients…" />}
      {error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && rows.length === 0 && <EmptyState label="Aucun client trouvé" />}

      {!loading && !error && rows.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {rows.map((c) => (
            <div key={c.client_id} className="rounded-lg border p-5 group relative" style={{ borderColor: T.line, backgroundColor: T.surface }}>
              <div className="absolute top-4 right-4 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={() => setFormId(c.client_id)} aria-label={`Modifier ${c.nom}`} className="p-1.5 rounded-md hover:bg-black/5">
                  <Pencil size={14} color={T.muted} />
                </button>
                <button onClick={() => setToDelete(c)} aria-label={`Supprimer ${c.nom}`} className="p-1.5 rounded-md hover:bg-black/5">
                  <Trash2 size={14} color={T.red} />
                </button>
              </div>
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold mb-3"
                style={{ backgroundColor: T.accentDim, color: T.accent }}
              >
                {[c.prenom, c.nom].filter(Boolean).map((n) => n[0]).join("").toUpperCase() || "?"}
              </div>
              <div className="font-medium text-sm">{[c.prenom, c.nom].filter(Boolean).join(" ") || "—"}</div>
              <div className="text-xs mt-1" style={{ color: T.grey }}>
                {c.telephone || c.email || "Aucun contact renseigné"}
              </div>
              <div className="flex gap-4 mt-3 pt-3 border-t text-xs" style={{ borderColor: T.lineLight }}>
                <span><span className="f-mono font-medium">{c.nb_contrats ?? 0}</span> contrat(s)</span>
                <span><span className="f-mono font-medium">{c.nb_sinistres ?? 0}</span> sinistre(s)</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {formId !== undefined && (
        <ClientForm clientId={formId} onClose={() => setFormId(undefined)} onSaved={() => { setFormId(undefined); load(); }} />
      )}

      {toDelete && (
        <ConfirmDialog
          title="Supprimer ce client ?"
          message={`${toDelete.nom} ${toDelete.prenom || ""} sera définitivement supprimé. Impossible s'il possède encore des contrats.`}
          confirmLabel="Supprimer"
          onConfirm={handleDelete}
          onCancel={() => setToDelete(null)}
          busy={deleting}
        />
      )}
    </div>
  );
}
