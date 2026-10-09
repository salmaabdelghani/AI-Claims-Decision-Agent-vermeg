"""
Détermination du taux de responsabilité des deux conducteurs (véhicule A / B)
à partir des données extraites du constat amiable (OCR), sur la base du
Barème de responsabilité FTUSA (ressources/bareme_responsabilite.py).

── Principe ─────────────────────────────────────────────────────────────
1. Moteur de règles déterministe (fonction `_match_regles`) : compare les
   cases cochées circonstances_a / circonstances_b aux combinaisons
   officielles du barème. Auditable, reproductible, sans appel LLM.
2. Si aucune règle "fiable" ne correspond (cas ambigus type stationnement
   irrégulier/gênant, désaccord entre versions, cases sans équivalent au
   formulaire comme portière ouverte ou éclairage) : appel à un LLM de
   raisonnement (`_llm_fallback`) qui reçoit le barème complet + les
   circonstances + le croquis + les dégâts + les observations, et propose
   un taux JUSTIFIÉ mais explicitement marqué comme nécessitant une
   validation humaine.
3. IMPORTANT — ce que dit le barème officiel sur le point de choc : le
   document FTUSA liste explicitement en section II ("Eléments à exclure")
   que le point d'impact sur les véhicules NE DOIT PAS influencer le taux.
   Seules comptent la direction des véhicules, leur position sur la
   chaussée et le stationnement (section III). Ce module respecte cette
   règle : le croquis, le point de choc et les dégâts apparents sont donc
   TOUJOURS inclus dans la justification détaillée (traçabilité, cohérence,
   contexte pour le gestionnaire) mais NE modifient JAMAIS le taux calculé
   à partir des cases cochées. Ils sont en revanche transmis au module LLM
   de secours comme contexte factuel pour les cas non couverts par une case
   (ex. portière ouverte) où ils peuvent être déterminants.
4. Les taux renvoyés sont TOUJOURS normalisés pour que taux_a + taux_b = 1.0
   (voir `_normalize`).
5. Le résultat n'est JAMAIS une décision finale automatique : le champ
   `necessite_expertise` (et `statut`) doit être vérifié par un gestionnaire
   sinistre avant tout recours entre assureurs (cf. art. 123 Code des
   Assurances tunisien).

Usage:
    from .responsabilite import determine_responsabilite
    resp = determine_responsabilite(ocr_data)
    # resp = {
    #   "taux_a": 0.0-1.0, "taux_b": 0.0-1.0,          # somme toujours = 1.0
    #   "cas_type": "01" | ... | None,
    #   "methode": "bareme" | "llm_assiste" | "indetermine",
    #   "statut": "CONFIRME_BAREME" | "PROPOSITION_A_VALIDER" | "INDETERMINE",
    #   "necessite_expertise": bool,
    #   "justification": str,               # explication detaillee (voir ci-dessus)
    #   "elements_pris_en_compte": {...},   # circonstances, croquis, degats... (audit)
    # }
"""
import json
import logging
import os

from groq import Groq

from ressources.circonstances import CIRCONSTANCES_LABELS
from ressources.bareme_responsabilite import (
    REGLES, CAS_SANS_CASE, CAS_DESACCORD, CAS_MULTI_VEHICULES,
)

logger = logging.getLogger(__name__)

_LLM_MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile deprecie par Groq (coupure 16/08/2026) ; raisonnement texte seul, pas de vision requise ici
_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


# ─── Utilitaires communs ───────────────────────────────────────────────────

def _ticked(circ: dict) -> frozenset:
    """Retourne l'ensemble des cles cochees (True) dans un dict circonstances_*."""
    if not isinstance(circ, dict):
        return frozenset()
    return frozenset(k for k, v in circ.items() if v is True)


def _labels(ticks: frozenset) -> list[str]:
    return [CIRCONSTANCES_LABELS.get(k, k.replace("_", " ")) for k in ticks]


def _normalize(taux_a: float, taux_b: float) -> tuple[float, float]:
    """
    Garantit taux_a + taux_b == 1.0 (a 1e-9 pres).
    - Si les deux valeurs sont nulles/indeterminees -> repartition 50/50.
    - Sinon, remise a l'echelle proportionnelle (cas rare ou le LLM
      renverrait une somme != 1, ex. 0.3/0.6).
    """
    if taux_a is None or taux_b is None:
        return 0.5, 0.5
    total = taux_a + taux_b
    if total <= 0:
        return 0.5, 0.5
    if abs(total - 1.0) < 1e-9:
        return round(taux_a, 4), round(taux_b, 4)
    return round(taux_a / total, 4), round(taux_b / total, 4)


