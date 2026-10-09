import React, { useState, useEffect } from "react";
import {
  Bot, X, Search, RefreshCw, Download, Eye, ChevronDown, ChevronUp,
  CheckCircle2, XCircle, AlertTriangle, Clock, CheckCheck,
  ArrowRight, FileText, Mail, ScanSearch, Paperclip, ScanText,
  ShieldCheck, Image as ImageIcon, Scale, Flag, Moon, Settings as SettingsIcon,
  ImagePlus, Save, Pencil,
} from "lucide-react";
import { api } from "../api.js";
import { T, StatusBadge, RefStamp, Spinner, ErrorBanner, Button, useToast } from "../ui.jsx";
import AgentSettingsModal from "./AgentSettingsModal.jsx";

/* ————————————————————————————————————————————
   Dashboard "Agent" — meme identite visuelle que le dashboard de gestion
   (design tokens T communs), pour rester coherent avec le reste du
   logiciel plutot que de creer un espace visuellement a part.

   File unique (plus d'onglet "A traiter" / "Traites" : des qu'un dossier
   est confirme+transmis ou marque traite, il quitte simplement la liste —
   son historique vit desormais dans le dashboard Sinistres principal).
—————————————————————————————————————————————— */

const OUTCOME_STYLE = {
  ok: { color: T.green, Icon: CheckCircle2 },
  ko: { color: T.red, Icon: XCircle },
  warning: { color: T.gold, Icon: AlertTriangle },
  pending: { color: T.grey, Icon: Clock },
};

const CIRCONSTANCES_LABELS = {
  en_stationnement: "En stationnement",
  quittait_stationnement: "Quittait un stationnement",
  prenait_stationnement: "Prenait un stationnement",
  sortait_parking: "Sortait d'un parking / lieu privé",
  engageait_giratoire: "S'engageait dans un giratoire",
  circulait_giratoire: "Circulait dans un giratoire",
  heurtait_arriere: "Heurtait à l'arrière",
  meme_sens_meme_file: "Même sens, même file",
  changeait_file: "Changeait de file",
  depassait: "Doublait ou dépassait",
  virait_droite: "Virait à droite",
  virait_gauche: "Virait à gauche",
  reculait: "Reculait",
  empiete_sens_inverse: "Empiétait sur la voie inverse",
  venait_droite: "Venait de droite",
  non_prioritaire: "N'avait pas la priorité",
};

const STEP_META = [
  { key: "reception", label: "Réception", Icon: Mail },
  { key: "detection", label: "Détection", Icon: ScanSearch },
  { key: "documents", label: "Documents", Icon: Paperclip },
  { key: "ocr", label: "Constat", Icon: ScanText },
  { key: "contrat", label: "Contrat", Icon: ShieldCheck },
  { key: "photos", label: "Photos", Icon: ImageIcon },
  { key: "responsabilite", label: "Responsabilité", Icon: Scale },
  { key: "decision", label: "Décision", Icon: Flag },
];

