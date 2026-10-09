import React, { useEffect, useRef, useState, createContext, useContext, useCallback } from "react";
import { X, AlertTriangle, CheckCircle2, Loader2, Inbox } from "lucide-react";

/* ————————————————————————————————————————————
   Design tokens (identiques a la maquette d'origine)
—————————————————————————————————————————————— */
export const T = {
  ink: "#16213E",
  paper: "#EEF0F2",
  surface: "#FFFFFF",
  line: "#DADFE3",
  lineLight: "#EDEFF1",
  accent: "#2F5D8A",
  accentDim: "#E4EBF1",
  gold: "#C68A2E",
  goldBg: "#F7EEDD",
  green: "#3A7D5C",
  greenBg: "#E7F1EB",
  red: "#B4483A",
  redBg: "#F5E5E1",
  grey: "#8B8F94",
  greyBg: "#ECEDEE",
  muted: "#5C6470",
};

export const STATUS_STYLES = {
  Actif: { color: T.green, bg: T.greenBg },
  "En attente": { color: T.gold, bg: T.goldBg },
  Résilié: { color: T.red, bg: T.redBg },
  Expiré: { color: T.grey, bg: T.greyBg },

  A_TRAITER: { color: T.green, bg: T.greenBg, label: "A traiter" },
  PAS_DE_CONSTAT: { color: T.red, bg: T.redBg, label: "Constat manquant" },
  PAS_DE_PHOTOS: { color: T.red, bg: T.redBg, label: "Photos manquantes" },
  PAS_DE_CONSTAT_PHOTOS: { color: T.red, bg: T.redBg, label: "Constat + photos manquants" },
  CONSTAT_INCOMPLET: { color: T.red, bg: T.redBg, label: "Constat incomplet" },
  CONSTAT_A_VERIFIER: { color: T.gold, bg: T.goldBg, label: "A verifier" },
  CONTRAT_INTROUVABLE: { color: T.red, bg: T.redBg, label: "Contrat introuvable" },
  CONTRAT_INVALIDE: { color: T.red, bg: T.redBg, label: "Contrat invalide" },
  CONTRAT_INCOHERENT: { color: T.gold, bg: T.goldBg, label: "Contrat incoherent" },
  INVALIDE: { color: T.red, bg: T.redBg, label: "Invalide" },
  "En expertise": { color: T.gold, bg: T.goldBg },
  Validé: { color: T.green, bg: T.greenBg },
  Refusé: { color: T.red, bg: T.redBg },
  Clôturé: { color: T.grey, bg: T.greyBg },
};

export function StatusBadge({ status }) {
  const s = STATUS_STYLES[status] || { color: T.grey, bg: T.greyBg };
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium f-body whitespace-nowrap"
      style={{ color: s.color, backgroundColor: s.bg }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: s.color }} />
      {s.label || status || "—"}
    </span>
  );
}

export function RefStamp({ children }) {
  return (
    <span
      className="f-mono text-[11px] px-2 py-0.5 border rounded"
      style={{ borderColor: "#C7CDD3", color: T.ink, letterSpacing: "0.02em" }}
    >
      {children}
    </span>
  );
}

/* ————————————————————————————————————————————
   Etats de chargement / vide / erreur
—————————————————————————————————————————————— */
export function Spinner({ label = "Chargement…" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm" style={{ color: T.muted }}>
      <Loader2 size={16} className="animate-spin" /> {label}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  return (
    <div
      className="flex items-center justify-between gap-3 rounded-md border px-4 py-3 text-sm"
      style={{ borderColor: T.red, backgroundColor: T.redBg, color: T.red }}
      role="alert"
    >
      <span className="flex items-center gap-2">
        <AlertTriangle size={15} /> {message}
      </span>
      {onRetry && (
        <button onClick={onRetry} className="underline font-medium">
          Reessayer
        </button>
      )}
    </div>
  );
}

export function EmptyState({ label, sub }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center" style={{ color: T.grey }}>
      <Inbox size={28} strokeWidth={1.5} />
      <div className="text-sm font-medium" style={{ color: T.muted }}>
        {label}
      </div>
      {sub && <div className="text-xs">{sub}</div>}
    </div>
  );
}

