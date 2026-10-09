import React, { useState, useEffect } from "react";
import {
  LayoutGrid, FileText, ShieldAlert, Users, Settings, Search, Bell, Plus, Bot,
} from "lucide-react";
import { api } from "./api.js";
import { T, ToastProvider } from "./ui.jsx";
import Dashboard from "./views/Dashboard.jsx";
import Contrats from "./views/Contrats.jsx";
import Sinistres from "./views/Sinistres.jsx";
import Clients from "./views/Clients.jsx";
import ContratForm from "./views/ContratForm.jsx";
import AgentDashboard from "./views/AgentDashboard.jsx";

/* ————————————————————————————————————————————
   ASSURANTIA — back-office assurance
   Tokens
   ink        #16213E   texte / structure
   paper      #EEF0F2   fond
   surface    #FFFFFF   cartes / panneaux
   line       #DADFE3   bordures
   accent     #2F5D8A   interaction / liens / actif
   accent-dim #E4EBF1   fond léger accent
   gold       #C68A2E   avertissement / en attente
   green      #3A7D5C   validé / actif
   red        #B4483A   refusé / résilié
   grey       #8B8F94   neutre / clôturé
   Display: Fraunces (institutionnelle, un peu de caractère)
   Body: Inter
   Data: IBM Plex Mono (références, montants, dates)
—————————————————————————————————————————————— */

const FONT_LINK = (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
    .f-display { font-family: 'Fraunces', serif; }
    .f-body { font-family: 'Inter', sans-serif; }
    .f-mono { font-family: 'IBM Plex Mono', monospace; }
  `}</style>
);

const NAV = [
  { key: "dashboard", label: "Tableau de bord", icon: LayoutGrid },
  { key: "contrats", label: "Contrats", icon: FileText },
  { key: "sinistres", label: "Sinistres", icon: ShieldAlert },
  { key: "clients", label: "Clients", icon: Users },
];

function AssurBackInner() {
  const [view, setView] = useState("dashboard");
  const [query, setQuery] = useState("");
  const [meta, setMeta] = useState(null);
  const [apiDown, setApiDown] = useState(false);
  const [newContrat, setNewContrat] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentBadge, setAgentBadge] = useState(0);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setApiDown(true));
    api.health().catch(() => setApiDown(true));
  }, []);

  // Badge "à traiter" de l'icône Agent — visible depuis n'importe quelle
  // fenêtre du logiciel, actualisé périodiquement même quand le dashboard
  // Agent est fermé (suivi en temps réel du travail de l'agent).
  useEffect(() => {
    const refresh = () => api.agent.stats().then((s) => setAgentBadge(s.a_traiter || 0)).catch(() => {});
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="f-body flex h-full min-h-[720px] w-full" style={{ backgroundColor: T.paper, color: T.ink }}>
      {FONT_LINK}

      {/* Sidebar */}
      <aside className="w-60 shrink-0 flex flex-col justify-between" style={{ backgroundColor: T.ink, color: T.paper }}>
        <div>
          <div className="px-6 py-6 border-b" style={{ borderColor: "#2A3A5C" }}>
            <div className="f-display text-xl tracking-tight" style={{ fontWeight: 600 }}>Assurantia</div>
            <div className="text-[11px] mt-0.5 opacity-60 f-mono tracking-wide">BACK-OFFICE</div>
          </div>

          <nav className="px-3 py-5 space-y-1">
            {NAV.map((item) => {
              const Icon = item.icon;
              const active = view === item.key;
              return (
                <button
                  key={item.key}
                  onClick={() => setView(item.key)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors"
                  style={{
                    backgroundColor: active ? T.accent : "transparent",
                    color: active ? "#FFFFFF" : "#B7C0D1",
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  <Icon size={17} strokeWidth={1.8} />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="px-3 pb-5">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm" style={{ color: "#8592AA" }}>
            <Settings size={17} strokeWidth={1.8} />
            Paramètres
          </button>
          <div className="mt-4 mx-3 pt-4 border-t flex items-center gap-2.5" style={{ borderColor: "#2A3A5C" }}>
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold" style={{ backgroundColor: T.accent }}>
              SA
            </div>
            <div className="leading-tight">
              <div className="text-sm">Salma Abdelghani</div>
              <div className="text-[11px] opacity-60">Gestionnaire</div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="flex items-center justify-between px-8 py-4 border-b shrink-0" style={{ borderColor: T.line, backgroundColor: "#F7F8F9" }}>
          <div className="flex items-center gap-2 px-3 py-2 rounded-md w-80" style={{ backgroundColor: T.paper }}>
            <Search size={15} color={T.grey} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Rechercher un client, un contrat…"
              className="bg-transparent text-sm outline-none w-full placeholder:text-[#8B8F94]"
              aria-label="Rechercher"
            />
          </div>
          <div className="flex items-center gap-4">
            <button className="relative p-2 rounded-md hover:bg-black/5" aria-label="Notifications">
              <Bell size={18} strokeWidth={1.8} />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full" style={{ backgroundColor: T.red }} />
            </button>
            <button
              onClick={() => setNewContrat(true)}
              className="flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-md font-medium"
              style={{ backgroundColor: T.accent, color: "#fff" }}
            >
              <Plus size={15} /> Nouveau contrat
            </button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-8">
          {apiDown && (
            <div className="mb-6 rounded-md border px-4 py-3 text-sm" style={{ borderColor: T.red, backgroundColor: "#F5E5E1", color: T.red }}>
              Impossible de joindre l'API Assurantia. Vérifiez qu'elle est démarrée
              (<code className="f-mono">uvicorn app.main:app --port 8000</code> dans <code className="f-mono">assurantia-api/</code>)
              et que <code className="f-mono">VITE_API_URL</code> pointe vers la bonne adresse.
            </div>
          )}
          {view === "dashboard" && <Dashboard />}
          {view === "contrats" && <Contrats query={query} meta={meta} />}
          {view === "sinistres" && <Sinistres query={query} meta={meta} />}
          {view === "clients" && <Clients query={query} />}
        </main>
      </div>

      {newContrat && (
        <ContratForm contratId={null} onClose={() => setNewContrat(false)} onSaved={() => setNewContrat(false)} />
      )}

      {/* Icône Agent — flottante, accessible depuis toutes les fenêtres du
          logiciel, ouvre le dashboard de suivi du traitement automatique
          des sinistres par l'agent email. */}
      <button
        onClick={() => setAgentOpen(true)}
        aria-label="Ouvrir le dashboard de l'agent de traitement des sinistres"
        title="Agent — traitement automatique des sinistres"
        className="fixed bottom-6 right-6 z-[80] w-14 h-14 rounded-full flex items-center justify-center shadow-lg transition-transform hover:scale-105"
        style={{ backgroundColor: T.ink }}
      >
        <Bot size={24} color="#fff" strokeWidth={1.8} />
        {agentBadge > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full flex items-center justify-center text-[11px] font-semibold f-mono"
            style={{ backgroundColor: T.red, color: "#fff" }}
          >
            {agentBadge > 99 ? "99+" : agentBadge}
          </span>
        )}
      </button>

      {agentOpen && (
        <AgentDashboard
          onClose={() => setAgentOpen(false)}
          onViewInSinistres={(numeroDossier) => {
            setQuery(numeroDossier);
            setView("sinistres");
            setAgentOpen(false);
          }}
        />
      )}
    </div>
  );
}

export default function AssurBack() {
  return (
    <ToastProvider>
      <AssurBackInner />
    </ToastProvider>
  );
}
