import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Modal, Field, Input, Select, Button, SectionTitle, Checkbox, useToast } from "../ui.jsx";

const emptyContrat = {
  num_police: "",
  type_contrat: "Auto",
  statut: "En attente",
  date_souscription: "",
  date_effet: "",
  date_expiration: "",
  bonus_malus: "1.00",
  prime_annuelle: "",
  mode_paiement: "Annuel",
  agence: "",
  numero_agence: "",
};

const emptyClient = {
  client_id: null,
  nom: "",
  prenom: "",
  cin: "",
  date_naissance: "",
  adresse: "",
  telephone: "",
  email: "",
  profession: "",
  numero_permis: "",
  date_delivrance_permis: "",
};

const emptyVehicule = {
  immatriculation: "",
  vin: "",
  marque: "",
  modele: "",
  annee: "",
  energie: "Essence",
  couleur: "",
  valeur_assuree: "",
  usage: "Privé",
};

const emptyGaranties = {
  dommages_collision_active: false, dommages_collision_franchise: "", dommages_collision_plafond: "", dommages_collision_couverture: "",
  rc_active: true, rc_franchise: "", rc_plafond: "", rc_couverture: "",
  vol_active: false, vol_franchise: "", vol_plafond: "", vol_couverture: "",
  incendie_active: false, incendie_franchise: "", incendie_plafond: "", incendie_couverture: "",
  bris_glace_active: false, bris_glace_franchise: "", bris_glace_plafond: "", bris_glace_couverture: "",
};

const emptyExclusion = { conduite_sous_alcool: false, conducteur_non_autorise: false };

// nettoie les chaines vides -> null / nombres avant envoi a l'API
function cleanNumbers(obj, numKeys) {
  const out = { ...obj };
  for (const k of numKeys) {
    if (out[k] === "" || out[k] === undefined) out[k] = null;
    else out[k] = Number(out[k]);
  }
  return out;
}
function cleanEmptyStrings(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) out[k] = v === "" ? null : v;
  return out;
}

const GARANTIES_DEFS = [
  { key: "dommages_collision", label: "Dommages Collision" },
  { key: "rc", label: "Responsabilité Civile" },
  { key: "vol", label: "Vol" },
  { key: "incendie", label: "Incendie" },
  { key: "bris_glace", label: "Bris de glace" },
];

