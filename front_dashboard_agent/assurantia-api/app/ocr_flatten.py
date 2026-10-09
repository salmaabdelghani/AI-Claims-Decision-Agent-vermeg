"""
Aplatit la structure JSON imbriquee renvoyee par l'OCR du constat (agent
mailconnector) en un dict de champs plats correspondant aux colonnes de la
table `dossiers_sinistres`.

Portage exact de mailconnector/mailconnector/agent/dossier_sinistre_client.py
::_flatten_ocr_data — duplique ici plutot que partage entre les deux projets
pour que l'API assurantia reste deployable independamment de mailconnector
(les deux ne partagent que la base Postgres, pas de code Python commun).
Si l'un est modifie, verifier que l'autre reste coherent.
"""


def flatten_ocr_data(ocr_data: dict) -> dict:
    acc = ocr_data.get("accident", {}) or {}
    veh_a = ocr_data.get("vehicule_a", {}) or {}
    veh_b = ocr_data.get("vehicule_b", {}) or {}
    ass_a = veh_a.get("assurance", {}) or {}
    ass_b = veh_b.get("assurance", {}) or {}
    cond_a = veh_a.get("conducteur", {}) or {}
    cond_b = veh_b.get("conducteur", {}) or {}
    assure_a = veh_a.get("assure", {}) or {}
    assure_b = veh_b.get("assure", {}) or {}
    auto_a = veh_a.get("vehicule", {}) or {}
    auto_b = veh_b.get("vehicule", {}) or {}
    mvt_a = veh_a.get("circulation", {}) or {}
    mvt_b = veh_b.get("circulation", {}) or {}
    cases_a = ocr_data.get("circonstances_a", {}) or {}
    cases_b = ocr_data.get("circonstances_b", {}) or {}

    def _nullify(val):
        if val is None or val in ("manquant", ""):
            return None
        if isinstance(val, bool):
            return None if val is False else "Oui"
        if isinstance(val, list):
            items = [str(v) for v in val if v not in (None, "", "manquant")]
            return ", ".join(items) if items else None
        if isinstance(val, dict):
            return str(val) if val else None
        if isinstance(val, str):
            return val
        return str(val)

    def _bool(val):
        if val in ("manquant", None):
            return None
        return bool(val)

    temoins = acc.get("temoins")
    if isinstance(temoins, list) and len(temoins) == 0:
        temoins = None

    return {
        "ocr_json": ocr_data,

        "date_accident": _nullify(acc.get("date")),
        "heure_accident": _nullify(acc.get("heure")),
        "lieu_accident": _nullify(acc.get("lieu")),
        "blesses": _nullify(str(acc.get("blesses"))) if acc.get("blesses") not in (None, "manquant") else None,
        "degats_materiels_autres": _nullify(acc.get("degats_materiels_autres")),
        "temoins": temoins,

        "ass_a_societe": _nullify(ass_a.get("societe")),
        "ass_a_numero_police": _nullify(ass_a.get("numero_police")),
        "ass_a_carte_verte": _nullify(ass_a.get("carte_verte")),
        "ass_a_validite": _nullify(ass_a.get("validite")),
        "ass_a_agence": _nullify(ass_a.get("agence")),

        "cond_a_nom": _nullify(cond_a.get("nom")),
        "cond_a_prenom": _nullify(cond_a.get("prenom")),
        "cond_a_adresse": _nullify(cond_a.get("adresse")),
        "cond_a_telephone": _nullify(cond_a.get("telephone")),
        "cond_a_permis": _nullify(cond_a.get("permis")),
        "cond_a_date_permis": _nullify(cond_a.get("date_permis")),

        "assure_a_nom": _nullify(assure_a.get("nom")),
        "assure_a_prenom": _nullify(assure_a.get("prenom")),
        "assure_a_adresse": _nullify(assure_a.get("adresse")),
        "assure_a_telephone": _nullify(assure_a.get("telephone")),

        "veh_a_marque": _nullify(auto_a.get("marque")),
        "veh_a_modele": _nullify(auto_a.get("type_modele")),
        "veh_a_immatriculation": _nullify(auto_a.get("immatriculation")),
        "veh_a_pays": _nullify(auto_a.get("pays")),

        "circ_a_sens": _nullify(mvt_a.get("sens")),
        "circ_a_venant_de": _nullify(mvt_a.get("venant_de")),
        "circ_a_allant_a": _nullify(mvt_a.get("allant_a")),
        "circ_a_point_choc": _nullify(mvt_a.get("point_choc")),
        "circ_a_degats_apparents": _nullify(mvt_a.get("degats_apparents")),
        "circ_a_observations": _nullify(mvt_a.get("observations")),

        "circ_a_en_stationnement": _bool(cases_a.get("en_stationnement")),
        "circ_a_quittait_stationnement": _bool(cases_a.get("quittait_stationnement")),
        "circ_a_prenait_stationnement": _bool(cases_a.get("prenait_stationnement")),
        "circ_a_sortait_parking": _bool(cases_a.get("sortait_parking")),
        "circ_a_engageait_giratoire": _bool(cases_a.get("engageait_giratoire")),
        "circ_a_circulait_giratoire": _bool(cases_a.get("circulait_giratoire")),
        "circ_a_heurtait_arriere": _bool(cases_a.get("heurtait_arriere")),
        "circ_a_meme_sens_meme_file": _bool(cases_a.get("meme_sens_meme_file")),
        "circ_a_changeait_file": _bool(cases_a.get("changeait_file")),
        "circ_a_depassait": _bool(cases_a.get("depassait")),
        "circ_a_virait_droite": _bool(cases_a.get("virait_droite")),
        "circ_a_virait_gauche": _bool(cases_a.get("virait_gauche")),
        "circ_a_reculait": _bool(cases_a.get("reculait")),
        "circ_a_empiete_sens_inverse": _bool(cases_a.get("empiete_sens_inverse")),
        "circ_a_venait_droite": _bool(cases_a.get("venait_droite")),
        "circ_a_non_prioritaire": _bool(cases_a.get("non_prioritaire")),

        "signature_a": _bool(ocr_data.get("signature_a")),

        "ass_b_societe": _nullify(ass_b.get("societe")),
        "ass_b_numero_police": _nullify(ass_b.get("numero_police")),
        "ass_b_carte_verte": _nullify(ass_b.get("carte_verte")),
        "ass_b_validite": _nullify(ass_b.get("validite")),
        "ass_b_agence": _nullify(ass_b.get("agence")),

        "cond_b_nom": _nullify(cond_b.get("nom")),
        "cond_b_prenom": _nullify(cond_b.get("prenom")),
        "cond_b_adresse": _nullify(cond_b.get("adresse")),
        "cond_b_telephone": _nullify(cond_b.get("telephone")),
        "cond_b_permis": _nullify(cond_b.get("permis")),
        "cond_b_date_permis": _nullify(cond_b.get("date_permis")),

        "assure_b_nom": _nullify(assure_b.get("nom")),
        "assure_b_prenom": _nullify(assure_b.get("prenom")),
        "assure_b_adresse": _nullify(assure_b.get("adresse")),
        "assure_b_telephone": _nullify(assure_b.get("telephone")),

        "veh_b_marque": _nullify(auto_b.get("marque")),
        "veh_b_modele": _nullify(auto_b.get("type_modele")),
        "veh_b_immatriculation": _nullify(auto_b.get("immatriculation")),
        "veh_b_pays": _nullify(auto_b.get("pays")),

        "circ_b_sens": _nullify(mvt_b.get("sens")),
        "circ_b_venant_de": _nullify(mvt_b.get("venant_de")),
        "circ_b_allant_a": _nullify(mvt_b.get("allant_a")),
        "circ_b_point_choc": _nullify(mvt_b.get("point_choc")),
        "circ_b_degats_apparents": _nullify(mvt_b.get("degats_apparents")),
        "circ_b_observations": _nullify(mvt_b.get("observations")),

        "circ_b_en_stationnement": _bool(cases_b.get("en_stationnement")),
        "circ_b_quittait_stationnement": _bool(cases_b.get("quittait_stationnement")),
        "circ_b_prenait_stationnement": _bool(cases_b.get("prenait_stationnement")),
        "circ_b_sortait_parking": _bool(cases_b.get("sortait_parking")),
        "circ_b_engageait_giratoire": _bool(cases_b.get("engageait_giratoire")),
        "circ_b_circulait_giratoire": _bool(cases_b.get("circulait_giratoire")),
        "circ_b_heurtait_arriere": _bool(cases_b.get("heurtait_arriere")),
        "circ_b_meme_sens_meme_file": _bool(cases_b.get("meme_sens_meme_file")),
        "circ_b_changeait_file": _bool(cases_b.get("changeait_file")),
        "circ_b_depassait": _bool(cases_b.get("depassait")),
        "circ_b_virait_droite": _bool(cases_b.get("virait_droite")),
        "circ_b_virait_gauche": _bool(cases_b.get("virait_gauche")),
        "circ_b_reculait": _bool(cases_b.get("reculait")),
        "circ_b_empiete_sens_inverse": _bool(cases_b.get("empiete_sens_inverse")),
        "circ_b_venait_droite": _bool(cases_b.get("venait_droite")),
        "circ_b_non_prioritaire": _bool(cases_b.get("non_prioritaire")),

        "signature_b": _bool(ocr_data.get("signature_b")),

        "croquis_present": _bool(ocr_data.get("croquis_present")),
        "description_croquis": _nullify(ocr_data.get("description_croquis")),
    }
