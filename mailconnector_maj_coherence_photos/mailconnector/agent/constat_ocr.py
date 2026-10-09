"""
Module OCR du constat amiable via vision LLM.
Methode principale : Mistral OCR + Gemini 2.5 Flash (constat_hybrid_ocr.py).
extract_constat_old() ci-dessous est le filet de secours (Groq qwen3.6-27b)
utilise seulement si la methode hybride echoue.
- Verifie presence constat + photos dommages
- Extrait tous les champs du constat (champs non lus -> "manquant")
- Cases cochees identifiees visuellement
- Inclut : description du croquis, point de choc / degats / observations pour A et B
"""
import json
import time
import logging
import os
import base64
import io
from groq import Groq

from .constat_hybrid_ocr import extract_constat_hybrid
from .constat_validator import validate_constat
from ressources.insurance_companies import INSURANCE_COMPANIES
from ressources.circonstances import CIRCONSTANCES, CIRCONSTANCES_KEYS

logger = logging.getLogger(__name__)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
VISION_MODEL = "qwen/qwen3.6-27b"  # remplace llama-4-scout, deprecie par Groq le 17/06/2026
MANQUANT = "manquant"


def _maybe_fix_orientation(image_b64: str, content_type: str) -> str:
    """
    Tente de detecter et corriger l'orientation d'une image (EXIF + heuristique
    largeur/hauteur). Les photos de constat prises au telephone sont souvent
    tournees de 90deg, ce qui degrade fortement la qualite de l'OCR vision.
    Retourne le base64 (corrige si possible, original sinon).
    """
    try:
        from PIL import Image, ExifTags
        raw = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(raw))

        # 1. Corrige selon les metadonnees EXIF si presentes
        try:
            exif = img._getexif()
            if exif:
                orientation_key = next(
                    (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
                )
                if orientation_key and orientation_key in exif:
                    orientation = exif[orientation_key]
                    rotate_map = {3: 180, 6: 270, 8: 90}
                    if orientation in rotate_map:
                        img = img.rotate(rotate_map[orientation], expand=True)
        except Exception:
            pass

        buf = io.BytesIO()
        fmt = "PNG" if "png" in content_type else "JPEG"
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"Correction orientation echouee, utilisation image originale: {e}")
        return image_b64


# ─── Verification des documents requis ───────────────────────────────────────

def check_required_documents(classified_attachments: list[dict]) -> dict:
    natures = [a.get("nature", "").lower() for a in classified_attachments]
    has_constat = any("constat" in n for n in natures)
    has_photos  = any("photo" in n or "dommage" in n for n in natures)
    missing = []
    if not has_constat:
        missing.append("Constat amiable")
    if not has_photos:
        missing.append("Photos de dommages")
    return {
        "has_constat": has_constat,
        "has_photos":  has_photos,
        "complete":    has_constat and has_photos,
        "missing":     missing,
        "message":     _build_missing_message(missing) if missing else None,
    }


def _build_missing_message(missing: list[str]) -> str:
    parts = " et ".join(f"**{m}**" for m in missing)
    return (
        f"Dossier incomplet — document(s) manquant(s) : {parts}. "
        f"Merci de renvoyer un email avec les documents manquants."
    )


def get_constat_attachment(classified_attachments: list[dict]) -> dict | None:
    for att in classified_attachments:
        if "constat" in att.get("nature", "").lower():
            return att
    return None


# ─── Determination du statut final du dossier ────────────────────────────────

COMPLETUDE_MIN_PCT = 70  # en dessous, on considere le constat incomplet


