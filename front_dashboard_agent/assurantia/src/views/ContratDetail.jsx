import React, { useEffect, useState } from "react";
import { X, Pencil, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { T, StatusBadge, RefStamp, Spinner, ErrorBanner, Button, ConfirmDialog, useToast } from "../ui.jsx";

function Fact({ label, value }) {
  return (
    <div className="border rounded-md p-3" style={{ borderColor: T.lineLight }}>
      <div className="text-[11px] uppercase tracking-wide f-mono" style={{ color: T.grey }}>
        {label}
      </div>
      <div className="text-sm mt-1 font-medium">{value ?? "—"}</div>
    </div>
  );
}

const GARANTIES_DEFS = [
  { key: "dommages_collision", label: "Dommages Collision" },
  { key: "rc", label: "Responsabilité Civile" },
  { key: "vol", label: "Vol" },
  { key: "incendie", label: "Incendie" },
  { key: "bris_glace", label: "Bris de glace" },
];

const money = (v) => (v == null ? "—" : `${Number(v).toLocaleString("fr-FR")} DT`);
const dateFr = (v) => (v ? new Date(v).toLocaleDateString("fr-FR") : "—");

export default function ContratDetail({ contratId, onClose, onEdit, onDeleted }) {
  const notify = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    api.contrats.get(contratId).then(setData).catch((e) => setError(e.message));
  }, [contratId]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.contrats.remove(contratId);
      notify("Contrat supprimé.");
      onDeleted();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ backgroundColor: "rgba(22,33,62,0.35)" }} onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[480px] h-full overflow-auto relative"
        style={{ backgroundColor: T.surface }}
      >
        <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ backgroundColor: T.accent }} />
        <button onClick={onClose} aria-label="Fermer" className="absolute top-5 right-5 p-1.5 rounded-md hover:bg-black/5">
          <X size={18} />
        </button>

        <div className="pl-8 pr-6 py-8">
          {error && <ErrorBanner message={error} />}
          {!error && !data && <Spinner label="Chargement du contrat…" />}

          {data && (
            <div className="space-y-6">
              <div>
                <RefStamp>{data.contrat.num_police}</RefStamp>
                <h2 className="f-display text-xl mt-3" style={{ fontWeight: 600 }}>
                  {[data.client?.prenom, data.client?.nom].filter(Boolean).join(" ") || "Client non renseigné"}
                </h2>
                <div className="mt-2 flex items-center gap-2">
                  <StatusBadge status={data.contrat.statut} />
                  <span className="text-xs" style={{ color: T.grey }}>{data.contrat.type_contrat}</span>
                </div>
              </div>

              <div className="flex gap-2">
                <Button variant="ghost" onClick={onEdit}>
                  <Pencil size={14} /> Modifier
                </Button>
                <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                  <Trash2 size={14} /> Supprimer
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <Fact label="Prime annuelle" value={money(data.contrat.prime_annuelle)} />
                <Fact label="Bonus / Malus" value={data.contrat.bonus_malus} />
                <Fact label="Date d'effet" value={dateFr(data.contrat.date_effet)} />
                <Fact label="Échéance" value={dateFr(data.contrat.date_expiration)} />
                <Fact label="Mode de paiement" value={data.contrat.mode_paiement} />
                <Fact label="Agence" value={data.contrat.agence} />
              </div>

              {data.client && (
                <div className="pt-4 border-t" style={{ borderColor: T.lineLight }}>
                  <h3 className="text-sm font-semibold mb-3">Client</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <Fact label="CIN" value={data.client.cin} />
                    <Fact label="Téléphone" value={data.client.telephone} />
                    <Fact label="Email" value={data.client.email} />
                    <Fact label="Profession" value={data.client.profession} />
                  </div>
                </div>
              )}

              {data.vehicule && (
                <div className="pt-4 border-t" style={{ borderColor: T.lineLight }}>
                  <h3 className="text-sm font-semibold mb-3">Véhicule assuré</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <Fact label="Véhicule" value={[data.vehicule.marque, data.vehicule.modele].filter(Boolean).join(" ")} />
                    <Fact label="Année" value={data.vehicule.annee} />
                    <Fact label="Immatriculation" value={data.vehicule.immatriculation} />
                    <Fact label="Couleur" value={data.vehicule.couleur} />
                    <Fact label="Énergie" value={data.vehicule.energie} />
                    <Fact label="Usage" value={data.vehicule.usage} />
                    <Fact label="Valeur assurée" value={money(data.vehicule.valeur_assuree)} />
                  </div>
                </div>
              )}

              {data.garanties && (
                <div className="pt-4 border-t" style={{ borderColor: T.lineLight }}>
                  <h3 className="text-sm font-semibold mb-3">Garanties souscrites</h3>
                  <ul className="space-y-2 text-sm">
                    {GARANTIES_DEFS.map((g) => {
                      const active = data.garanties[`${g.key}_active`];
                      return (
                        <li key={g.key} className="flex items-center justify-between">
                          <span className="flex items-center gap-2" style={{ color: active ? T.ink : T.grey }}>
                            <span
                              className="w-1.5 h-1.5 rounded-full"
                              style={{ backgroundColor: active ? T.green : T.line }}
                            />
                            {g.label}
                          </span>
                          {active && (
                            <span className="f-mono text-xs" style={{ color: T.muted }}>
                              franchise {money(data.garanties[`${g.key}_franchise`])} · plafond{" "}
                              {money(data.garanties[`${g.key}_plafond`])}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {data.exclusion && (data.exclusion.conduite_sous_alcool || data.exclusion.conducteur_non_autorise) && (
                <div className="pt-4 border-t" style={{ borderColor: T.lineLight }}>
                  <h3 className="text-sm font-semibold mb-3">Exclusions actives</h3>
                  <ul className="space-y-1 text-sm" style={{ color: T.red }}>
                    {data.exclusion.conduite_sous_alcool && <li>Conduite sous l'emprise de l'alcool</li>}
                    {data.exclusion.conducteur_non_autorise && <li>Conducteur non autorisé</li>}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title="Supprimer ce contrat ?"
          message="Le véhicule, les garanties et les exclusions associés seront également supprimés. Cette action est irréversible."
          confirmLabel="Supprimer"
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(false)}
          busy={deleting}
        />
      )}
    </div>
  );
}