def _elements_pris_en_compte(ocr_data: dict, ticks_a: frozenset, ticks_b: frozenset) -> dict:
    """Recapitulatif de TOUS les elements consideres, pour tracabilite/audit."""
    veh_a = ocr_data.get("vehicule_a", {}).get("circulation", {})
    veh_b = ocr_data.get("vehicule_b", {}).get("circulation", {})
    return {
        "circonstances_cochees_a": _labels(ticks_a),
        "circonstances_cochees_b": _labels(ticks_b),
        "point_choc_a": veh_a.get("point_choc"),
        "degats_apparents_a": veh_a.get("degats_apparents"),
        "point_choc_b": veh_b.get("point_choc"),
        "degats_apparents_b": veh_b.get("degats_apparents"),
        "croquis_present": ocr_data.get("croquis_present"),
        "description_croquis": ocr_data.get("description_croquis"),
    }


def _format_elements_texte(elements: dict) -> str:
    """Rend le recapitulatif ci-dessus lisible dans la justification detaillee."""
    parts = []
    if elements["circonstances_cochees_a"]:
        parts.append(f"Circonstances A cochées : {', '.join(elements['circonstances_cochees_a'])}.")
    else:
        parts.append("Circonstances A : aucune case cochée.")
    if elements["circonstances_cochees_b"]:
        parts.append(f"Circonstances B cochées : {', '.join(elements['circonstances_cochees_b'])}.")
    else:
        parts.append("Circonstances B : aucune case cochée.")
    if elements.get("croquis_present"):
        parts.append(f"Croquis présent — {elements.get('description_croquis') or 'sans description exploitable'}.")
    else:
        parts.append("Aucun croquis exploitable sur le constat.")
    if elements.get("point_choc_a") or elements.get("degats_apparents_a"):
        parts.append(f"Véhicule A — choc : {elements.get('point_choc_a') or '-'}, "
                      f"dégâts : {elements.get('degats_apparents_a') or '-'}.")
    if elements.get("point_choc_b") or elements.get("degats_apparents_b"):
        parts.append(f"Véhicule B — choc : {elements.get('point_choc_b') or '-'}, "
                      f"dégâts : {elements.get('degats_apparents_b') or '-'}.")
    parts.append("(Rappel barème FTUSA : le point de choc/dégâts est un élément d'EXCLUSION "
                  "pour le calcul du taux — il est indiqué ici à titre de contexte/cohérence uniquement.)")
    return " ".join(parts)


# ─── Étape 1 : moteur de règles déterministe (cases cochées) ──────────────

def _rule_matches(rule: dict, ticks_x: frozenset, ticks_y: frozenset) -> bool:
    if not rule["x_true"].issubset(ticks_x):
        return False
    if rule["x_false"] & ticks_x:
        return False
    if not rule["y_true"].issubset(ticks_y):
        return False
    if rule["y_false"] & ticks_y:
        return False
    return True


def _match_regles(ticks_a: frozenset, ticks_b: frozenset) -> dict | None:
    """
    Teste chaque regle du bareme dans les deux affectations possibles
    (A=X,B=Y) puis (A=Y,B=X). Retourne la premiere correspondance "fiable"
    trouvee ; a defaut, la premiere correspondance non fiable (ambigue) pour
    permettre de proposer les cas alternatifs.
    """
    fallback_ambigu = None
    for rule in REGLES:
        for (tx, ty, taux_a_key, taux_b_key) in (
            (ticks_a, ticks_b, "taux_x", "taux_y"),
            (ticks_b, ticks_a, "taux_y", "taux_x"),
        ):
            if _rule_matches(rule, tx, ty):
                result = {
                    "cas": rule["cas"],
                    "titre": rule["titre"],
                    "taux_a": rule[taux_a_key],
                    "taux_b": rule[taux_b_key],
                    "fiable": rule["fiable"],
                    "note": rule.get("note"),
                    "cases_alternatives": rule.get("cases_alternatives"),
                }
                if rule["fiable"]:
                    return result
                if fallback_ambigu is None:
                    fallback_ambigu = result
    return fallback_ambigu


