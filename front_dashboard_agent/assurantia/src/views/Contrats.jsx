import React, { useEffect, useState, useCallback } from "react";
import { Plus, ChevronRight, Pencil, Trash2, Car, Home, HeartPulse, Umbrella } from "lucide-react";
import { api } from "../api.js";
import {
  T, StatusBadge, RefStamp, Spinner, ErrorBanner, EmptyState, Button, Select,
  ConfirmDialog, useToast,
} from "../ui.jsx";
import ContratForm from "./ContratForm.jsx";
import ContratDetail from "./ContratDetail.jsx";

const TYPE_ICON = { Auto: Car, Habitation: Home, "Santé": HeartPulse, Vie: Umbrella };

export default function Contrats({ query, meta }) {
  const notify = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statutFilter, setStatutFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const [formId, setFormId] = useState(undefined); // undefined = fermé, null = création, id = édition
  const [detailId, setDetailId] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.contrats
      .list({ q: query, statut: statutFilter, type_contrat: typeFilter })
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [query, statutFilter, typeFilter]);

  useEffect(load, [load]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.contrats.remove(toDelete.contrat_id);
      notify(`Contrat ${toDelete.num_police} supprimé.`);
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
          <h1 className="f-display text-2xl" style={{ fontWeight: 600 }}>
            Contrats
          </h1>
          <p className="text-sm mt-1" style={{ color: T.muted }}>
            {rows.length} contrat{rows.length > 1 ? "s" : ""} affiché{rows.length > 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="!w-40">
            <option value="">Tous types</option>
            {(meta?.types_contrat || []).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Select value={statutFilter} onChange={(e) => setStatutFilter(e.target.value)} className="!w-40">
            <option value="">Tous statuts</option>
            {(meta?.statuts_contrat || []).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Button onClick={() => setFormId(null)}>
            <Plus size={15} /> Nouveau contrat
          </Button>
        </div>
      </div>

      {loading && <Spinner label="Chargement des contrats…" />}
      {error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && rows.length === 0 && (
        <EmptyState label="Aucun contrat trouvé" sub="Ajustez vos filtres ou créez un nouveau contrat." />
      )}

      {!loading && !error && rows.length > 0 && (
        <div className="rounded-lg border overflow-hidden" style={{ borderColor: T.line, backgroundColor: T.surface }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b" style={{ borderColor: T.line, backgroundColor: "#F7F8F9" }}>
                {["Référence", "Client", "Type", "Prime annuelle", "Échéance", "Statut", ""].map((h) => (
                  <th key={h} className="px-5 py-3 text-xs font-medium uppercase tracking-wide" style={{ color: T.grey }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const Icon = TYPE_ICON[c.type_contrat] || Car;
                return (
                  <tr
                    key={c.contrat_id}
                    onClick={() => setDetailId(c.contrat_id)}
                    className="border-b last:border-0 cursor-pointer hover:bg-[#F7F8F9] transition-colors"
                    style={{ borderColor: T.lineLight }}
                  >
                    <td className="px-5 py-3.5">
                      <RefStamp>{c.num_police || `CT-${c.contrat_id}`}</RefStamp>
                    </td>
                    <td className="px-5 py-3.5 font-medium">
                      {[c.client_prenom, c.client_nom].filter(Boolean).join(" ") || "—"}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="inline-flex items-center gap-1.5" style={{ color: T.muted }}>
                        <Icon size={14} /> {c.type_contrat || "—"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 f-mono">
                      {c.prime_annuelle != null ? `${Number(c.prime_annuelle).toLocaleString("fr-FR")} DT` : "—"}
                    </td>
                    <td className="px-5 py-3.5 f-mono" style={{ color: T.muted }}>
                      {c.date_expiration ? new Date(c.date_expiration).toLocaleDateString("fr-FR") : "—"}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={c.statut} />
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={(e) => { e.stopPropagation(); setFormId(c.contrat_id); }}
                          className="p-1.5 rounded-md hover:bg-black/5"
                          aria-label={`Modifier le contrat ${c.num_police}`}
                        >
                          <Pencil size={14} color={T.muted} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); setToDelete(c); }}
                          className="p-1.5 rounded-md hover:bg-black/5"
                          aria-label={`Supprimer le contrat ${c.num_police}`}
                        >
                          <Trash2 size={14} color={T.red} />
                        </button>
                        <ChevronRight size={16} color={T.grey} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {formId !== undefined && (
        <ContratForm
          contratId={formId}
          onClose={() => setFormId(undefined)}
          onSaved={() => { setFormId(undefined); load(); }}
        />
      )}

      {detailId && (
        <ContratDetail
          contratId={detailId}
          onClose={() => setDetailId(null)}
          onEdit={() => { setFormId(detailId); setDetailId(null); }}
          onDeleted={() => { setDetailId(null); load(); }}
        />
      )}

      {toDelete && (
        <ConfirmDialog
          title="Supprimer ce contrat ?"
          message={`Le contrat ${toDelete.num_police} ainsi que le véhicule, les garanties et les exclusions qui lui sont associés seront définitivement supprimés. Cette action est irréversible.`}
          confirmLabel="Supprimer"
          onConfirm={handleDelete}
          onCancel={() => setToDelete(null)}
          busy={deleting}
        />
      )}
    </div>
  );
}