/* ————————————————————————————————————————————
   Notifications (toasts)
—————————————————————————————————————————————— */
const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const notify = useCallback((message, type = "success") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  return (
    <ToastCtx.Provider value={notify}>
      {children}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2" aria-live="polite" aria-atomic="true">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="flex items-center gap-2 px-4 py-2.5 rounded-md text-sm shadow-lg f-body"
            style={{
              backgroundColor: t.type === "error" ? T.red : T.ink,
              color: "#fff",
            }}
          >
            {t.type === "error" ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast doit etre utilise dans <ToastProvider>");
  return ctx;
}

/* ————————————————————————————————————————————
   Modal accessible (form, confirmation…)
—————————————————————————————————————————————— */
export function Modal({ title, subtitle, onClose, children, width = 640 }) {
  const ref = useRef(null);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector("input, select, textarea, button")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(22,33,62,0.45)" }}
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-h-[90vh] overflow-auto rounded-lg shadow-xl"
        style={{ backgroundColor: T.surface, maxWidth: width }}
      >
        <div
          className="flex items-start justify-between gap-4 px-6 py-5 border-b sticky top-0"
          style={{ borderColor: T.lineLight, backgroundColor: T.surface }}
        >
          <div>
            <h2 id="modal-title" className="f-display text-lg" style={{ fontWeight: 600, color: T.ink }}>
              {title}
            </h2>
            {subtitle && (
              <p className="text-xs mt-0.5" style={{ color: T.grey }}>
                {subtitle}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Fermer"
            className="p-1.5 rounded-md hover:bg-black/5 shrink-0"
          >
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-6">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({ title, message, confirmLabel = "Confirmer", danger = true, onConfirm, onCancel, busy }) {
  return (
    <Modal title={title} onClose={onCancel} width={420}>
      <p className="text-sm" style={{ color: T.muted }}>
        {message}
      </p>
      <div className="flex justify-end gap-2 mt-6">
        <Button variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
        <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} busy={busy}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

/* ————————————————————————————————————————————
   Boutons / champs de formulaire
—————————————————————————————————————————————— */
export function Button({ children, variant = "primary", busy, className = "", ...rest }) {
  const styles = {
    primary: { backgroundColor: T.accent, color: "#fff" },
    danger: { backgroundColor: T.red, color: "#fff" },
    ghost: { backgroundColor: "transparent", color: T.muted, border: `1px solid ${T.line}` },
  };
  return (
    <button
      {...rest}
      disabled={busy || rest.disabled}
      className={`inline-flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-md font-medium transition-opacity disabled:opacity-60 ${className}`}
      style={styles[variant]}
    >
      {busy && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Field({ label, error, required, children, hint }) {
  return (
    <label className="block text-sm">
      <span className="block text-xs font-medium mb-1.5" style={{ color: T.muted }}>
        {label} {required && <span style={{ color: T.red }}>*</span>}
      </span>
      {children}
      {hint && !error && (
        <span className="block text-[11px] mt-1" style={{ color: T.grey }}>
          {hint}
        </span>
      )}
      {error && (
        <span className="block text-[11px] mt-1" style={{ color: T.red }} role="alert">
          {error}
        </span>
      )}
    </label>
  );
}

const inputStyle = {
  borderColor: T.line,
  backgroundColor: T.surface,
  color: T.ink,
};

export function Input(props) {
  return (
    <input
      {...props}
      className={`w-full px-3 py-2 rounded-md border text-sm outline-none focus:ring-2 ${props.className || ""}`}
      style={{ ...inputStyle, ...(props.style || {}) }}
      onFocus={(e) => (e.target.style.borderColor = T.accent)}
      onBlur={(e) => (e.target.style.borderColor = T.line)}
    />
  );
}

export function Select(props) {
  return (
    <select
      {...props}
      className={`w-full px-3 py-2 rounded-md border text-sm outline-none focus:ring-2 bg-white ${props.className || ""}`}
      style={{ ...inputStyle, ...(props.style || {}) }}
    >
      {props.children}
    </select>
  );
}

export function Textarea(props) {
  return (
    <textarea
      {...props}
      className={`w-full px-3 py-2 rounded-md border text-sm outline-none focus:ring-2 ${props.className || ""}`}
      style={{ ...inputStyle, ...(props.style || {}) }}
    />
  );
}

export function Checkbox({ label, ...props }) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
      <input type="checkbox" {...props} className="w-4 h-4 rounded" style={{ accentColor: T.accent }} />
      {label}
    </label>
  );
}

export function SectionTitle({ children }) {
  return (
    <h3
      className="text-xs font-semibold uppercase tracking-wide pb-2 mb-4 border-b"
      style={{ color: T.grey, borderColor: T.lineLight }}
    >
      {children}
    </h3>
  );
}