# ─── Étape 2 : fallback LLM pour cas ambigus / non couverts ────────────────

def _build_bareme_reference_text() -> str:
    lignes = ["BAREME OFFICIEL DE RESPONSABILITE (FTUSA, art. 123 Code des Assurances tunisien) :"]
    for r in REGLES:
        lignes.append(f"- Cas {r['cas']}: {r['titre']} -> X={float(r['taux_x'])}, Y={float(r['taux_y'])}"
                       + (f" [ATTENTION: {r['note']}]" if r.get("note") else ""))
    for r in CAS_SANS_CASE:
        lignes.append(f"- Cas {r['cas']} (pas de case dediee, se deduit du texte libre / croquis / degats): "
                       f"{r['titre']} -> X={float(r['taux_x'])}, Y={float(r['taux_y'])}")
    lignes.append(f"- Cas {CAS_DESACCORD['cas']} (dernier recours): {CAS_DESACCORD['titre']} "
                   f"-> X={float(CAS_DESACCORD['taux_x'])}, Y={float(CAS_DESACCORD['taux_y'])}")
    lignes.append(
        "RAPPEL : le point de choc / l'emplacement des degats est officiellement un ELEMENT A "
        "EXCLURE du calcul (section II du bareme) ; ne l'utilise que pour les cas 19-22 (sans "
        "case dediee) ou pour eclairer le contexte, jamais pour justifier un ecart par rapport "
        "aux cas bases sur les cases cochees et le croquis."
    )
    return "\n".join(lignes)


_BAREME_REFERENCE_TEXT = None  # construit paresseusement (evite le cout a l'import)


