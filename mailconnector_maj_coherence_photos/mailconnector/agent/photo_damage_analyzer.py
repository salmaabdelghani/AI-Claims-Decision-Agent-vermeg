"""
Analyse de coherence entre les photos de dommages jointes a la declaration
et le constat amiable (OCR).

Objectif : detecter les cas de fraude / erreur ou les photos envoyees ne
correspondent pas au sinistre declare. Trois controles sont effectues en
un seul appel vision (Gemini), sur l'ensemble des photos "Photos de
dommages" du dossier :

  1. Coherence INTER-PHOTOS : les photos montrent-elles bien le/les meme(s)
     vehicule(s) (couleur, carrosserie, plaque si visible) ou y a-t-il des
     photos manifestement d'un vehicule different / d'une autre scene ?
  2. Coherence PHOTOS <-> CONSTAT : la zone de choc et les degats visibles
     sur les photos correspondent-ils au "point_choc" / "degats_apparents"
     declares pour le vehicule A et/ou B dans le constat ?
  3. Coherence PHOTOS <-> CROQUIS/CIRCONSTANCES : les degats visibles
     sont-ils compatibles avec le scenario decrit (croquis + cases
     circonstances cochees) ? Ex: un choc arriere declare mais des degats
     visibles uniquement a l'avant est une incoherence.

Le resultat est renvoye sous forme de dict et est destine a :
  - alimenter la section Markdown "Coherence constat-degats" du rapport
    (voir report_generator.py) ;
  - determiner si le dossier doit passer au statut INVALIDE (voir main.py).

N'echoue jamais bruyamment : en cas d'erreur technique (API indisponible,
JSON invalide...), renvoie un resultat "non concluant" (coherent=None) qui
ne doit PAS a lui seul invalider un dossier par ailleurs correct.
"""
import base64
import logging
import os
import time

from google import genai
from google.genai import types

from ressources.circonstances import CIRCONSTANCES_LABELS

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-flash-latest"  # alias auto-mis a jour, voir constat_hybrid_ocr.py

MAX_PHOTOS = 12  # garde-fou : limite le nombre d'images envoyees en un seul appel
MAX_RETRIES = 3  # le modele Gemini renvoie parfois des 503 "high demand" transitoires
RETRY_BACKOFF_SECONDS = 8  # delai avant nouvelle tentative en cas d'erreur transitoire


def _is_transient_error(e: Exception) -> bool:
    """Detecte les erreurs transitoires (surcharge/rate-limit) qui meritent un backoff."""
    msg = str(e).lower()
    return "503" in msg or "unavailable" in msg or "429" in msg or "rate" in msg or "overloaded" in msg


def get_photo_attachments(classified_attachments: list[dict]) -> list[dict]:
    """Renvoie les pieces jointes classifiees comme photos de dommages."""
    return [
        a for a in classified_attachments
        if ("photo" in a.get("nature", "").lower() or "dommage" in a.get("nature", "").lower())
        and a.get("data")
    ]


def _resume_vehicule(ocr_data: dict, prefix: str) -> str:
    veh = ocr_data.get(prefix, {}) or {}
    auto = veh.get("vehicule", {}) or {}
    circ = veh.get("circulation", {}) or {}
    return (
        f"Marque/modele : {auto.get('marque') or 'manquant'} {auto.get('type_modele') or ''} — "
        f"Immatriculation : {auto.get('immatriculation') or 'manquant'} — "
        f"Point de choc declare : {circ.get('point_choc') or 'manquant'} — "
        f"Degats apparents declares : {circ.get('degats_apparents') or 'manquant'} — "
        f"Observations : {circ.get('observations') or 'manquant'}"
    )


def _circonstances_cochees(ocr_data: dict, key: str) -> str:
    circ_dict = ocr_data.get(key, {}) or {}
    coches = [CIRCONSTANCES_LABELS.get(k, k) for k, v in circ_dict.items() if v is True]
    return ", ".join(coches) if coches else "aucune case cochee"