def determine_status(doc_check: dict, ocr_data: dict = None) -> dict:
    """
    Determine le statut final du dossier selon les documents et l'OCR.

    Statuts possibles :
    - PAS_DE_CONSTAT       : aucun constat trouve
    - PAS_DE_PHOTOS        : aucune photo de dommages trouvee
    - PAS_DE_CONSTAT_PHOTOS: les deux manquent
    - CONSTAT_INCOMPLET    : constat present mais OCR n'a pas extrait assez de champs
    - CONSTAT_A_VERIFIER   : constat complet mais un ou plusieurs champs extraits
                             ne respectent pas le format attendu (regex metier)
    - A_TRAITER            : tout est complet et valide, pret pour traitement
    """
    missing_constat = not doc_check.get("has_constat")
    missing_photos  = not doc_check.get("has_photos")

    if missing_constat and missing_photos:
        return {"status": "PAS_DE_CONSTAT_PHOTOS",
                "note": "Constat amiable et photos de dommages manquants."}
    if missing_constat:
        return {"status": "PAS_DE_CONSTAT",
                "note": "Constat amiable manquant."}
    if missing_photos:
        return {"status": "PAS_DE_PHOTOS",
                "note": "Photos de dommages manquantes."}

    # Constat et photos presents : verifier la qualite de l'OCR
    if ocr_data is None or "error" in ocr_data:
        return {"status": "CONSTAT_INCOMPLET",
                "note": "Extraction OCR du constat a echoue."}

    pct = ocr_data.get("completude_pct", 0)
    if pct < COMPLETUDE_MIN_PCT:
        nb_manquant = ocr_data.get("champs_manquant", 0)
        total       = ocr_data.get("champs_total", 0)
        return {"status": "CONSTAT_INCOMPLET",
                "note": f"OCR incomplet : seulement {pct}% des champs extraits "
                        f"({total - nb_manquant}/{total})."}

    # Verification du format des champs extraits (regex metier)
    validation = ocr_data.get("validation")
    if validation and validation.get("nb_errors", 0) > 0:
        champs = ", ".join(f"{e['label']} ({e['value']!r})" for e in validation["errors"][:5])
        return {"status": "CONSTAT_A_VERIFIER",
                "note": f"{validation['nb_errors']} champ(s) au format invalide : {champs}."}

    return {"status": "A_TRAITER", "note": None}


# ─── Post-traitement : None -> "manquant" ────────────────────────────────────