def _llm_fallback(ocr_data: dict, elements: dict, indice_regle: dict | None) -> dict:
    global _BAREME_REFERENCE_TEXT
    if _BAREME_REFERENCE_TEXT is None:
        _BAREME_REFERENCE_TEXT = _build_bareme_reference_text()

    acc = ocr_data.get("accident", {})

    prompt = f"""Tu es un expert sinistre automobile tunisien. Determine le taux de
responsabilite des vehicules A et B en te basant UNIQUEMENT sur le barème
officiel ci-dessous et les faits fournis. N'invente aucune regle hors barème.

{_BAREME_REFERENCE_TEXT}

FAITS DU CONSTAT :
- Lieu de l'accident : {acc.get('lieu')}
- Circonstances cochees vehicule A : {elements['circonstances_cochees_a']}
- Circonstances cochees vehicule B : {elements['circonstances_cochees_b']}
- Point de choc A : {elements['point_choc_a']}
- Degats apparents A : {elements['degats_apparents_a']}
- Point de choc B : {elements['point_choc_b']}
- Degats apparents B : {elements['degats_apparents_b']}
- Croquis present : {elements['croquis_present']}
- Description du croquis : {elements['description_croquis']}
{"- Piste du moteur de regles (cas ambigu detecte) : cas " + str(indice_regle.get('cas')) + " - " + str(indice_regle.get('note')) if indice_regle else ""}

Reponds UNIQUEMENT en JSON valide (sans markdown) :
{{
  "taux_a": <nombre entre 0 et 1>,
  "taux_b": <nombre entre 0 et 1>,
  "cas_bareme_retenu": "<numero du cas du bareme, ou null si aucun ne correspond>",
  "justification": "<3-5 phrases factuelles citant le cas du bareme applique et les elements du croquis/degats utilises s'il s'agit d'un cas 19-22>"
}}
La somme taux_a + taux_b DOIT etre egale a 1.
Si aucune information suffisante n'est disponible pour trancher, retourne
taux_a=0.5, taux_b=0.5 avec cas_bareme_retenu="23" (desaccord / cause indeterminee)."""

    try:
        response = _get_client().chat.completions.create(
            model=_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,  # marge pour le raisonnement de gpt-oss-120b avant le JSON final
            temperature=0.1,
            reasoning_effort="medium",
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        taux_a, taux_b = _normalize(
            float(result.get("taux_a", 0.5)), float(result.get("taux_b", 0.5))
        )
        return {
            "taux_a": taux_a,
            "taux_b": taux_b,
            "cas_type": result.get("cas_bareme_retenu"),
            "methode": "llm_assiste",
            "necessite_expertise": True,
            "justification": result.get("justification", "Analyse assistee par LLM — a valider."),
        }
    except Exception as e:
        logger.error(f"Echec fallback LLM responsabilite: {e}")
        return {
            "taux_a": 0.5, "taux_b": 0.5, "cas_type": "23",
            "methode": "indetermine", "necessite_expertise": True,
            "justification": f"Echec de determination automatique ({e}) — repartition par defaut 50/50, expertise obligatoire.",
        }


# ─── Point d'entree ─────────────────────────────────────────────────────

def determine_responsabilite(ocr_data: dict, overrides: dict = None) -> dict:
    """
    Determine le taux de responsabilite propose pour les vehicules A et B, en
    s'appuyant sur : les cases cochees (circonstances_a/b, base officielle du
    calcul), le croquis et sa description, l'emplacement des degats/point de
    choc (contexte et cas 19-22 sans case dediee), et les observations
    ecrites (via le module LLM de secours). Le resultat n'est jamais une
    decision finale automatique : le champ `necessite_expertise` (et
    `statut`) doit systematiquement etre revu par un gestionnaire sinistre
    avant tout recours entre assureurs.

    `overrides` : {"cas": (taux_a, taux_b)} — surcharges des taux definies
    depuis le dashboard (voir storage/postgres_storage.py::get_bareme_overrides).
    Appliquees APRES la correspondance de regle (jamais sur les conditions
    de correspondance elles-memes), donc sans danger pour le moteur.
    """
    overrides = overrides or {}
    if not ocr_data or "error" in ocr_data:
        return {
            "taux_a": 0.5, "taux_b": 0.5, "cas_type": None,
            "methode": "indetermine", "statut": "INDETERMINE",
            "necessite_expertise": True,
            "justification": "Pas de donnees OCR exploitables pour determiner la responsabilite.",
            "elements_pris_en_compte": {},
        }

    ticks_a = _ticked(ocr_data.get("circonstances_a", {}))
    ticks_b = _ticked(ocr_data.get("circonstances_b", {}))
    elements = _elements_pris_en_compte(ocr_data, ticks_a, ticks_b)
    elements_texte = _format_elements_texte(elements)

    match = _match_regles(ticks_a, ticks_b)

    if match and match["fiable"]:
        taux_a, taux_b = float(match["taux_a"]), float(match["taux_b"])
        override_txt = ""
        if match["cas"] in overrides:
            taux_a, taux_b = overrides[match["cas"]]
            override_txt = " (taux personnalise defini par le gestionnaire, remplace le taux par defaut du bareme)"
        taux_a, taux_b = _normalize(taux_a, taux_b)
        return {
            "taux_a": taux_a,
            "taux_b": taux_b,
            "cas_type": match["cas"],
            "methode": "bareme",
            "statut": "CONFIRME_BAREME",
            "necessite_expertise": False,
            "justification": (
                f"Cas {match['cas']} du barème FTUSA : {match['titre']}. "
                f"Taux appliqué : A={round(taux_a*100)}% / B={round(taux_b*100)}%{override_txt}. {elements_texte}"
            ),
            "elements_pris_en_compte": elements,
        }

    # Cas ambigu (case commune a plusieurs cas du bareme) ou aucune
    # correspondance directe (cases 19-22 sans case dediee, desaccord, etc.)
    # -> raisonnement LLM avec le contexte texte libre + croquis + degats.
    llm_result = _llm_fallback(ocr_data, elements, indice_regle=match)
    llm_result["statut"] = "PROPOSITION_A_VALIDER" if llm_result["methode"] == "llm_assiste" else "INDETERMINE"
    llm_result["elements_pris_en_compte"] = elements
    llm_result["justification"] = f"{llm_result['justification']} {elements_texte}"

    if match and not match["fiable"]:
        alternatives = match.get("cases_alternatives")
        if alternatives:
            alt_txt = " / ".join(
                f"cas {a['cas']} ({a['condition']}: A={float(a['taux_x'])}, B={float(a['taux_y'])})"
                for a in alternatives
            )
            llm_result["justification"] += f" [Cas alternatifs possibles selon le barème : {alt_txt}]"

    return llm_result
