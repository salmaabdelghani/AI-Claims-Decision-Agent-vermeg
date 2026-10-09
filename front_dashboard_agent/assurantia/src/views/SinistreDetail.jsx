import React, { useEffect, useState } from "react";
import { X, Trash2, FileText, Download, Eye } from "lucide-react";
import { api } from "../api.js";
import {
  T, StatusBadge, RefStamp, Spinner, ErrorBanner, Button, Select, Input,
  Textarea, Field, ConfirmDialog, SectionTitle, useToast,
} from "../ui.jsx";

const CIRCONSTANCES_LABELS = {
  en_stationnement: "En stationnement",
  quittait_stationnement: "Quittait un stationnement",
  prenait_stationnement: "Prenait un stationnement",
  sortait_parking: "Sortait d'un parking / lieu privé / chemin de terre",
  engageait_giratoire: "S'engageait dans un carrefour à sens giratoire",
  circulait_giratoire: "Circulait dans un carrefour à sens giratoire",
  heurtait_arriere: "Heurtait à l'arrière (même sens, même file)",
  meme_sens_meme_file: "Roulait dans le même sens, sur une même file",
  changeait_file: "Changeait de file",
  depassait: "Doublait ou dépassait",
  virait_droite: "Virait à droite",
  virait_gauche: "Virait à gauche",
  reculait: "Reculait",
  empiete_sens_inverse: "Empiétait sur la voie de sens inverse",
  venait_droite: "Venait de droite (dans un carrefour)",
  non_prioritaire: "N'avait pas respecté un signal de priorité",
};
const CIRC_KEYS = Object.keys(CIRCONSTANCES_LABELS);

function Fact({ label, value }) {
  return (
    <div className="border rounded-md p-3" style={{ borderColor: T.lineLight }}>
      <div className="text-[11px] uppercase tracking-wide f-mono" style={{ color: T.grey }}>{label}</div>
      <div className="text-sm mt-1 font-medium">{value ?? "—"}</div>
    </div>
  );
}

