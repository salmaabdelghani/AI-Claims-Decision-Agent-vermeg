import React, { useEffect, useState, useCallback } from "react";
import { Trash2 } from "lucide-react";
import { api } from "../api.js";
import { T, StatusBadge, RefStamp, Spinner, ErrorBanner, EmptyState, Select, ConfirmDialog, useToast } from "../ui.jsx";
import SinistreDetail from "./SinistreDetail.jsx";

export default function Sinistres({ query, meta }) {
  const notify = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statutFilter, setStatutFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const allStatuts = [...(meta?.statuts_sinistre_pipeline || []), ...(meta?.statuts_sinistre_gestion || [])];

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.sinistres.list({ q: query, statut: statutFilter }).then(setRows).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [query, statutFilter]);

  useEffect(load, [load]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.sinistres.remove(toDelete.id);
      notify(`Dossier ${toDelete.numero_dossier} supprimé.`);
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
          <h1 className="f-display text-2xl" style={{ fontWeight: 600 }}>Sinistres</h1>
          <p className="text-sm mt-1" style={{ color: T.muted }}>
            {rows.length} dossier{rows.length > 1 ? "s" : ""} affiché{rows.length > 1 ? "s" : ""}
          </p>
        </div>
        <Select value={statutFilter} onChange={(e) => setStatutFilter(e.target.value)} className="!w-56">
          <option value="">Tous statuts</option>
          {allStatuts.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
      </div>

      {loading && <Spinner label="Chargement des dossiers…" />}
      {error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && rows.length === 0 && (
        <EmptyState label="Aucun dossier sinistre" sub="Les dossiers apparaissent ici dès qu'un email de déclaration est traité." />
      )}

      {!loading && !error && rows.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          {rows.map((s) => (
            <div
              key={s.id}
              onClick={() => setSelected(s.id)}
              className="rounded-lg border p-5 cursor-pointer hover:shadow-sm transition-shadow relative group"
              style={{ borderColor: T.line, backgroundColor: T.surface }}
            >
              <button
                onClick={(e) => { e.stopPropagation(); setToDelete(s); }}
                aria-label={`Supprimer le dossier ${s.numero_dossier}`}
                className="absolute top-4 right-4 p-1.5 rounded-md hover:bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <Trash2 size={14} color={T.red} />
              </button>
              <div className="flex items-start justify-between pr-8">
                <RefStamp>{s.numero_dossier}</RefStamp>
                <StatusBadge status={s.statut} />
              </div>
              <div className="mt-3 font-medium text-sm">{s.sender || "Expéditeur inconnu"}</div>
              <div className="text-xs mt-1" style={{ color: T.grey }}>
                Police liée : <span className="f-mono">{s.ass_a_numero_police || s.ass_b_numero_police || "—"}</span>
              </div>
              {s.expert && (
                <div className="text-xs mt-1" style={{ color: T.accent }}>
                  Expert affecté : {s.expert}
                </div>
              )}
              <div className="flex items-center justify-between mt-4 pt-4 border-t" style={{ borderColor: T.lineLight }}>
                <span className="text-xs f-mono" style={{ color: T.grey }}>
                  {s.date_accident ? `Accident le ${s.date_accident}` : `Déclaré le ${s.email_date || "—"}`}
                </span>
                <span className="text-xs" style={{ color: T.grey }}>{s.lieu_accident || ""}</span>
              </div>
              <div className="text-[11px] f-mono mt-1.5" style={{ color: T.grey }}>
                Dossier créé le {s.created_at ? new Date(s.created_at).toLocaleString("fr-FR") : "—"}
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <SinistreDetail
          sinistreId={selected}
          meta={meta}
          onClose={() => setSelected(null)}
          onUpdated={load}
          onDeleted={() => { setSelected(null); load(); }}
        />
      )}

      {toDelete && (
        <ConfirmDialog
          title="Supprimer ce dossier ?"
          message={`Le dossier ${toDelete.numero_dossier} sera définitivement supprimé.`}
          confirmLabel="Supprimer"
          onConfirm={handleDelete}
          onCancel={() => setToDelete(null)}
          busy={deleting}
        />
      )}
    </div>
  );
}