def _build_prompt(ocr_data: dict, nb_photos: int) -> str:
    return f"""Tu es un expert en analyse d'images pour l'assurance automobile (detection de fraude / coherence de sinistre).

On te fournit {nb_photos} photo(s) de dommages jointes a une declaration de sinistre, ainsi que les informations extraites du constat amiable correspondant. Ta mission est de verifier la COHERENCE entre les photos et le constat, PAS de juger de la responsabilite.

=== DONNEES DU CONSTAT ===

Vehicule A :
{_resume_vehicule(ocr_data, "vehicule_a")}
Circonstances A cochees : {_circonstances_cochees(ocr_data, "circonstances_a")}

Vehicule B :
{_resume_vehicule(ocr_data, "vehicule_b")}
Circonstances B cochees : {_circonstances_cochees(ocr_data, "circonstances_b")}

Croquis present : {"oui" if ocr_data.get("croquis_present") else "non"}
Description/synthese du croquis : {ocr_data.get("description_croquis") or "manquant"}

=== CONTROLES A EFFECTUER ===

1. COHERENCE ENTRE LES PHOTOS (meme vehicule) :
   - Les photos representent-elles un nombre de vehicules coherent avec le sinistre (1 ou 2 vehicules, A et/ou B) ?
   - Pour chaque groupe de photos qui semble representer le meme vehicule : la couleur, la carrosserie, le modele, la plaque (si visible) sont-ils coherents entre les photos ?
   - Signale une incoherence UNIQUEMENT si tu vois clairement des vehicules manifestement differents (couleur differente, modele different, plaque differente) presentes comme s'il s'agissait du meme vehicule. En cas de doute (angle different, eclairage different), ne signale rien.

2. COHERENCE POINT DE CHOC / DEGATS (photos vs constat) :
   - Pour chaque vehicule identifiable, la zone de choc visible sur les photos (avant, arriere, lateral droit/gauche, angle...) correspond-elle au "point de choc declare" et aux "degats apparents declares" dans le constat ?
   - Signale une incoherence si les degats visibles sont a un endroit clairement different de celui declare (ex: constat déclare un choc a l'arriere, photos montrent uniquement des degats a l'avant, sans lien logique entre les deux).
   - Des degats supplementaires ou plus etendus que ceux decrits ne sont PAS une incoherence en soi (le texte manuscrit peut etre incomplet) : ne signale que les contradictions franches de LOCALISATION du choc.

3. COHERENCE AVEC LE CROQUIS ET LES CIRCONSTANCES :
   - Le scenario decrit par le croquis et les cases circonstances cochees (ex: choc arriere en circulant meme sens, choc lateral en changeant de file, choc a l'avant en marche arriere...) est-il compatible avec la nature et la localisation des degats visibles sur les photos ?
   - Signale une incoherence uniquement si le scenario declare est physiquement incompatible avec les degats vus (ex: "reculait" coche mais degats uniquement a l'avant sans aucun degat arriere, alors qu'un recul impliquerait un choc arriere).

REGLE ANTI-FAUX-POSITIF (CRITIQUE) :
- Le doute profite TOUJOURS au dossier : ne signale une incoherence que si elle est manifeste et objective, visible sans ambiguite sur les images.
- Des photos floues, mal cadrees, ou ne montrant pas clairement la zone de choc ne sont PAS une incoherence : dans ce cas, indique-le dans l'explication mais ne fais pas echouer la coherence pour ce seul motif.
- N'invente jamais un vehicule, une couleur ou un degat non visible sur les images.

Reponds UNIQUEMENT en JSON valide (sans markdown, sans backticks) avec cette structure exacte :
{{
  "nb_photos_analysees": {nb_photos},
  "nb_vehicules_identifies": <entier>,
  "coherence_inter_photos": {{"coherent": true/false, "explication": "..."}},
  "coherence_points_choc_degats": {{"coherent": true/false, "explication": "..."}},
  "coherence_croquis_circonstances": {{"coherent": true/false, "explication": "..."}},
  "coherent_global": true/false,
  "explication_detaillee": "synthese complete et redigee en francais (5-10 lignes) justifiant la conclusion, reprenant les 3 controles ci-dessus"
}}"""


def analyze_photo_coherence(classified_attachments: list[dict], ocr_data: dict) -> dict:
    """
    Analyse la coherence des photos de dommages par rapport au constat.

    Renvoie un dict avec au minimum :
      - "analyzed" (bool) : True si l'analyse a pu etre menee jusqu'au bout
      - "coherent" (bool | None) : None si non concluant (ex: erreur technique,
        pas assez de donnees), sinon resultat du controle global
      - "explication" (str) : explication detaillee (toujours renseignee)
      - autres details bruts sous la cle "details"
    """
    photos = get_photo_attachments(classified_attachments)

    if not photos:
        return {
            "analyzed": False,
            "coherent": None,
            "explication": "Aucune photo de dommages exploitable n'a ete trouvee dans le dossier.",
            "details": {},
        }

    if not ocr_data or "error" in ocr_data:
        return {
            "analyzed": False,
            "coherent": None,
            "explication": "Analyse de coherence non effectuee : les donnees du constat (OCR) sont indisponibles.",
            "details": {},
        }

    photos = photos[:MAX_PHOTOS]

    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    except Exception as e:
        logger.error(f"Client Gemini indisponible pour l'analyse photo: {e}")
        return {
            "analyzed": False,
            "coherent": None,
            "explication": f"Analyse de coherence photos/constat indisponible (erreur technique : {e}).",
            "details": {},
        }

    prompt = _build_prompt(ocr_data, len(photos))

    contents = [prompt]
    for photo in photos:
        try:
            image_bytes = base64.b64decode(photo["data"])
            content_type = photo.get("content_type", "image/jpeg")
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=content_type))
        except Exception as e:
            logger.warning(f"Photo ignoree (decodage impossible) : {photo.get('filename')} — {e}")

    from .classifier import _parse_json

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=3000,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            )
            response_text = (response.text or "").strip()
            if not response_text:
                last_err = RuntimeError("Reponse vide du modele Gemini")
                logger.warning(f"Reponse vide analyse photo (tentative {attempt+1}/{MAX_RETRIES})")
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue

            result = _parse_json(response_text)
            coherent_global = result.get("coherent_global")
            explication = result.get("explication_detaillee") or "Analyse effectuee, sans explication detaillee fournie."

            logger.info(
                f"Analyse coherence photos/constat : coherent_global={coherent_global} "
                f"({len(photos)} photo(s) analysee(s))"
            )

            return {
                "analyzed": True,
                "coherent": bool(coherent_global) if coherent_global is not None else None,
                "explication": explication,
                "details": result,
            }
        except Exception as e:
            last_err = e
            logger.warning(f"Appel Gemini (analyse photo) echoue (tentative {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1 and _is_transient_error(e):
                # Erreur transitoire (surcharge modele, rate-limit) : on laisse
                # un court delai avant de retenter, plutot que de retenter
                # immediatement dans les memes conditions de charge.
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    logger.error(f"Analyse coherence photos/constat en echec definitif: {last_err}")
    return {
        "analyzed": False,
        "coherent": None,
        "explication": f"Analyse de coherence photos/constat non concluante (erreur technique : {last_err}).",
        "details": {},
    }