function relativeTime(iso) {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.round(diffMs / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.round(h / 24)} j`;
}

function useElapsedSeconds(since) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!since) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [since]);
  if (!since) return 0;
  return Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
}

/* ————————————————————————————————————————————
   Panneau d'activite en direct — visualisation par etapes, pas une ligne
—————————————————————————————————————————————— */
function ActivityPanel() {
  const [activity, setActivity] = useState(null);

  useEffect(() => {
    const refresh = () => api.agent.activity().then(setActivity).catch(() => {});
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, []);

  const elapsed = useElapsedSeconds(activity?.started_at);
  const currentIndex = activity && !activity.is_idle ? STEP_META.findIndex((s) => s.key === activity.step) : -1;

  return (
    <div className="px-8 py-5 shrink-0 border-b" style={{ backgroundColor: T.surface, borderColor: T.line }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2.5 w-2.5">
            {activity && !activity.is_idle && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: T.accent }} />
            )}
            <span
              className="relative inline-flex rounded-full h-2.5 w-2.5"
              style={{ backgroundColor: activity && !activity.is_idle ? T.accent : T.grey }}
            />
          </span>
          <span className="text-sm font-semibold" style={{ color: T.ink }}>
            {activity && !activity.is_idle ? "Agent en cours de traitement" : "Agent au repos"}
          </span>
          {activity && !activity.is_idle && (
            <span className="text-xs f-mono px-2 py-0.5 rounded-full" style={{ color: T.accent, backgroundColor: T.accentDim }}>
              {elapsed}s
            </span>
          )}
        </div>
        {activity && !activity.is_idle ? (
          <span className="text-xs truncate max-w-[50%]" style={{ color: T.grey }}>
            {activity.sender} {activity.subject && `— « ${activity.subject} »`}
          </span>
        ) : (
          <span className="text-xs flex items-center gap-1.5" style={{ color: T.grey }}>
            <Moon size={12} /> En attente du prochain email…
          </span>
        )}
      </div>

      {/* Stepper visuel */}
      <div className="flex items-center">
        {STEP_META.map((s, i) => {
          const isDone = currentIndex >= 0 && i < currentIndex;
          const isCurrent = i === currentIndex;
          const Icon = s.Icon;
          const color = isCurrent ? T.accent : isDone ? T.green : T.grey;
          return (
            <React.Fragment key={s.key}>
              <div className="flex flex-col items-center gap-1.5" style={{ width: 84 }}>
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center relative"
                  style={{ backgroundColor: isCurrent ? T.accentDim : `${color}1A`, border: isCurrent ? `1.5px solid ${T.accent}` : "1.5px solid transparent" }}
                >
                  {isCurrent && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-40" style={{ backgroundColor: T.accent }} />
                  )}
                  <Icon size={14} color={color} strokeWidth={2} className="relative" />
                </div>
                <span className="text-[10.5px] text-center leading-tight" style={{ color: isCurrent ? T.ink : T.muted, fontWeight: isCurrent ? 600 : 400 }}>
                  {s.label}
                </span>
              </div>
              {i < STEP_META.length - 1 && (
                <div className="flex-1 h-px -mt-4" style={{ backgroundColor: isDone ? T.green : T.line }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

/* ————————————————————————————————————————————
   Contenu detaille par etape (l'objet concerne)
—————————————————————————————————————————————— */
function KV({ label, value }) {
  return (
    <div className="text-xs">
      <span style={{ color: T.grey }}>{label} : </span>
      <span style={{ color: T.ink }}>{value ?? "—"}</span>
    </div>
  );
}

function DocumentThumb({ doc }) {
  const isImage = /\.(png|jpe?g|gif|webp)$/i.test(doc.filename || "");
  return (
    <a href={api.documents.url(doc.gridfs_id)} target="_blank" rel="noreferrer"
       className="flex items-center gap-2 border rounded-md p-2 text-xs hover:shadow-sm" style={{ borderColor: T.line }}>
      {isImage ? (
        <img src={api.documents.url(doc.gridfs_id)} alt={doc.filename} className="w-10 h-10 object-cover rounded" />
      ) : (
        <FileText size={16} color={T.accent} />
      )}
      <div>
        <div className="font-medium">{doc.filename}</div>
        <div style={{ color: T.grey }}>{doc.nature}</div>
      </div>
    </a>
  );
}

function VehiculeOcrCard({ letter, veh, circonstances }) {
  const auto = veh?.vehicule || {};
  const ass = veh?.assurance || {};
  const circ = veh?.circulation || {};
  const coches = Object.entries(circonstances || {}).filter(([, v]) => v === true).map(([k]) => k);
  return (
    <div className="border rounded-md p-3 space-y-1.5" style={{ borderColor: T.lineLight }}>
      <div className="text-xs font-semibold mb-1">Véhicule {letter}</div>
      <KV label="Marque / modèle" value={[auto.marque, auto.type_modele].filter(Boolean).join(" ")} />
      <KV label="Immatriculation" value={auto.immatriculation} />
      <KV label="Assurance" value={[ass.societe, ass.numero_police].filter(Boolean).join(" — ")} />
      <KV label="Point de choc" value={circ.point_choc} />
      <KV label="Dégâts apparents" value={circ.degats_apparents} />
      {coches.length > 0 && (
        <div className="pt-1">
          <div className="text-[11px]" style={{ color: T.grey }}>Circonstances cochées :</div>
          <ul className="text-xs list-disc pl-4">
            {coches.map((k) => <li key={k}>{CIRCONSTANCES_LABELS[k] || k}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function StepDetail({ step }) {
  const d = step.data;
  if (!d) return <p className="text-xs" style={{ color: T.grey }}>Aucune donnée disponible pour cette étape.</p>;

  switch (step.key) {
    case "reception":
      return (
        <div className="space-y-1">
          <KV label="Expéditeur" value={d.sender} />
          <KV label="Objet" value={d.subject} />
          <KV label="Date de l'email" value={d.email_date} />
        </div>
      );
    case "detection":
      return (
        <div className="space-y-1">
          <KV label="Type" value={d.sinistre_type} />
          <KV label="Confiance" value={d.confidence != null ? `${Math.round(d.confidence * 100)} %` : "—"} />
          {d.reason && <KV label="Raison" value={d.reason} />}
        </div>
      );
    case "documents":
      return Array.isArray(d) && d.length > 0 ? (
        <div className="grid grid-cols-2 gap-2">{d.map((doc) => <DocumentThumb key={doc.id} doc={doc} />)}</div>
      ) : (
        <p className="text-xs" style={{ color: T.grey }}>Aucun document reçu pour l'instant.</p>
      );
    case "ocr":
      if (d.error) return <p className="text-xs" style={{ color: T.red }}>Échec OCR : {d.error}</p>;
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <KV label="Date accident" value={d.accident?.date} />
            <KV label="Lieu" value={d.accident?.lieu} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <VehiculeOcrCard letter="A" veh={d.vehicule_a} circonstances={d.circonstances_a} />
            <VehiculeOcrCard letter="B" veh={d.vehicule_b} circonstances={d.circonstances_b} />
          </div>
          {d.description_croquis && <KV label="Croquis" value={d.description_croquis} />}
        </div>
      );
    case "contrat":
      return (
        <div className="space-y-1">
          <KV label="Trouvé" value={d.found ? "Oui" : "Non"} />
          {d.found && (
            <>
              <KV label="N° police" value={d.num_police} />
              <KV label="Contrat" value={d.contrat_id} />
              <KV label="Véhicule concerné" value={d.party} />
              <KV label="Valide" value={d.valid ? "Oui" : "Non"} />
              <KV label="Cohérent avec le constat" value={d.coherent === false ? "Non" : "Oui"} />
            </>
          )}
          {d.invalid_reason && <KV label="Motif" value={d.invalid_reason} />}
          {d.mismatches?.length > 0 && (
            <ul className="text-xs list-disc pl-4 mt-1" style={{ color: T.gold }}>
              {d.mismatches.map((m, i) => <li key={i}>{m.champ} — constat : « {m.constat} » / base : « {m.contrat} »</li>)}
            </ul>
          )}
        </div>
      );
    case "photos":
      return (
        <div className="space-y-2">
          <KV label="Explication" value={d.explication} />
          {d.details && (
            <div className="grid grid-cols-1 gap-1 mt-1">
              {["coherence_inter_photos", "coherence_points_choc_degats", "coherence_croquis_circonstances"].map((k) => {
                const sc = d.details[k];
                if (!sc) return null;
                const ok = sc.coherent;
                return (
                  <div key={k} className="text-xs flex items-start gap-1.5">
                    <span style={{ color: ok ? T.green : ok === false ? T.red : T.gold }}>●</span>
                    <span>{sc.explication}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      );
    case "responsabilite":
      return (
        <div className="space-y-2">
          <div className="flex gap-4">
            <KV label="Taux A" value={`${Math.round((d.taux_a || 0) * 100)} %`} />
            <KV label="Taux B" value={`${Math.round((d.taux_b || 0) * 100)} %`} />
            <KV label="Cas" value={d.cas_type} />
          </div>
          <p className="text-xs" style={{ color: T.muted }}>{d.justification}</p>
          {d.elements_pris_en_compte?.length > 0 && (
            <ul className="text-xs list-disc pl-4" style={{ color: T.muted }}>
              {d.elements_pris_en_compte.map((el, i) => <li key={i}>{el}</li>)}
            </ul>
          )}
        </div>
      );
    case "decision":
      return <div className="space-y-1"><KV label="Statut" value={d.status} />{d.note && <KV label="Note" value={d.note} />}</div>;
    default:
      return null;
  }
}

function Timeline({ steps }) {
  const [openStep, setOpenStep] = useState(null);
  if (!steps?.length) return null;
  return (
    <div className="mt-1">
      {steps.map((s, i) => {
        const style = OUTCOME_STYLE[s.outcome] || OUTCOME_STYLE.pending;
        const Icon = style.Icon;
        const isLast = i === steps.length - 1;
        const isOpen = openStep === s.key;
        return (
          <div key={s.key} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className="w-6 h-6 rounded-full flex items-center justify-center shrink-0" style={{ backgroundColor: `${style.color}1A` }}>
                <Icon size={13} color={style.color} strokeWidth={2.4} />
              </div>
              {!isLast && <div className="w-px flex-1 my-0.5" style={{ backgroundColor: T.line, minHeight: 16 }} />}
            </div>
            <div className="pb-4 min-w-0 flex-1">
              <button onClick={() => setOpenStep(isOpen ? null : s.key)} className="flex items-center gap-1.5 text-left w-full">
                <span className="text-sm font-medium" style={{ color: T.ink }}>{s.label}</span>
                {s.data && (isOpen ? <ChevronUp size={12} color={T.grey} /> : <ChevronDown size={12} color={T.grey} />)}
              </button>
              <div className="text-xs mt-0.5 leading-relaxed" style={{ color: T.muted }}>{s.detail}</div>
              {isOpen && s.data && (
                <div className="mt-2 p-3 rounded-md" style={{ backgroundColor: T.paper }}>
                  <StepDetail step={s} />
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ————————————————————————————————————————————
   Dossier final (vue consolidee, pret a transmettre)
—————————————————————————————————————————————— */
function EditableField({ label, value, onChange }) {
  return (
    <div>
      <div className="text-[11px]" style={{ color: T.grey }}>{label}</div>
      <input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-xs mt-0.5 px-2 py-1.5 rounded border outline-none"
        style={{ borderColor: T.line, color: T.ink }}
      />
    </div>
  );
}

function EditableVehiculeCard({ letter, veh, onChange }) {
  const auto = veh?.vehicule || {};
  const ass = veh?.assurance || {};
  const circ = veh?.circulation || {};

  const set = (section, field) => (value) => {
    onChange({
      ...veh,
      [section]: { ...(veh?.[section] || {}), [field]: value },
    });
  };

  return (
    <div className="border rounded-md p-3 space-y-2" style={{ borderColor: T.lineLight }}>
      <div className="text-xs font-semibold mb-1">Véhicule {letter}</div>
      <div className="grid grid-cols-2 gap-2">
        <EditableField label="Marque" value={auto.marque} onChange={set("vehicule", "marque")} />
        <EditableField label="Modèle" value={auto.type_modele} onChange={set("vehicule", "type_modele")} />
      </div>
      <EditableField label="Immatriculation" value={auto.immatriculation} onChange={set("vehicule", "immatriculation")} />
      <div className="grid grid-cols-2 gap-2">
        <EditableField label="Compagnie d'assurance" value={ass.societe} onChange={set("assurance", "societe")} />
        <EditableField label="N° police" value={ass.numero_police} onChange={set("assurance", "numero_police")} />
      </div>
      <EditableField label="Point de choc" value={circ.point_choc} onChange={set("circulation", "point_choc")} />
      <EditableField label="Dégâts apparents" value={circ.degats_apparents} onChange={set("circulation", "degats_apparents")} />
    </div>
  );
}

function DossierFinal({ item, onCorrected }) {
  const notify = useToast();
  const [ocr, setOcr] = useState(item.ocr_json);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const editable = !item.transmis;

  useEffect(() => { setOcr(item.ocr_json); setDirty(false); }, [item.ocr_json]);

  if (!ocr) {
    return <p className="text-xs" style={{ color: T.grey }}>Constat non exploitable — dossier final indisponible.</p>;
  }

  const updateVeh = (key) => (newVeh) => {
    setOcr((prev) => ({ ...prev, [key]: newVeh }));
    setDirty(true);
  };
  const updateAccident = (field) => (value) => {
    setOcr((prev) => ({ ...prev, accident: { ...(prev.accident || {}), [field]: value } }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.agent.correctOcr(item.id, ocr);
      notify("Corrections enregistrées.");
      setDirty(false);
      onCorrected?.();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.agent.addPhoto(item.id, file);
      notify("Photo ajoutée au dossier.");
      onCorrected?.();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  return (
    <div className="space-y-4">
      {editable ? (
        <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-md" style={{ color: T.accent, backgroundColor: T.accentDim }}>
          <Pencil size={13} /> Champs modifiables — corrigez une donnée mal lue par l'OCR avant de confirmer le dossier.
        </div>
      ) : (
        <p className="text-xs" style={{ color: T.grey }}>Dossier déjà transmis — non modifiable ici.</p>
      )}

      <div className="grid grid-cols-2 gap-2">
        <EditableField label="Date de l'accident" value={ocr.accident?.date} onChange={updateAccident("date")} />
        <EditableField label="Lieu" value={ocr.accident?.lieu} onChange={updateAccident("lieu")} />
      </div>

      {editable ? (
        <div className="grid grid-cols-2 gap-2">
          <EditableVehiculeCard letter="A" veh={ocr.vehicule_a} onChange={updateVeh("vehicule_a")} />
          <EditableVehiculeCard letter="B" veh={ocr.vehicule_b} onChange={updateVeh("vehicule_b")} />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <VehiculeOcrCard letter="A" veh={ocr.vehicule_a} circonstances={ocr.circonstances_a} />
          <VehiculeOcrCard letter="B" veh={ocr.vehicule_b} circonstances={ocr.circonstances_b} />
        </div>
      )}

      {editable && (
        <div className="flex justify-end">
          <Button variant="primary" busy={saving} disabled={!dirty} onClick={handleSave} className="!py-1.5 !px-3 !text-xs">
            <Save size={13} /> Enregistrer les corrections
          </Button>
        </div>
      )}

      {item.responsabilite && (
        <div className="border rounded-md p-3" style={{ borderColor: T.lineLight }}>
          <div className="text-xs font-semibold mb-1">Responsabilité proposée</div>
          <KV label="Taux" value={`A ${Math.round((item.responsabilite.taux_a || 0) * 100)}% / B ${Math.round((item.responsabilite.taux_b || 0) * 100)}%`} />
          <p className="text-xs mt-1" style={{ color: T.muted }}>{item.responsabilite.justification}</p>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold">Documents du dossier</div>
          {editable && (
            <label className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md border cursor-pointer" style={{ color: T.accent, borderColor: T.line }}>
              <ImagePlus size={13} /> {uploading ? "Envoi…" : "Ajouter une photo"}
              <input type="file" accept="image/*" className="hidden" onChange={handleUpload} disabled={uploading} />
            </label>
          )}
        </div>
        {item.documents?.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">{item.documents.map((doc) => <DocumentThumb key={doc.id} doc={doc} />)}</div>
        ) : (
          <p className="text-xs" style={{ color: T.grey }}>Aucun document.</p>
        )}
      </div>
    </div>
  );
}

/* ————————————————————————————————————————————
   Actions de confirmation / transmission
—————————————————————————————————————————————— */
function ActionBar({ item, onToggleStatut, onConfirm, busy, onViewInSinistres }) {
  if (item.transmis) {
    return (
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md" style={{ color: T.green, backgroundColor: T.greenBg }}>
          <CheckCheck size={13} /> Transmis — {item.numero_dossier}
        </span>
        <button
          onClick={() => onViewInSinistres(item.numero_dossier)}
          className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md border"
          style={{ color: T.accent, borderColor: T.line }}
        >
          Voir dans Sinistres <ArrowRight size={12} />
        </button>
      </div>
    );
  }

  if (item.status === "A_TRAITER") {
    return (
      <Button variant="primary" busy={busy} onClick={() => onConfirm(item)} className="!py-1.5 !px-3 !text-xs">
        <CheckCheck size={13} /> Confirmer et transmettre
      </Button>
    );
  }

  return (
    <Button variant="ghost" busy={busy} onClick={() => onToggleStatut(item)} className="!py-1.5 !px-2.5 !text-xs">
      <CheckCheck size={13} /> Marquer traité
    </Button>
  );
}

/* ————————————————————————————————————————————
   Carte sinistre
—————————————————————————————————————————————— */
function PdfActions({ item }) {
  if (!item.pdf_available) {
    return <span className="text-xs" style={{ color: T.grey }}>Rapport PDF non disponible</span>;
  }
  return (
    <div className="flex items-center gap-1.5">
      <a href={api.agent.pdfUrl(item.id)} target="_blank" rel="noreferrer"
         className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md" style={{ color: T.accent, backgroundColor: T.accentDim }}>
        <Eye size={13} /> Rapport
      </a>
      <a href={api.agent.pdfUrl(item.id, true)}
         className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md border" style={{ color: T.muted, borderColor: T.line }}>
        <Download size={13} />
      </a>
    </div>
  );
}

function SinistreCard({ item, onToggleStatut, onConfirm, busy, onViewInSinistres, onCorrected }) {
  const [section, setSection] = useState(null);

  return (
    <div className="rounded-lg border" style={{ borderColor: T.line, backgroundColor: T.surface }}>
      <div className="p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <RefStamp>SIN-{String(item.id).padStart(5, "0")}</RefStamp>
              <StatusBadge status={item.status} />
              {item.numero_dossier && <span className="text-xs f-mono" style={{ color: T.grey }}>{item.numero_dossier}</span>}
            </div>
            <div className="mt-2 text-sm font-medium">{item.sender || "Expéditeur inconnu"}</div>
            {item.subject && <div className="text-xs mt-0.5" style={{ color: T.grey }}>{item.subject}</div>}
            <div className="text-[11px] f-mono mt-1" style={{ color: T.grey }}>
              Créé le {item.created_at ? new Date(item.created_at).toLocaleString("fr-FR") : "—"}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-xs f-mono" style={{ color: T.grey }}>{relativeTime(item.updated_at)}</div>
            {item.num_police && <div className="text-xs f-mono mt-1" style={{ color: T.muted }}>Police {item.num_police}</div>}
            {item.responsabilite_resume && <div className="text-xs mt-1 font-medium" style={{ color: T.accent }}>Resp. {item.responsabilite_resume}</div>}
          </div>
        </div>

        <div className="flex items-center justify-between mt-4 pt-3 border-t flex-wrap gap-2" style={{ borderColor: T.lineLight }}>
          <div className="flex items-center gap-3">
            <button onClick={() => setSection(section === "suivi" ? null : "suivi")} className="flex items-center gap-1 text-xs font-medium" style={{ color: T.accent }}>
              {section === "suivi" ? <ChevronUp size={14} /> : <ChevronDown size={14} />} Suivi du traitement
            </button>
            <button onClick={() => setSection(section === "final" ? null : "final")} className="flex items-center gap-1 text-xs font-medium" style={{ color: T.accent }}>
              {section === "final" ? <ChevronUp size={14} /> : <ChevronDown size={14} />} Dossier final
            </button>
          </div>
          <div className="flex items-center gap-2">
            <PdfActions item={item} />
            <ActionBar item={item} onToggleStatut={onToggleStatut} onConfirm={onConfirm} busy={busy} onViewInSinistres={onViewInSinistres} />
          </div>
        </div>

        {section === "suivi" && (
          <div className="mt-4 pt-4 border-t" style={{ borderColor: T.lineLight }}>
            <Timeline steps={item.chronogram} />
          </div>
        )}
        {section === "final" && (
          <div className="mt-4 pt-4 border-t" style={{ borderColor: T.lineLight }}>
            <DossierFinal item={item} onCorrected={onCorrected} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ————————————————————————————————————————————
   Dashboard principal — file unique (plus d'onglets)
—————————————————————————————————————————————— */
export default function AgentDashboard({ onClose, onViewInSinistres }) {
  const notify = useToast();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const load = React.useCallback(
    (silent = false) => {
      if (!silent) setLoading(true);
      setError(null);
      Promise.all([api.agent.list({ tab: "a_traiter", q }), api.agent.stats()])
        .then(async ([list, s]) => {
          const full = await Promise.all(list.map((item) => api.agent.get(item.id).catch(() => item)));
          setRows(full);
          setStats(s);
          setLastRefresh(new Date());
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    },
    [q]
  );

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const id = setInterval(() => load(true), 20000);
    return () => clearInterval(id);
  }, [load]);

  const handleToggle = async (item) => {
    setBusyId(item.id);
    try {
      await api.agent.patch(item.id, { dashboard_statut: "traite" });
      notify(`Dossier SIN-${item.id} marqué comme traité.`);
      load(true);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusyId(null);
    }
  };

  const handleConfirm = async (item) => {
    setBusyId(item.id);
    try {
      const res = await api.agent.confirm(item.id);
      notify(`Dossier transmis au dashboard Sinistres — n° ${res.numero_dossier}.`);
      load(true);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[95] flex flex-col f-body" style={{ backgroundColor: T.paper, color: T.ink }}>
      <div className="flex items-center justify-between px-8 py-5 border-b shrink-0" style={{ borderColor: T.line, backgroundColor: T.surface }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: T.ink }}>
            <Bot size={20} color="#fff" strokeWidth={1.8} />
          </div>
          <div>
            <h1 className="f-display text-xl" style={{ fontWeight: 600 }}>Agent — Traitement automatique des sinistres</h1>
            <p className="text-xs mt-0.5" style={{ color: T.grey }}>
              File d'attente — {stats?.a_traiter ?? "…"} dossier(s) à examiner
              {lastRefresh && ` · actualisé à ${lastRefresh.toLocaleTimeString("fr-FR")}`}
            </p>
          </div>
        </div>
        <button onClick={onClose} aria-label="Fermer le dashboard agent" className="p-2 rounded-md hover:bg-black/5">
          <X size={20} />
        </button>
      </div>

      <div className="px-8 py-2.5 border-b flex justify-end" style={{ borderColor: T.line, backgroundColor: T.surface }}>
        <button
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md border"
          style={{ color: T.muted, borderColor: T.line }}
        >
          <SettingsIcon size={13} /> Paramètres de l'agent
        </button>
      </div>

      {settingsOpen && <AgentSettingsModal onClose={() => setSettingsOpen(false)} />}

      <ActivityPanel />

      <div className="flex items-center justify-between gap-4 px-8 py-4 border-b shrink-0" style={{ borderColor: T.line, backgroundColor: T.surface }}>
        <div className="flex items-center gap-2 px-3 py-2 rounded-md w-80" style={{ backgroundColor: T.paper }}>
          <Search size={14} color={T.grey} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Expéditeur, objet, n° police…"
            className="bg-transparent text-sm outline-none w-full placeholder:text-[#8B8F94]"
            aria-label="Rechercher un dossier"
          />
        </div>
        <button onClick={() => load()} className="p-2 rounded-md hover:bg-black/5" aria-label="Rafraîchir" title="Rafraîchir">
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex-1 overflow-auto px-8 py-6">
        <div className="max-w-4xl mx-auto space-y-3">
          {loading && rows.length === 0 && <Spinner label="Chargement des dossiers…" />}
          {error && <ErrorBanner message={error} onRetry={() => load()} />}
          {!loading && !error && rows.length === 0 && (
            <div className="text-center py-16">
              <p className="text-sm" style={{ color: T.muted }}>Aucun dossier à examiner pour l'instant.</p>
              <p className="text-xs mt-1" style={{ color: T.grey }}>
                Les dossiers apparaissent ici dès qu'un email de déclaration est traité par l'agent.
              </p>
            </div>
          )}
          {rows.map((item) => (
            <SinistreCard
              key={item.id}
              item={item}
              onToggleStatut={handleToggle}
              onConfirm={handleConfirm}
              busy={busyId === item.id}
              onViewInSinistres={onViewInSinistres}
              onCorrected={() => load(true)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
