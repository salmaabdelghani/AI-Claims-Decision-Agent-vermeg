
import base64
import io
import logging
import os

import cv2
import numpy as np
from PIL import Image, ImageEnhance

try:
    from mistralai.client import Mistral
except ImportError:
    from mistralai import Mistral
from google import genai
from google.genai import types

from ressources.insurance_companies import INSURANCE_COMPANIES
from ressources.circonstances import CIRCONSTANCES, CIRCONSTANCES_KEYS

logger = logging.getLogger(__name__)

MISTRAL_OCR_MODEL = "mistral-ocr-latest"
GEMINI_MODEL = "gemini-flash-latest"  # alias auto-mis a jour (actuellement gemini-3.5-flash) ; gemini-2.5-flash coupe pour les nouvelles clefs API depuis le 09/07/2026


_CIRC_JSON_FIELDS = ", ".join(f'"{k}": false' for k in CIRCONSTANCES_KEYS)

_CIRC_LEGEND = "\n".join(
    f'  {i}. "{key}" = "{label}"' for i, (key, label) in enumerate(CIRCONSTANCES, start=1)
)


class AdvancedConstatExtractor:
    def __init__(self):
        self.mistral_client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
        self.gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # ── 1. Pretraitement OpenCV ────────────────────────────────────────────
    def enhance_image(self, image_b64: str):
        """
        Amelioration de l'image avant OCR :
        - Contraste et nettete (PIL)
        - Conversion niveaux de gris
        - CLAHE (egalisation d'histogramme adaptative)
        - Debruitage (fastNlMeansDenoising)
        """
        try:
            img_data = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(img_data)).convert('RGB')

            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(2.0)

            opencv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(opencv_img, cv2.COLOR_BGR2GRAY)

            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            gray = cv2.fastNlMeansDenoising(gray, h=10)

            return gray, opencv_img
        except Exception as e:
            logger.error(f"Enhance error: {e}")
            return None, None

    @staticmethod
    def _encode_png_b64(cv_img) -> str:
        """Reencode une image OpenCV (BGR ou niveaux de gris) en base64 PNG."""
        ok, buf = cv2.imencode(".png", cv_img)
        if not ok:
            raise RuntimeError("Echec de l'encodage PNG de l'image pretraitee")
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    # ── 2. OCR brut via Mistral OCR ────────────────────────────────────────
    def _run_mistral_ocr(self, image_b64: str, content_type: str) -> str:
        """
        Envoie l'image (pretraitee) a l'API Mistral OCR et renvoie le texte
        Markdown extrait. Renvoie une chaine vide en cas d'echec (le pipeline
        continue alors avec Gemini seul, sans indice OCR).
        """
        try:
            response = self.mistral_client.ocr.process(
                model=MISTRAL_OCR_MODEL,
                document={
                    "type": "image_url",
                    "image_url": f"data:{content_type};base64,{image_b64}",
                },
            )
            pages = getattr(response, "pages", None) or []
            texte = "\n".join(p.markdown for p in pages if getattr(p, "markdown", None))
            return texte
        except Exception as e:
            logger.warning(f"Mistral OCR echoue: {e}")
            return ""

    # ── 3. Analyse structuree via Gemini 2.5 Flash ─────────────────────────
    def extract_constat_advanced(self, attachment: dict) -> dict:
        image_b64 = attachment.get("data")
        if not image_b64:
            return {"error": "Pas d'image"}

        content_type = attachment.get("content_type", "image/png")

        # 1. Pretraitement OpenCV
        gray_img, color_img = self.enhance_image(image_b64)
        if gray_img is None:
            logger.warning("enhance_image a echoue, utilisation de l'image brute pour l'OCR Mistral")
            ocr_image_b64, ocr_content_type = image_b64, content_type
        else:
            ocr_image_b64, ocr_content_type = self._encode_png_b64(gray_img), "image/png"

        # 2. OCR Mistral sur l'image pretraitee (texte indicatif)
        mistral_text = self._run_mistral_ocr(ocr_image_b64, ocr_content_type)

        prompt = f"""Tu es un expert judiciaire en constats amiables tunisiens.

L'image du constat amiable t'est fournie directement ci-dessus. Utilise-la comme source principale de lecture.

En complement, voici le texte extrait automatiquement par Mistral OCR, qui peut t'aider a confirmer ou corriger ta lecture de l'image, mais qui peut aussi etre partiel, bruite ou absent — dans ce cas, base-toi uniquement sur l'image :
{mistral_text if mistral_text else "(OCR Mistral indisponible ou vide pour cette image)"}

Lis attentivement chaque champ manuscrit et imprimé DIRECTEMENT SUR L'IMAGE.
Sois extrêmement fidèle à ce qui est écrit.
Si tu n'es pas sûr à 95% → "manquant".

REGLE ANTI-HALLUCINATION (CRITIQUE) :
- N'invente JAMAIS de texte. Si l'image est floue, tournee ou le texte manuscrit illisible, mets "manquant" plutot que de deviner.
- Pour "observations" : c'est le texte manuscrit dans la case 14 "observations" de CHAQUE vehicule (zone distincte en bas a gauche pour A, en bas a droite pour B). Lis MOT A MOT le texte manuscrit present dans CETTE case precise. Ne copie pas le texte d'un vehicule vers l'autre. Si tu n'es pas sur a 100% de ta lecture, recopie ce que tu vois meme partiellement plutot que d'inventer une phrase plausible.
- Pour "point_choc" : c'est determine par la fleche dessinee dans la case 10 "indiquer par une fleche le point de choc initial" pour CHAQUE vehicule separement. Decris la position exacte de la fleche sur le dessin du vehicule (ex: "fleche pointant l'arriere du vehicule", "fleche pointant l'avant droit"). Ne confonds pas avec le lieu de l'accident (case 2) qui est un champ different.
- Pour "degats_apparents" : c'est le texte manuscrit dans la case 11 "degats apparents", separe et different du point de choc. Lis le texte exact ecrit dans cette case.
- Si l'image semble pivotee ou inclinee, analyse-la quand meme mais sois encore plus prudent : prefere "manquant" a une hallucination.

REGLE STRICTE POUR "circonstances_a" / "circonstances_b" (case 12 du constat, 17 cases exactement) :
- Il n'existe QUE les 17 cases suivantes. N'en invente AUCUNE autre (pas de "giratoire", pas de case fusionnee) :
""" + _CIRC_LEGEND + """
- Pour CHAQUE vehicule (A et B) separement, mets true UNIQUEMENT pour les cases ou une croix/coche est clairement visible dans la colonne correspondante ; false sinon (jamais "manquant" pour ces cases : une absence de croix = false).
- Chaque case correspond a UNE ligne precise du formulaire : ne fusionne pas deux libelles differents en une seule case cochee, et ne coche pas une case juste parce qu'elle semble plausible au vu du croquis — fie-toi uniquement a la croix effectivement dessinee sur le papier.

REGLE POUR "description_croquis" (ANALYSE, pas simple description visuelle) :
- Objectif : produire une synthese factuelle et structuree du sinistre, exploitable pour de l'analyse de donnees (et non une simple description litteraire du dessin).
- Base-toi sur TROIS sources croisees : (1) ce qui est effectivement dessine dans le croquis case 13 (position des vehicules, sens des fleches, point d'impact, route/intersection), (2) les cases cochees dans circonstances_a et circonstances_b (la ou les manoeuvres declarees par chaque conducteur), et (3) point_choc / degats_apparents de chaque vehicule.
- Structure attendue (phrase concise par vehicule, puis une phrase de synthese) :
  "Vehicule A : [manoeuvre issue des circonstances cochees] — choc initial [point_choc A] — degats [degats_apparents A]. Vehicule B : [manoeuvre issue des circonstances cochees] — choc initial [point_choc B] — degats [degats_apparents B]. Contexte : [type de lieu/scene issu du croquis : intersection, ligne droite, stationnement, giratoire...]."
- Reste strictement factuel : ne deduis une manoeuvre ou un contexte que s'il est soutenu par le croquis ET/OU une case cochee ET/OU le texte du formulaire. Ne jamais inventer une cause, une faute ou une interpretation juridique de responsabilite.
- Si aucun croquis n'est visible ET qu'aucune circonstance n'est cochee, mets "manquant".

REGLE STRICTE POUR "societe" (compagnie d'assurance, vehicule A et B) :
- La valeur de "societe" DOIT etre EXACTEMENT l'un des noms suivants, recopie tel quel (aucune autre valeur n'est acceptee) :
""" + "\n".join(f'  - "{c}"' for c in INSURANCE_COMPANIES) + """
- Identifie la compagnie a partir du logo, du cachet, de l'en-tete ou du texte imprime sur le constat (case assurance de chaque vehicule).
- Si le texte lu ne correspond clairement a AUCUN nom de cette liste, ou si le champ est illisible/absent, mets "manquant". N'invente jamais un nom hors de cette liste.

Réponds UNIQUEMENT en JSON valide avec cette structure exacte :
{{
  "accident": {{
    "date": null, "heure": null, "lieu": null,
    "blesses": null, "degats_materiels_autres": null,
    "temoins": []
  }},
  "vehicule_a": {{
    "assurance": {{"societe": null, "numero_police": null, "validite": null, "agence": null}},
    "conducteur": {{"nom": null, "prenom": null, "adresse": null, "telephone": null, "permis": null, "date_permis": null}},
    "assure": {{"nom": null, "prenom": null, "adresse": null, "telephone": null}},
    "vehicule": {{"marque": null, "type_modele": null, "immatriculation": null}},
    "circulation": {{
      "sens": null, "venant_de": null, "allant_a": null,
      "point_choc": null, "degats_apparents": null, "observations": null
    }}
  }},
  "vehicule_b": {{
    "assurance": {{"societe": null, "numero_police": null, "validite": null, "agence": null}},
    "conducteur": {{"nom": null, "prenom": null, "adresse": null, "telephone": null, "permis": null, "date_permis": null}},
    "assure": {{"nom": null, "prenom": null, "adresse": null, "telephone": null}},
    "vehicule": {{"marque": null, "type_modele": null, "immatriculation": null}},
    "circulation": {{
      "sens": null, "venant_de": null, "allant_a": null,
      "point_choc": null, "degats_apparents": null, "observations": null
    }}
  }},
  "circonstances_a": {{""" + _CIRC_JSON_FIELDS + """}},
  "circonstances_b": {{""" + _CIRC_JSON_FIELDS + """}},
  "croquis_present": false,
  "description_croquis": null,
  "signature_a": false,
  "signature_b": false
}}"""

        from .classifier import _parse_json

        image_bytes = base64.b64decode(image_b64)

        last_err = None
        for attempt in range(2):
            try:
                response = self.gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_bytes, mime_type=content_type),
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=8000,
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_level="low"),
                    ),
                )
                response_text = (response.text or "").strip()

                finish_reason = None
                try:
                    finish_reason = response.candidates[0].finish_reason
                except Exception:
                    pass
                if finish_reason and str(finish_reason) not in ("STOP", "FinishReason.STOP"):
                    logger.warning(f"Reponse Gemini possiblement tronquee (finish_reason={finish_reason})")

                if not response_text:
                    logger.warning(f"Reponse Gemini vide (tentative {attempt+1}/2)")
                    last_err = RuntimeError("Reponse vide du modele Gemini")
                    continue

                result = _parse_json(response_text)
                result["ocr_method"] = (
                    "opencv_mistral_gemini" if mistral_text else "opencv_gemini_sans_mistral"
                )
                return result
            except Exception as e:
                last_err = e
                logger.warning(f"Appel Gemini echoue (tentative {attempt+1}/2): {e}")

        logger.error(f"Erreur finale: {last_err}")
        return {"error": str(last_err)}


# Pour compatibilité
def extract_constat_hybrid(attachment: dict) -> dict:
    extractor = AdvancedConstatExtractor()
    return extractor.extract_constat_advanced(attachment)