def _replace_null_with_manquant(obj):
    if isinstance(obj, dict):
        return {k: _replace_null_with_manquant(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_null_with_manquant(i) for i in obj]
    elif obj is None:
        return MANQUANT
    return obj


def _count_manquant(obj, total=0, manquant=0):
    if isinstance(obj, dict):
        for v in obj.values():
            total, manquant = _count_manquant(v, total, manquant)
    elif isinstance(obj, list):
        for i in obj:
            total, manquant = _count_manquant(i, total, manquant)
    elif isinstance(obj, str):
        total += 1
        if obj == MANQUANT:
            manquant += 1
    return total, manquant


# Fragment JSON ("cle": false, ...) et legende numerotee, generes depuis la
# liste canonique des 17 circonstances (ressources/circonstances.py) — voir
# constat_hybrid_ocr.py pour le detail du raisonnement.
_CIRC_JSON_FIELDS = ", ".join(f'"{k}": false' for k in CIRCONSTANCES_KEYS)
_CIRC_LEGEND = "\n".join(
    f'  {i}. "{key}" = "{label}"' for i, (key, label) in enumerate(CIRCONSTANCES, start=1)
)

# ─── OCR principal ────────────────────────────────────────────────────────────
def _build_constat_prompt() -> str:
    """
    Construit le prompt a CHAQUE appel (pas une constante figee a l'import) :
    la liste des compagnies d'assurance (INSURANCE_COMPANIES) est desormais
    editable depuis le dashboard et rechargee en base au demarrage de
    l'agent (voir main.py) — la construire ici garantit que le prompt reflete
    toujours la liste courante, y compris si elle change en cours de vie du
    processus (prochain redemarrage/rechargement).
    """
    return ("""Tu es un expert en sinistres automobile. Analyse cette image du constat amiable europeen/tunisien.

IMPORTANT:
- Pour chaque champ texte illisible ou absent, utilise exactement la valeur null.
- "degats_materiels_autres" est un champ TEXTE : decris les degats materiels autres que les vehicules A/B (poteau, mur, mobilier urbain...). Si la case "non" est cochee ou rien n'est indique, mets null. Ne jamais mettre true/false ici.
- "blesses" est un champ TEXTE : ecris "Oui" ou "Non" selon la case cochee sur le constat, jamais un booleen.
- Pour les cases a cocher (circonstances) : true si cochee (croix/coche visible), false si vide (jamais null pour ces cases).

REGLE ANTI-HALLUCINATION (CRITIQUE) :
- N'invente JAMAIS de texte. Si l'image est floue, tournee ou le texte manuscrit illisible, mets null plutot que de deviner.
- Pour "observations" : c'est le texte manuscrit dans la case 14 "observations" de CHAQUE vehicule (zone distincte en bas a gauche pour A, en bas a droite pour B). Lis MOT A MOT le texte manuscrit present dans CETTE case precise. Ne copie pas le texte d'un vehicule vers l'autre. Si tu n'es pas sur a 100% de ta lecture, recopie ce que tu vois meme partiellement plutot que d'inventer une phrase plausible.
- Pour "point_choc" : c'est determine par la fleche dessinee dans la case 10 "indiquer par une fleche le point de choc initial" pour CHAQUE vehicule separement. Decris la position exacte de la fleche sur le dessin du vehicule (ex: "fleche pointant l'arriere du vehicule", "fleche pointant l'avant droit"). Ne confonds pas avec le lieu de l'accident (case 2) qui est un champ different.
- Pour "degats_apparents" : c'est le texte manuscrit dans la case 11 "degats apparents", separe et different du point de choc. Lis le texte exact ecrit dans cette case.
- Si l'image semble pivotee ou inclinee, analyse-la quand meme mais sois encore plus prudent : prefere null a une hallucination.
- Pour "point_choc", "degats_apparents", "observations" : decris precisement ce que tu lis ou observes sur le formulaire et le croquis pour CHAQUE vehicule separement (A et B), meme si c'est juste une indication du croquis (ex: "choc avant droit" ou "rayure aile arriere gauche").

REGLE STRICTE POUR "circonstances_a" / "circonstances_b" (case 12 du constat, 17 cases exactement) :
- Il n'existe QUE les 17 cases suivantes. N'en invente AUCUNE autre (pas de "giratoire", pas de case fusionnee) :
""" + _CIRC_LEGEND + """
- Pour CHAQUE vehicule (A et B) separement, mets true UNIQUEMENT pour les cases ou une croix/coche est clairement visible dans la colonne correspondante ; false sinon.
- Chaque case correspond a UNE ligne precise du formulaire : ne fusionne pas deux libelles differents en une seule case cochee, et ne coche pas une case juste parce qu'elle semble plausible au vu du croquis — fie-toi uniquement a la croix effectivement dessinee sur le papier.

REGLE POUR "description_croquis" (ANALYSE, pas simple description visuelle) :
- Objectif : produire une synthese factuelle et structuree du sinistre, exploitable pour de l'analyse de donnees (et non une simple description litteraire du dessin).
- Base-toi sur TROIS sources croisees : (1) ce qui est effectivement dessine dans le croquis case 13 (position des vehicules, sens des fleches, point d'impact, route/intersection), (2) les cases cochees dans circonstances_a et circonstances_b (la ou les manoeuvres declarees par chaque conducteur), et (3) point_choc / degats_apparents de chaque vehicule.
- Structure attendue (phrase concise par vehicule, puis une phrase de synthese) :
  "Vehicule A : [manoeuvre issue des circonstances cochees] — choc initial [point_choc A] — degats [degats_apparents A]. Vehicule B : [manoeuvre issue des circonstances cochees] — choc initial [point_choc B] — degats [degats_apparents B]. Contexte : [type de lieu/scene issu du croquis : intersection, ligne droite, stationnement, giratoire...]."
- Reste strictement factuel : ne deduis une manoeuvre ou un contexte que s'il est soutenu par le croquis ET/OU une case cochee ET/OU le texte du formulaire. Ne jamais inventer une cause, une faute ou une interpretation juridique de responsabilite.
- Si aucun croquis n'est visible ET qu'aucune circonstance n'est cochee, mets null.

REGLE STRICTE POUR "societe" (compagnie d'assurance, vehicule A et B) :
- La valeur de "societe" DOIT etre EXACTEMENT l'un des noms suivants, recopie tel quel (aucune autre valeur n'est acceptee) :
""" + "\n".join(f'  - "{c}"' for c in INSURANCE_COMPANIES) + """
- Identifie la compagnie a partir du logo, du cachet, de l'en-tete ou du texte imprime sur le constat (case assurance de chaque vehicule).
- Si le texte lu ne correspond clairement a AUCUN nom de cette liste, ou si le champ est illisible/absent, mets null. N'invente jamais un nom hors de cette liste.

Reponds UNIQUEMENT en JSON valide (sans markdown) avec cette structure exacte:
{
  "accident": {
    "date": null, "heure": null, "lieu": null,
    "blesses": null, "degats_materiels_autres": null,
    "temoins": []
  },
  "vehicule_a": {
    "assurance": {"societe": null, "numero_police": null, "validite": null, "agence": null},
    "conducteur": {"nom": null, "prenom": null, "adresse": null, "telephone": null, "permis": null, "date_permis": null},
    "assure": {"nom": null, "prenom": null, "adresse": null, "telephone": null},
    "vehicule": {"marque": null, "type_modele": null, "immatriculation": null},
    "circulation": {
      "sens": null, "venant_de": null, "allant_a": null,
      "point_choc": null,
      "degats_apparents": null,
      "observations": null
    }
  },
  "vehicule_b": {
    "assurance": {"societe": null, "numero_police": null, "validite": null, "agence": null},
    "conducteur": {"nom": null, "prenom": null, "adresse": null, "telephone": null, "permis": null, "date_permis": null},
    "assure": {"nom": null, "prenom": null, "adresse": null, "telephone": null},
    "vehicule": {"marque": null, "type_modele": null, "immatriculation": null},
    "circulation": {
      "sens": null, "venant_de": null, "allant_a": null,
      "point_choc": null,
      "degats_apparents": null,
      "observations": null
    }
  },
  "circonstances_a": {""" + _CIRC_JSON_FIELDS + """},
  "circonstances_b": {""" + _CIRC_JSON_FIELDS + """},
  "croquis_present": false,
  "description_croquis": null,
  "signature_a": false,
  "signature_b": false
}""")


def extract_constat_old(attachment: dict) -> dict:
    """
    Extrait tous les champs du constat via vision LLM.
    Les champs non lisibles sont marques 'manquant'.
    """
    content_type = attachment.get("content_type", "image/jpeg")
    image_data   = attachment.get("data", "")

    if not image_data:
        return {"error": "Pas de donnees image", "ocr_status": "echec"}

    # Corrige l'orientation si possible (photos prises en mode portrait/paysage incorrect)
    image_data = _maybe_fix_orientation(image_data, content_type)

    raw_result = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:{content_type};base64,{image_data}"}},
                        {"type": "text", "text": _build_constat_prompt()}
                    ]
                }],
                max_tokens=4000,
                temperature=0.1,
                reasoning_effort="none",   # evite un content vide (reponse coupee en pleine reflexion)
                reasoning_format="hidden",
            )
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip().rstrip("`").strip()
            raw_result = json.loads(text)
            break

        except json.JSONDecodeError as e:
            logger.error(f"OCR JSON invalide (tentative {attempt+1}): {e}")
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 15 * (attempt + 1)
                logger.warning(f"Rate limit OCR, attente {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Erreur OCR: {e}")
                break

    if raw_result is None:
        return {"error": "Extraction echouee", "ocr_status": "echec"}

    result = _replace_null_with_manquant(raw_result)

    total, nb_manquant = _count_manquant(result)
    pct_complete = round((total - nb_manquant) / total * 100) if total > 0 else 0
    result["ocr_status"]      = "succes"
    result["champs_total"]    = total
    result["champs_manquant"] = nb_manquant
    result["completude_pct"]  = pct_complete

    validation = validate_constat(result)
    result["validation"] = validation

    logger.info(
        f"OCR constat: {total - nb_manquant}/{total} champs extraits "
        f"({pct_complete}% complet) — {nb_manquant} manquants — "
        f"croquis={result.get('croquis_present')} — "
        f"{validation['nb_errors']} erreur(s) de format sur {validation['nb_checked']} champs verifies"
    )
    return result
