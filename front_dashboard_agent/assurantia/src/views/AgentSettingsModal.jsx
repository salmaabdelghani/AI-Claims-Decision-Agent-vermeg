import React, { useEffect, useState } from "react";
import { X, Play, Pause, RotateCcw, Plus, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { T, Spinner, ErrorBanner, Button, Input, useToast } from "../ui.jsx";

const TABS = [
  { key: "general", label: "Général" },
  { key: "bareme", label: "Barème de responsabilité" },
  { key: "compagnies", label: "Compagnies d'assurance" },
];

function GeneralTab() {
  const notify = useToast();
  const [config, setConfig] = useState(null);
  const [activity, setActivity] = useState(null);
  const [interval, setIntervalVal] = useState(60);
  const [saving, setSaving] = useState(false);
  const [launching, setLaunching] = useState(false);

  const load = () => {
    api.agent.getConfig().then((c) => { setConfig(c); setIntervalVal(c.polling_interval_seconds); });
    api.agent.activity().then(setActivity);
  };
  useEffect(() => {
    load();
    const id = setInterval(() => api.agent.activity().then(setActivity), 4000);
    return () => clearInterval(id);
  }, []);

  const toggleRunning = async () => {
    setSaving(true);
    try {
      const updated = await api.agent.patchConfig({ is_running: !config.is_running });
      setConfig(updated);
      notify(updated.is_running ? "File d'attente activée." : "File d'attente mise en pause.");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleLaunch = async () => {
    setLaunching(true);
    try {
      await api.agent.launch();
      notify("Processus lancé — l'agent devrait apparaître actif d'ici quelques secondes.");
      setTimeout(load, 3000);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLaunching(false);
    }
  };

  const saveInterval = async () => {
    setSaving(true);
    try {
      const updated = await api.agent.patchConfig({ polling_interval_seconds: Number(interval) });
      setConfig(updated);
      notify("Intervalle de polling mis à jour.");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!config || !activity) return <Spinner label="Chargement…" />;

  const processAlive = activity.process_alive;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border p-5" style={{ borderColor: processAlive ? T.line : T.red }}>
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: processAlive ? T.green : T.red }} />
              <div className="text-sm font-semibold">
                {processAlive ? "Processus détecté et actif" : "Processus non détecté"}
              </div>
            </div>
            <div className="text-xs mt-1" style={{ color: T.grey }}>
              {processAlive
                ? `Dernier signal il y a ${activity.seconds_since_heartbeat}s — le programme mailconnector tourne bien en arrière-plan.`
                : "Le programme ne semble pas être lancé (aucun signal récent). Cliquez pour le démarrer sans ouvrir VSCode."}
            </div>
          </div>
          {!processAlive && (
            <Button variant="primary" onClick={handleLaunch} busy={launching}>
              <Play size={14} /> Lancer le processus
            </Button>
          )}
        </div>
      </div>

      <div className="rounded-lg border p-5" style={{ borderColor: T.line }}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">File d'attente</div>
            <div className="text-xs mt-1" style={{ color: T.grey }}>
              {config.is_running
                ? "L'agent (une fois le processus actif) surveille la boîte mail et traite les déclarations reçues."
                : "En pause — même si le processus tourne, aucun nouvel email ne sera traité tant que ce n'est pas réactivé."}
            </div>
          </div>
          <Button variant={config.is_running ? "danger" : "primary"} onClick={toggleRunning} busy={saving}>
            {config.is_running ? <><Pause size={14} /> Mettre en pause</> : <><Play size={14} /> Activer</>}
          </Button>
        </div>
      </div>

      <div className="rounded-lg border p-5" style={{ borderColor: T.line }}>
        <div className="text-sm font-semibold mb-1">Intervalle de polling</div>
        <div className="text-xs mb-3" style={{ color: T.grey }}>
          Fréquence à laquelle l'agent vérifie l'arrivée de nouveaux emails (en secondes, minimum 10s).
        </div>
        <div className="flex items-center gap-3">
          <Input type="number" min={10} value={interval} onChange={(e) => setIntervalVal(e.target.value)} className="!w-32" />
          <span className="text-xs" style={{ color: T.grey }}>secondes</span>
          <Button variant="secondary" onClick={saveInterval} busy={saving}>Enregistrer</Button>
        </div>
      </div>

      <p className="text-xs" style={{ color: T.grey }}>
        Pour ne plus jamais avoir à relancer le processus manuellement (même après un redémarrage de l'ordinateur),
        configurez-le en démarrage automatique via le Planificateur de tâches Windows — voir le fichier
        <code className="mx-1 px-1 rounded" style={{ backgroundColor: T.paper }}>demarrage_automatique_windows.md</code>
        fourni à la racine du projet mailconnector.
      </p>
    </div>
  );
}

function BaremeTab() {
  const notify = useToast();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [edits, setEdits] = useState({});
  const [savingCas, setSavingCas] = useState(null);

  const load = () => api.agent.getBareme().then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const handleSave = async (cas) => {
    const e = edits[cas];
    if (!e) return;
    setSavingCas(cas);
    try {
      await api.agent.patchBareme(cas, { taux_a: Number(e.taux_a), taux_b: Number(e.taux_b) });
      notify(`Taux du cas ${cas} mis à jour.`);
      load();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setSavingCas(null);
    }
  };

  const handleReset = async (cas) => {
    setSavingCas(cas);
    try {
      await api.agent.resetBareme(cas);
      notify(`Cas ${cas} réinitialisé au taux par défaut.`);
      setEdits((prev) => { const n = { ...prev }; delete n[cas]; return n; });
      load();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setSavingCas(null);
    }
  };

  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!rows) return <Spinner label="Chargement du barème…" />;

  return (
    <div className="space-y-2">
      <p className="text-xs mb-3" style={{ color: T.grey }}>
        Seuls les taux peuvent être ajustés (les conditions de reconnaissance de chaque cas restent celles du barème
        officiel FTUSA). Un taux personnalisé remplace le taux par défaut pour tous les prochains sinistres correspondant à ce cas.
      </p>
      {rows.map((r) => {
        const edit = edits[r.cas] || { taux_a: r.taux_a_actuel, taux_b: r.taux_b_actuel };
        return (
          <div key={r.cas} className="flex items-center gap-3 border rounded-md p-3" style={{ borderColor: T.lineLight }}>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold">
                Cas {r.cas} {r.personnalise && <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px]" style={{ color: T.accent, backgroundColor: T.accentDim }}>personnalisé</span>}
              </div>
              <div className="text-xs mt-0.5" style={{ color: T.grey }}>{r.titre}</div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <Input
                type="number" step="0.01" min={0} max={1} value={edit.taux_a}
                onChange={(e) => setEdits((prev) => ({ ...prev, [r.cas]: { ...edit, taux_a: e.target.value } }))}
                className="!w-16 !text-xs"
              />
              <span className="text-xs" style={{ color: T.grey }}>A /</span>
              <Input
                type="number" step="0.01" min={0} max={1} value={edit.taux_b}
                onChange={(e) => setEdits((prev) => ({ ...prev, [r.cas]: { ...edit, taux_b: e.target.value } }))}
                className="!w-16 !text-xs"
              />
              <span className="text-xs" style={{ color: T.grey }}>B</span>
              <button onClick={() => handleSave(r.cas)} disabled={savingCas === r.cas}
                      className="text-xs font-medium px-2 py-1 rounded" style={{ color: T.accent }}>
                Enregistrer
              </button>
              {r.personnalise && (
                <button onClick={() => handleReset(r.cas)} disabled={savingCas === r.cas} title="Réinitialiser" className="p-1">
                  <RotateCcw size={13} color={T.grey} />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CompagniesTab() {
  const notify = useToast();
  const [companies, setCompanies] = useState(null);
  const [error, setError] = useState(null);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.agent.getInsuranceCompanies().then(setCompanies).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      await api.agent.addInsuranceCompany(newName.trim());
      setNewName("");
      notify("Compagnie ajoutée.");
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (nom) => {
    setBusy(true);
    try {
      await api.agent.removeInsuranceCompany(nom);
      notify("Compagnie supprimée.");
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!companies) return <Spinner label="Chargement…" />;

  return (
    <div className="space-y-4">
      <p className="text-xs" style={{ color: T.grey }}>
        Liste fermée des compagnies que l'agent peut reconnaître automatiquement sur un constat scanné. Une compagnie
        absente de cette liste sera lue comme "manquant" plutôt que devinée.
      </p>
      <div className="flex gap-2">
        <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Nom de la compagnie…" onKeyDown={(e) => e.key === "Enter" && handleAdd()} />
        <Button variant="secondary" onClick={handleAdd} busy={busy}><Plus size={14} /> Ajouter</Button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {companies.length === 0 && <p className="text-xs col-span-2" style={{ color: T.grey }}>Aucune compagnie enregistrée.</p>}
        {companies.map((nom) => (
          <div key={nom} className="flex items-center justify-between border rounded-md px-3 py-2 text-sm" style={{ borderColor: T.lineLight }}>
            {nom}
            <button onClick={() => handleRemove(nom)} disabled={busy}><Trash2 size={13} color={T.red} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AgentSettingsModal({ onClose }) {
  const [tab, setTab] = useState("general");

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6" style={{ backgroundColor: "rgba(22,33,62,0.45)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-2xl max-h-[85vh] rounded-xl overflow-hidden flex flex-col" style={{ backgroundColor: T.surface }}>
        <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: T.lineLight }}>
          <h2 className="f-display text-lg" style={{ fontWeight: 600 }}>Paramètres de l'agent</h2>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-black/5"><X size={18} /></button>
        </div>
        <div className="flex gap-1 px-6 pt-3 border-b" style={{ borderColor: T.lineLight }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
              style={{ color: tab === t.key ? T.accent : T.muted, borderColor: tab === t.key ? T.accent : "transparent" }}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-auto p-6">
          {tab === "general" && <GeneralTab />}
          {tab === "bareme" && <BaremeTab />}
          {tab === "compagnies" && <CompagniesTab />}
        </div>
      </div>
    </div>
  );
}
