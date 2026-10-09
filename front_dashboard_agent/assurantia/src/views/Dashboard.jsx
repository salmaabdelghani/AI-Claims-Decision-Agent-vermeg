import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { T, Spinner, ErrorBanner, StatusBadge } from "../ui.jsx";

function StatCard({ label, value, sub, accent }) {
  return (
    <div className="rounded-lg p-5 border" style={{ backgroundColor: T.surface, borderColor: T.line }}>
      <div className="text-xs f-mono uppercase tracking-wide" style={{ color: T.grey }}>
        {label}
      </div>
      <div className="f-display text-3xl mt-2" style={{ fontWeight: 600, color: accent || T.ink }}>
        {value}
      </div>
      <div className="text-xs mt-1" style={{ color: T.grey }}>
        {sub}
      </div>
    </div>
  );
}

const MOIS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    api.dashboard
      .stats()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <Spinner label="Chargement du tableau de bord…" />;
  if (error) return <ErrorBanner message={`Impossible de charger les indicateurs : ${error}`} onRetry={load} />;

  const monthlyMap = Object.fromEntries((stats.sinistres_par_mois || []).map((m) => [String(parseInt(m.mois, 10)), m.n]));
  const monthly = Array.from({ length: 12 }, (_, i) => monthlyMap[String(i + 1)] || 0);
  const max = Math.max(1, ...monthly);
  const currentMonth = new Date().getMonth();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="f-display text-2xl" style={{ fontWeight: 600 }}>
          Tableau de bord
        </h1>
        <p className="text-sm mt-1" style={{ color: T.muted }}>
          Vue d'ensemble du portefeuille — donnees en temps reel
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Contrats actifs" value={stats.contrats_actifs} sub={`${stats.total_contrats} contrats au total`} />
        <StatCard
          label="Sinistres en cours"
          value={stats.sinistres_en_cours}
          sub={`${stats.total_sinistres} dossiers au total`}
          accent={T.gold}
        />
        <StatCard
          label="Primes encaissées"
          value={`${Math.round(stats.primes_encaissees).toLocaleString("fr-FR")} DT`}
          sub="Contrats actifs, cumul annuel"
          accent={T.green}
        />
        <StatCard label="Taux de sinistralité" value={`${stats.taux_sinistralite} %`} sub="Sinistres / contrats actifs" />
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 rounded-lg p-6 border" style={{ backgroundColor: T.surface, borderColor: T.line }}>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-sm font-semibold">Sinistres déclarés par mois</h2>
            <span className="text-xs f-mono" style={{ color: T.grey }}>
              {new Date().getFullYear()}
            </span>
          </div>
          <div className="flex items-end gap-2 h-40">
            {monthly.map((v, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-2">
                <div
                  className="w-full rounded-sm transition-all"
                  style={{
                    height: `${Math.max((v / max) * 100, v > 0 ? 4 : 1)}%`,
                    backgroundColor: i === currentMonth ? T.accent : "#C7D4E1",
                  }}
                  title={`${v} sinistre(s)`}
                />
                <span className="text-[10px] f-mono" style={{ color: T.grey }}>
                  {MOIS[i]}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg p-6 border" style={{ backgroundColor: T.surface, borderColor: T.line }}>
          <h2 className="text-sm font-semibold mb-4">Activité récente</h2>
          {stats.activite_recente?.length ? (
            <ul className="space-y-4">
              {stats.activite_recente.map((a, i) => (
                <li key={i} className="text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span style={{ color: T.ink }} className="f-mono">
                      {a.nature === "sinistre" ? "Dossier " : "Contrat "}
                      {a.ref}
                    </span>
                    <StatusBadge status={a.statut} />
                  </div>
                  <div className="f-mono mt-1" style={{ color: T.grey }}>
                    {a.moment ? new Date(a.moment).toLocaleDateString("fr-FR") : "—"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs" style={{ color: T.grey }}>
              Aucune activite recente.
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="rounded-lg p-6 border" style={{ backgroundColor: T.surface, borderColor: T.line }}>
          <h2 className="text-sm font-semibold mb-4">Contrats par type</h2>
          <ul className="space-y-2">
            {(stats.repartition_types_contrats || []).map((r) => (
              <li key={r.type_contrat || "—"} className="flex items-center justify-between text-sm">
                <span style={{ color: T.muted }}>{r.type_contrat || "Non renseigné"}</span>
                <span className="f-mono font-medium">{r.n}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg p-6 border" style={{ backgroundColor: T.surface, borderColor: T.line }}>
          <h2 className="text-sm font-semibold mb-4">Sinistres par statut</h2>
          <ul className="space-y-2">
            {(stats.repartition_statuts_sinistres || []).map((r) => (
              <li key={r.statut || "—"} className="flex items-center justify-between text-sm">
                <StatusBadge status={r.statut} />
                <span className="f-mono font-medium">{r.n}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