export default function ContratForm({ contratId, onClose, onSaved }) {
  const notify = useToast();
  const isEdit = !!contratId;

  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});

  const [contrat, setContrat] = useState(emptyContrat);
  const [client, setClient] = useState(emptyClient);
  const [vehicule, setVehicule] = useState(emptyVehicule);
  const [garanties, setGaranties] = useState(emptyGaranties);
  const [exclusion, setExclusion] = useState(emptyExclusion);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => {});
  }, []);

  useEffect(() => {
    if (!isEdit) return;
    api.contrats
      .get(contratId)
      .then((d) => {
        setContrat({ ...emptyContrat, ...d.contrat });
        setClient({ ...emptyClient, ...(d.client || {}) });
        setVehicule({ ...emptyVehicule, ...(d.vehicule || {}) });
        setGaranties({ ...emptyGaranties, ...(d.garanties || {}) });
        setExclusion({ ...emptyExclusion, ...(d.exclusion || {}) });
      })
      .catch((e) => notify(`Chargement impossible : ${e.message}`, "error"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contratId]);

  const validate = () => {
    const errs = {};
    if (!contrat.num_police?.trim()) errs.num_police = "Numero de police requis";
    if (!client.nom?.trim()) errs.nom = "Nom requis";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      const payload = {
        contrat: cleanNumbers(cleanEmptyStrings(contrat), ["bonus_malus", "prime_annuelle", "numero_agence"]),
        client: cleanEmptyStrings(client),
        vehicule: cleanNumbers(cleanEmptyStrings(vehicule), ["annee", "valeur_assuree"]),
        garanties: cleanNumbers(garanties, [
          "dommages_collision_franchise", "dommages_collision_plafond", "dommages_collision_couverture",
          "rc_franchise", "rc_plafond", "rc_couverture",
          "vol_franchise", "vol_plafond", "vol_couverture",
          "incendie_franchise", "incendie_plafond", "incendie_couverture",
          "bris_glace_franchise", "bris_glace_plafond", "bris_glace_couverture",
        ]),
        exclusion,
      };
      if (isEdit) {
        await api.contrats.update(contratId, payload);
        notify("Contrat mis a jour avec succes.");
      } else {
        await api.contrats.create(payload);
        notify("Contrat cree avec succes.");
      }
      onSaved();
    } catch (err) {
      notify(err.message || "Une erreur est survenue.", "error");
    } finally {
      setSaving(false);
    }
  };

  const set = (setter) => (field) => (e) => {
    const value = e && e.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e;
    setter((prev) => ({ ...prev, [field]: value }));
  };
  const setC = set(setContrat);
  const setCl = set(setClient);
  const setV = set(setVehicule);
  const setG = set(setGaranties);
  const setE = set(setExclusion);

  return (
    <Modal
      title={isEdit ? `Modifier le contrat` : "Nouveau contrat"}
      subtitle={isEdit ? contrat.num_police : "Client, véhicule, garanties et exclusions en une seule fiche"}
      onClose={onClose}
      width={760}
    >
      {loading ? (
        <p className="text-sm" style={{ color: "#8B8F94" }}>
          Chargement du contrat…
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-8" noValidate>
          {/* Contrat */}
          <section>
            <SectionTitle>Contrat</SectionTitle>
            <div className="grid grid-cols-3 gap-4">
              <Field label="N° de police" required error={errors.num_police}>
                <Input value={contrat.num_police || ""} onChange={setC("num_police")} placeholder="POL00234" />
              </Field>
              <Field label="Type de contrat">
                <Select value={contrat.type_contrat || ""} onChange={setC("type_contrat")}>
                  {(meta?.types_contrat || ["Auto"]).map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Statut">
                <Select value={contrat.statut || ""} onChange={setC("statut")}>
                  {(meta?.statuts_contrat || ["En attente"]).map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Date de souscription">
                <Input type="date" value={contrat.date_souscription || ""} onChange={setC("date_souscription")} />
              </Field>
              <Field label="Date d'effet">
                <Input type="date" value={contrat.date_effet || ""} onChange={setC("date_effet")} />
              </Field>
              <Field label="Date d'expiration">
                <Input type="date" value={contrat.date_expiration || ""} onChange={setC("date_expiration")} />
              </Field>
              <Field label="Bonus / Malus" hint="0.50 à 3.50">
                <Input type="number" step="0.01" min="0" value={contrat.bonus_malus ?? ""} onChange={setC("bonus_malus")} />
              </Field>
              <Field label="Prime annuelle (DT)">
                <Input type="number" step="0.01" min="0" value={contrat.prime_annuelle ?? ""} onChange={setC("prime_annuelle")} />
              </Field>
              <Field label="Mode de paiement">
                <Select value={contrat.mode_paiement || ""} onChange={setC("mode_paiement")}>
                  {(meta?.modes_paiement || ["Annuel"]).map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Agence">
                <Input value={contrat.agence || ""} onChange={setC("agence")} />
              </Field>
              <Field label="N° d'agence">
                <Input type="number" min="1" value={contrat.numero_agence ?? ""} onChange={setC("numero_agence")} />
              </Field>
            </div>
          </section>

          {/* Client */}
          <section>
            <SectionTitle>Client / souscripteur</SectionTitle>
            <div className="grid grid-cols-3 gap-4">
              <Field label="Nom" required error={errors.nom}>
                <Input value={client.nom || ""} onChange={setCl("nom")} />
              </Field>
              <Field label="Prénom">
                <Input value={client.prenom || ""} onChange={setCl("prenom")} />
              </Field>
              <Field label="CIN">
                <Input value={client.cin || ""} onChange={setCl("cin")} maxLength={8} />
              </Field>
              <Field label="Date de naissance">
                <Input type="date" value={client.date_naissance || ""} onChange={setCl("date_naissance")} />
              </Field>
              <Field label="Téléphone">
                <Input value={client.telephone || ""} onChange={setCl("telephone")} />
              </Field>
              <Field label="Email">
                <Input type="email" value={client.email || ""} onChange={setCl("email")} />
              </Field>
              <Field label="Profession">
                <Input value={client.profession || ""} onChange={setCl("profession")} />
              </Field>
              <Field label="N° de permis">
                <Input value={client.numero_permis || ""} onChange={setCl("numero_permis")} />
              </Field>
              <Field label="Délivrance du permis">
                <Input type="date" value={client.date_delivrance_permis || ""} onChange={setCl("date_delivrance_permis")} />
              </Field>
              <div className="col-span-3">
                <Field label="Adresse">
                  <Input value={client.adresse || ""} onChange={setCl("adresse")} />
                </Field>
              </div>
            </div>
          </section>

          {/* Vehicule */}
          <section>
            <SectionTitle>Véhicule assuré</SectionTitle>
            <div className="grid grid-cols-3 gap-4">
              <Field label="Marque">
                <Input value={vehicule.marque || ""} onChange={setV("marque")} />
              </Field>
              <Field label="Modèle">
                <Input value={vehicule.modele || ""} onChange={setV("modele")} />
              </Field>
              <Field label="Année">
                <Input type="number" value={vehicule.annee ?? ""} onChange={setV("annee")} />
              </Field>
              <Field label="Immatriculation">
                <Input value={vehicule.immatriculation || ""} onChange={setV("immatriculation")} />
              </Field>
              <Field label="VIN">
                <Input value={vehicule.vin || ""} onChange={setV("vin")} maxLength={17} />
              </Field>
              <Field label="Couleur">
                <Input value={vehicule.couleur || ""} onChange={setV("couleur")} />
              </Field>
              <Field label="Énergie">
                <Select value={vehicule.energie || ""} onChange={setV("energie")}>
                  {["Essence", "Diesel", "Hybride", "Électrique", "GPL"].map((e) => (
                    <option key={e} value={e}>{e}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Usage">
                <Select value={vehicule.usage || ""} onChange={setV("usage")}>
                  {["Privé", "Professionnel", "Taxi/VTC", "Utilitaire"].map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Valeur assurée (DT)">
                <Input type="number" step="0.01" min="0" value={vehicule.valeur_assuree ?? ""} onChange={setV("valeur_assuree")} />
              </Field>
            </div>
          </section>

          {/* Garanties */}
          <section>
            <SectionTitle>Garanties</SectionTitle>
            <div className="space-y-3">
              {GARANTIES_DEFS.map((g) => {
                const active = garanties[`${g.key}_active`];
                return (
                  <div
                    key={g.key}
                    className="grid items-center gap-3 rounded-md border px-3 py-2.5"
                    style={{ borderColor: "#EDEFF1", gridTemplateColumns: "160px repeat(3, 1fr)" }}
                  >
                    <Checkbox
                      label={g.label}
                      checked={!!active}
                      onChange={setG(`${g.key}_active`)}
                    />
                    <Input
                      type="number" step="0.01" min="0" placeholder="Franchise (DT)"
                      disabled={!active}
                      value={garanties[`${g.key}_franchise`] ?? ""}
                      onChange={setG(`${g.key}_franchise`)}
                    />
                    <Input
                      type="number" step="0.01" min="0" placeholder="Plafond (DT)"
                      disabled={!active}
                      value={garanties[`${g.key}_plafond`] ?? ""}
                      onChange={setG(`${g.key}_plafond`)}
                    />
                    <Input
                      type="number" min="0" max="100" placeholder="Couverture (%)"
                      disabled={!active}
                      value={garanties[`${g.key}_couverture`] ?? ""}
                      onChange={setG(`${g.key}_couverture`)}
                    />
                  </div>
                );
              })}
            </div>
          </section>

          {/* Exclusions */}
          <section>
            <SectionTitle>Exclusions</SectionTitle>
            <div className="flex flex-col gap-2">
              <Checkbox
                label="Conduite sous l'emprise de l'alcool"
                checked={!!exclusion.conduite_sous_alcool}
                onChange={setE("conduite_sous_alcool")}
              />
              <Checkbox
                label="Conducteur non autorisé"
                checked={!!exclusion.conducteur_non_autorise}
                onChange={setE("conducteur_non_autorise")}
              />
            </div>
          </section>

          <div className="flex justify-end gap-2 pt-2 border-t" style={{ borderColor: "#EDEFF1" }}>
            <Button variant="ghost" type="button" onClick={onClose}>
              Annuler
            </Button>
            <Button variant="primary" type="submit" busy={saving}>
              {isEdit ? "Enregistrer les modifications" : "Créer le contrat"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