def extract_constat(attachment: dict) -> dict:
    """Nouvelle version hybride (recommandée)"""
    try:
        # Utilise la nouvelle méthode hybride
        result = extract_constat_hybrid(attachment)

        # extract_constat_hybrid() attrape deja ses propres erreurs et
        # renvoie {"error": ...} plutot que de lever une exception : il faut
        # donc verifier explicitement, sinon le fallback ci-dessous (dans le
        # except) ne se declenche jamais pour ce type d'echec.
        if "error" in result:
            logger.warning(
                f"OCR hybride en echec ({result.get('error')}) — "
                f"repli sur l'ancienne methode (vision LLM seul)."
            )
            return extract_constat_old(attachment)

        if "error" not in result:
            # Normalise les null -> "manquant" (comme l'ancienne methode) pour
            # que _count_manquant() et validate_constat() comptent correctement
            # les champs non extraits (sinon un champ None est invisible et
            # gonfle artificiellement le pourcentage de completude).
            result = _replace_null_with_manquant(result)

            # Ajoute les métriques de complétude comme avant
            total, nb_manquant = _count_manquant(result)
            pct_complete = round((total - nb_manquant) / total * 100) if total > 0 else 0
            
            result["ocr_status"] = "succes_hybride"
            result["champs_total"] = total
            result["champs_manquant"] = nb_manquant
            result["completude_pct"] = pct_complete

            validation = validate_constat(result)
            result["validation"] = validation

            logger.info(
                f"OCR Hybride réussi — {pct_complete}% de complétude — "
                f"{validation['nb_errors']} erreur(s) de format sur {validation['nb_checked']} champs vérifiés"
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur OCR Hybride: {e}")
        # Fallback sur l'ancienne méthode si besoin
        return extract_constat_old(attachment)  # à renommer l'ancienne