function VehiculeConstat({ letter, data }) {
  const l = letter.toLowerCase();
  const circCoches = CIRC_KEYS.filter((k) => data[`circ_${l}_${k}`] === true);
  return (
    <div className="rounded-lg border p-4 space-y-4" style={{ borderColor: T.line }}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Véhicule {letter}</h4>
        {data[`signature_${l}`] != null && (
          <span className="text-xs f-mono" style={{ color: data[`signature_${l}`] ? T.green : T.red }}>
            {data[`signature_${l}`] ? "Signé" : "Non signé"}
          </span>
        )}
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide f-mono mb-1.5" style={{ color: T.grey }}>Véhicule</div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div><span style={{ color: T.grey }}>Marque / modèle : </span>{[data[`veh_${l}_marque`], data[`veh_${l}_modele`]].filter(Boolean).join(" ") || "—"}</div>
          <div><span style={{ color: T.grey }}>Immatriculation : </span><span className="f-mono">{data[`veh_${l}_immatriculation`] || "—"}</span></div>
        </div>
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide f-mono mb-1.5" style={{ color: T.grey }}>Assurance</div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div><span style={{ color: T.grey }}>Société : </span>{data[`ass_${l}_societe`] || "—"}</div>
          <div><span style={{ color: T.grey }}>N° police : </span><span className="f-mono">{data[`ass_${l}_numero_police`] || "—"}</span></div>
          <div><span style={{ color: T.grey }}>Agence : </span>{data[`ass_${l}_agence`] || "—"}</div>
          <div><span style={{ color: T.grey }}>Validité : </span>{data[`ass_${l}_validite`] || "—"}</div>
        </div>
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide f-mono mb-1.5" style={{ color: T.grey }}>Conducteur</div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div><span style={{ color: T.grey }}>Nom : </span>{[data[`cond_${l}_nom`], data[`cond_${l}_prenom`]].filter(Boolean).join(" ") || "—"}</div>
          <div><span style={{ color: T.grey }}>Téléphone : </span>{data[`cond_${l}_telephone`] || "—"}</div>
          <div><span style={{ color: T.grey }}>Permis : </span>{data[`cond_${l}_permis`] || "—"}</div>
          <div><span style={{ color: T.grey }}>Adresse : </span>{data[`cond_${l}_adresse`] || "—"}</div>
        </div>
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide f-mono mb-1.5" style={{ color: T.grey }}>Dégâts déclarés</div>
        <div className="grid grid-cols-1 gap-2 text-sm">
          <div><span style={{ color: T.grey }}>Point de choc : </span>{data[`circ_${l}_point_choc`] || "—"}</div>
          <div><span style={{ color: T.grey }}>Dégâts apparents : </span>{data[`circ_${l}_degats_apparents`] || "—"}</div>
          {data[`circ_${l}_observations`] && (
            <div><span style={{ color: T.grey }}>Observations : </span>{data[`circ_${l}_observations`]}</div>
          )}
        </div>
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wide f-mono mb-1.5" style={{ color: T.grey }}>Circonstances cochées</div>
        {circCoches.length === 0 ? (
          <div className="text-sm" style={{ color: T.grey }}>Aucune case cochée</div>
        ) : (
          <ul className="text-sm space-y-1 list-disc pl-4">
            {circCoches.map((k) => <li key={k}>{CIRCONSTANCES_LABELS[k]}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

const TABS = [
  { key: "apercu", label: "Aperçu" },
  { key: "constat", label: "Constat complet" },
  { key: "documents", label: "Photos & documents" },
  { key: "responsabilite", label: "Responsabilité" },
  { key: "expertise", label: "Expertise & remboursement" },
];

export default function SinistreDetail({ sinistreId, meta, onClose, onUpdated, onDeleted }) {
  const notify = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("apercu");

  const [statut, setStatut] = useState("");
  const [expert, setExpert] = useState("");
  const [avisExpert, setAvisExpert] = useState("");
  const [statutRemb, setStatutRemb] = useState("");
  const [montantRemb, setMontantRemb] = useState("");
  const [dateRemb, setDateRemb] = useState("");

  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    api.sinistres
      .get(sinistreId)
      .then((d) => {
        setData(d);
        setStatut(d.statut || "");
        setExpert(d.expert || "");
        setAvisExpert(d.avis_expert || "");
        setStatutRemb(d.statut_remboursement || "");
        setMontantRemb(d.montant_rembourse ?? "");
        setDateRemb(d.date_remboursement || "");
      })
      .catch((e) => setError(e.message));
  };

  useEffect(load, [sinistreId]);

  const allStatuts = [...(meta?.statuts_sinistre_pipeline || []), ...(meta?.statuts_sinistre_gestion || [])];
  const statutsRemboursement = meta?.statuts_remboursement || ["Non initié", "En cours", "Remboursé", "Refusé"];

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.sinistres.patch(sinistreId, {
        statut, expert: expert || null,
        avis_expert: avisExpert || null,
        statut_remboursement: statutRemb || null,
        montant_rembourse: montantRemb === "" ? null : Number(montantRemb),
        date_remboursement: dateRemb || null,
      });
      notify("Dossier mis à jour.");
      load();
      onUpdated();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.sinistres.remove(sinistreId);
      notify("Dossier supprimé.");
      onDeleted();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setDeleting(false);
    }
  };

  const photos = (data?.documents || []).filter((d) => /photo|dommage/i.test(d.nature || ""));
  const constats = (data?.documents || []).filter((d) => /constat/i.test(d.nature || ""));

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ backgroundColor: "rgba(22,33,62,0.35)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-[720px] max-w-full h-full overflow-hidden relative flex flex-col" style={{ backgroundColor: T.surface }}>
        <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ backgroundColor: T.accent }} />
        <button onClick={onClose} aria-label="Fermer" className="absolute top-5 right-5 p-1.5 rounded-md hover:bg-black/5 z-10">
          <X size={18} />
        </button>

        {error && <div className="p-8"><ErrorBanner message={error} /></div>}
        {!error && !data && <div className="p-8"><Spinner label="Chargement du dossier…" /></div>}

        {data && (
          <>
            {/* En-tête fixe */}
            <div className="pl-8 pr-16 pt-8 pb-4 shrink-0 border-b" style={{ borderColor: T.lineLight }}>
              <RefStamp>{data.numero_dossier}</RefStamp>
              <h2 className="f-display text-xl mt-3" style={{ fontWeight: 600 }}>{data.sender || "Expéditeur inconnu"}</h2>
              <div className="mt-2 flex items-center gap-3 flex-wrap">
                <StatusBadge status={data.statut} />
                <span className="text-xs f-mono" style={{ color: T.grey }}>
                  Créé le {data.created_at ? new Date(data.created_at).toLocaleString("fr-FR") : "—"}
                </span>
              </div>

              <div className="flex gap-1 mt-4 -mb-px overflow-x-auto">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className="px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors"
                    style={{
                      color: tab === t.key ? T.accent : T.muted,
                      borderColor: tab === t.key ? T.accent : "transparent",
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Contenu scrollable */}
            <div className="flex-1 overflow-auto pl-8 pr-6 py-6 space-y-6">
              {tab === "apercu" && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <Fact label="N° police (A)" value={data.ass_a_numero_police} />
                    <Fact label="N° police (B)" value={data.ass_b_numero_police} />
                    <Fact label="Date de l'accident" value={data.date_accident} />
                    <Fact label="Lieu" value={data.lieu_accident} />
                    <Fact label="Blessés" value={data.blesses} />
                    <Fact label="Croquis présent" value={data.croquis_present ? "Oui" : "Non"} />
                  </div>

                  {(data.veh_a_marque || data.veh_b_marque) && (
                    <div className="pt-4 border-t space-y-3" style={{ borderColor: T.lineLight }}>
                      <h3 className="text-sm font-semibold">Véhicules impliqués</h3>
                      <div className="grid grid-cols-2 gap-3">
                        <Fact label="Véhicule A" value={[data.veh_a_marque, data.veh_a_modele].filter(Boolean).join(" ") || "—"} />
                        <Fact label="Véhicule B" value={[data.veh_b_marque, data.veh_b_modele].filter(Boolean).join(" ") || "—"} />
                      </div>
                    </div>
                  )}

                  {data.description_croquis && (
                    <div className="pt-4 border-t" style={{ borderColor: T.lineLight }}>
                      <SectionTitle>Croquis</SectionTitle>
                      <p className="text-sm" style={{ color: T.muted }}>{data.description_croquis}</p>
                    </div>
                  )}

                  <div className="pt-4 border-t space-y-4" style={{ borderColor: T.lineLight }}>
                    <SectionTitle>Gestion du dossier</SectionTitle>
                    <Field label="Statut">
                      <Select value={statut} onChange={(e) => setStatut(e.target.value)}>
                        <option value="">—</option>
                        {allStatuts.map((s) => <option key={s} value={s}>{s}</option>)}
                      </Select>
                    </Field>
                    <Field label="Expert affecté">
                      <Input value={expert} onChange={(e) => setExpert(e.target.value)} placeholder="Nom de l'expert" />
                    </Field>
                  </div>
                </>
              )}

              {tab === "constat" && (
                <div className="grid grid-cols-1 gap-4">
                  {constats.length > 0 && (
                    <div>
                      <SectionTitle>Constat original</SectionTitle>
                      <div className="grid grid-cols-1 gap-3">
                        {constats.map((d) => {
                          const isPdf = /\.pdf$/i.test(d.filename || "");
                          const url = api.documents.url(d.gridfs_id);
                          return isPdf ? (
                            <div key={d.id} className="border rounded-md overflow-hidden" style={{ borderColor: T.line }}>
                              <embed src={url} type="application/pdf" className="w-full" style={{ height: 480 }} />
                              <div className="px-3 py-2 text-xs flex items-center justify-between" style={{ backgroundColor: T.paper, color: T.grey }}>
                                {d.filename}
                                <a href={url} target="_blank" rel="noreferrer" style={{ color: T.accent }}>Ouvrir dans un nouvel onglet</a>
                              </div>
                            </div>
                          ) : (
                            <a key={d.id} href={url} target="_blank" rel="noreferrer" className="block border rounded-md overflow-hidden" style={{ borderColor: T.line }}>
                              <img src={url} alt={d.filename} className="w-full max-h-[480px] object-contain" style={{ backgroundColor: T.paper }} />
                              <div className="px-3 py-2 text-xs" style={{ backgroundColor: T.paper, color: T.grey }}>{d.filename}</div>
                            </a>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <Fact label="Date" value={data.date_accident} />
                    <Fact label="Heure" value={data.heure_accident} />
                    <Fact label="Lieu" value={data.lieu_accident} />
                    <Fact label="Blessés" value={data.blesses} />
                    <Fact label="Dégâts matériels autres" value={data.degats_materiels_autres} />
                    <Fact label="Témoins" value={data.temoins?.length ? `${data.temoins.length} témoin(s)` : "Aucun"} />
                  </div>
                  <VehiculeConstat letter="A" data={data} />
                  <VehiculeConstat letter="B" data={data} />
                  {data.description_croquis && (
                    <div>
                      <SectionTitle>Croquis</SectionTitle>
                      <p className="text-sm" style={{ color: T.muted }}>{data.description_croquis}</p>
                    </div>
                  )}
                </div>
              )}

              {tab === "documents" && (
                <div className="space-y-6">
                  <div>
                    <SectionTitle>Constat scanné</SectionTitle>
                    {constats.length === 0 ? (
                      <p className="text-sm" style={{ color: T.grey }}>Aucun constat scanné disponible.</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-3">
                        {constats.map((d) => (
                          <a key={d.id} href={api.documents.url(d.gridfs_id)} target="_blank" rel="noreferrer"
                             className="flex items-center gap-2 border rounded-md p-3 text-sm hover:shadow-sm" style={{ borderColor: T.line }}>
                            <FileText size={16} color={T.accent} /> {d.filename}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <SectionTitle>Photos de dommages</SectionTitle>
                    {photos.length === 0 ? (
                      <p className="text-sm" style={{ color: T.grey }}>Aucune photo de dommages disponible.</p>
                    ) : (
                      <div className="grid grid-cols-3 gap-3">
                        {photos.map((d) => (
                          <a key={d.id} href={api.documents.url(d.gridfs_id)} target="_blank" rel="noreferrer" className="block">
                            <img
                              src={api.documents.url(d.gridfs_id)}
                              alt={d.filename}
                              className="w-full h-32 object-cover rounded-md border"
                              style={{ borderColor: T.line }}
                            />
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                  {data.pdf_path && (
                    <div>
                      <SectionTitle>Rapport d'analyse</SectionTitle>
                      <div className="flex gap-2">
                        <a href={api.sinistres.pdfUrl(data.id)} target="_blank" rel="noreferrer"
                           className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-md" style={{ color: T.accent, backgroundColor: T.accentDim }}>
                          <Eye size={13} /> Voir le rapport PDF
                        </a>
                        <a href={api.sinistres.pdfUrl(data.id, true)}
                           className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-md border" style={{ color: T.muted, borderColor: T.line }}>
                          <Download size={13} /> Télécharger
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {tab === "responsabilite" && (
                <div className="space-y-4">
                  {!data.responsabilite ? (
                    <p className="text-sm" style={{ color: T.grey }}>Aucune estimation de responsabilité disponible pour ce dossier.</p>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-lg border p-4 text-center" style={{ borderColor: T.line }}>
                          <div className="text-xs" style={{ color: T.grey }}>Véhicule A</div>
                          <div className="text-3xl f-display mt-1" style={{ fontWeight: 600, color: T.accent }}>
                            {Math.round((data.responsabilite.taux_a || 0) * 100)}%
                          </div>
                        </div>
                        <div className="rounded-lg border p-4 text-center" style={{ borderColor: T.line }}>
                          <div className="text-xs" style={{ color: T.grey }}>Véhicule B</div>
                          <div className="text-3xl f-display mt-1" style={{ fontWeight: 600, color: T.accent }}>
                            {Math.round((data.responsabilite.taux_b || 0) * 100)}%
                          </div>
                        </div>
                      </div>
                      <Fact label="Cas du barème" value={data.responsabilite.cas_type} />
                      <div>
                        <SectionTitle>Justification détaillée</SectionTitle>
                        <p className="text-sm leading-relaxed" style={{ color: T.muted }}>{data.responsabilite.justification}</p>
                      </div>
                      {data.responsabilite.elements_pris_en_compte?.length > 0 && (
                        <div>
                          <SectionTitle>Éléments pris en compte</SectionTitle>
                          <ul className="text-sm space-y-1 list-disc pl-4" style={{ color: T.muted }}>
                            {data.responsabilite.elements_pris_en_compte.map((el, i) => <li key={i}>{el}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {tab === "expertise" && (
                <div className="space-y-5">
                  <Field label="Avis d'expert" hint="Visible dès que le dossier passe en expertise.">
                    <Textarea rows={6} value={avisExpert} onChange={(e) => setAvisExpert(e.target.value)}
                              placeholder="Conclusions de l'expertise, réserves, montant estimé des dommages…" />
                  </Field>
                  <div className="grid grid-cols-2 gap-4">
                    <Field label="Statut du remboursement">
                      <Select value={statutRemb} onChange={(e) => setStatutRemb(e.target.value)}>
                        <option value="">—</option>
                        {statutsRemboursement.map((s) => <option key={s} value={s}>{s}</option>)}
                      </Select>
                    </Field>
                    <Field label="Montant remboursé (DT)">
                      <Input type="number" step="0.01" value={montantRemb} onChange={(e) => setMontantRemb(e.target.value)} placeholder="0.00" />
                    </Field>
                  </div>
                  <Field label="Date de remboursement">
                    <Input type="date" value={dateRemb ? String(dateRemb).slice(0, 10) : ""} onChange={(e) => setDateRemb(e.target.value)} />
                  </Field>
                </div>
              )}
            </div>

            {/* Pied fixe */}
            <div className="px-8 py-4 border-t flex justify-between items-center shrink-0" style={{ borderColor: T.lineLight }}>
              <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={14} /> Supprimer
              </Button>
              <Button variant="primary" onClick={handleSave} busy={saving}>
                Enregistrer
              </Button>
            </div>
          </>
        )}
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title="Supprimer ce dossier ?"
          message="Cette action est irréversible."
          confirmLabel="Supprimer"
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(false)}
          busy={deleting}
        />
      )}
    </div>
  );
}
