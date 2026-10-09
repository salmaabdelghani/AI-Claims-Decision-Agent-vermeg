import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Modal, Field, Input, Button, useToast } from "../ui.jsx";

const empty = {
  nom: "", prenom: "", cin: "", date_naissance: "", adresse: "",
  telephone: "", email: "", profession: "", numero_permis: "", date_delivrance_permis: "",
};

function cleanEmptyStrings(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) out[k] = v === "" ? null : v;
  return out;
}

export default function ClientForm({ clientId, onClose, onSaved }) {
  const notify = useToast();
  const isEdit = !!clientId;
  const [form, setForm] = useState(empty);
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isEdit) return;
    api.clients
      .get(clientId)
      .then((c) => setForm({ ...empty, ...c }))
      .catch((e) => notify(`Chargement impossible : ${e.message}`, "error"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const set = (field) => (e) => setForm((p) => ({ ...p, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.nom?.trim()) { setError("Le nom est requis."); return; }
    setError(null);
    setSaving(true);
    try {
      const payload = cleanEmptyStrings(form);
      if (isEdit) {
        await api.clients.update(clientId, payload);
        notify("Client mis à jour.");
      } else {
        await api.clients.create(payload);
        notify("Client créé.");
      }
      onSaved();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? "Modifier le client" : "Nouveau client"} onClose={onClose} width={560}>
      {loading ? (
        <p className="text-sm" style={{ color: "#8B8F94" }}>Chargement…</p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Nom" required error={error && !form.nom ? error : null}>
              <Input value={form.nom || ""} onChange={set("nom")} />
            </Field>
            <Field label="Prénom">
              <Input value={form.prenom || ""} onChange={set("prenom")} />
            </Field>
            <Field label="CIN">
              <Input value={form.cin || ""} onChange={set("cin")} maxLength={8} />
            </Field>
            <Field label="Date de naissance">
              <Input type="date" value={form.date_naissance || ""} onChange={set("date_naissance")} />
            </Field>
            <Field label="Téléphone">
              <Input value={form.telephone || ""} onChange={set("telephone")} />
            </Field>
            <Field label="Email">
              <Input type="email" value={form.email || ""} onChange={set("email")} />
            </Field>
            <Field label="Profession">
              <Input value={form.profession || ""} onChange={set("profession")} />
            </Field>
            <Field label="N° de permis">
              <Input value={form.numero_permis || ""} onChange={set("numero_permis")} />
            </Field>
            <Field label="Délivrance du permis">
              <Input type="date" value={form.date_delivrance_permis || ""} onChange={set("date_delivrance_permis")} />
            </Field>
            <div className="col-span-2">
              <Field label="Adresse">
                <Input value={form.adresse || ""} onChange={set("adresse")} />
              </Field>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t" style={{ borderColor: "#EDEFF1" }}>
            <Button variant="ghost" type="button" onClick={onClose}>Annuler</Button>
            <Button variant="primary" type="submit" busy={saving}>
              {isEdit ? "Enregistrer" : "Créer le client"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
