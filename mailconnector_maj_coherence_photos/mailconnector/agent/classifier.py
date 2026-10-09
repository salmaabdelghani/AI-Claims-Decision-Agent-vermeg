"""
Classificateur IA base sur Groq (llama-3.3-70b-versatile).
Free tier : 14,400 requetes/jour, 6000 tokens/minute.
"""
import json
import os
import time
import logging
from groq import Groq

logger = logging.getLogger(__name__)

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile est deprecie par Groq, coupure prevue le 16/08/2026

ATTACHMENT_TYPES = [
    "Constat amiable", "CIN / Carte d'identite", "Permis de conduire",
    "Carte grise / Immatriculation", "Contrat d'assurance", "Facture de reparation",
    "Devis de reparation", "Rapport d'expertise", "Ordonnance medicale",
    "Certificat medical", "Proces-verbal de police", "Photos de dommages",
    "Releve bancaire", "Autre document",
]


def _call_groq(prompt: str, max_tokens: int = 1000, retries: int = 3, temperature: float = 0.2) -> str:
    """Appel Groq avec retry sur les erreurs 429."""
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort="low",  # gpt-oss reflechit avant de repondre ; "low" evite de saturer max_tokens avec le raisonnement
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                wait = 10 * (attempt + 1)
                logger.warning(f"Rate limit Groq, attente {wait}s (tentative {attempt+1}/{retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Groq indisponible apres {retries} tentatives")


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip().rstrip("`").strip())


def classify_email(email_data: dict) -> dict:
    """Classe l'email : sinistre ou non."""
    prompt = f"""Tu es un assistant specialise en assurance. Analyse cet email et determine s'il s'agit d'une declaration de sinistre.

Objet: {email_data['subject']}
Expediteur: {email_data['sender']}
Corps: {email_data['body'][:1500]}
Pieces jointes: {[a['filename'] for a in email_data.get('attachments', [])]}

Reponds UNIQUEMENT en JSON valide (sans markdown ni backticks):
{{
  "is_sinistre": true ou false,
  "confidence": nombre entre 0.0 et 1.0,
  "reason": "explication courte",
  "sinistre_type": "auto ou habitation ou sante ou vie ou autre, ou null si pas sinistre"
}}"""

    try:
        result = _parse_json(_call_groq(prompt, max_tokens=250))
    except Exception as e:
        logger.error(f"Erreur classification: {e}")
        result = {"is_sinistre": False, "confidence": 0.0, "reason": str(e), "sinistre_type": None}

    logger.info(f"Classification: is_sinistre={result.get('is_sinistre')} confidence={result.get('confidence')}")
    return result


def analyze_sinistre(email_data: dict) -> dict:
    """Analyse approfondie : resume + classification des pieces jointes."""
    summary_prompt = f"""Tu es un expert en sinistres assurance. Resume cette declaration en 5-8 lignes.

Objet: {email_data['subject']}
Corps: {email_data['body'][:2500]}

Inclure: nature du sinistre, date/lieu, dommages, demandes. Repondre en francais, prose directe, sans liste."""

    try:
        summary = _call_groq(summary_prompt, max_tokens=500)
    except Exception as e:
        logger.error(f"Erreur resume: {e}")
        summary = "Resume non disponible."

    classified_attachments = []
    for attachment in email_data.get("attachments", []):
        att_type, att_nature = classify_attachment(attachment)
        classified_attachments.append({**attachment, "classified_type": att_type, "nature": att_nature})

    return {"summary": summary, "classified_attachments": classified_attachments}


def classify_attachment(attachment: dict) -> tuple[str, str]:
    """
    Classifie une piece jointe.
    - Si c'est une image : envoie le contenu visuel au modele vision (llama-3.2-11b-vision-preview)
    - Sinon : classification par nom de fichier et type MIME
    """
    content_type = attachment.get("content_type", "")
    is_image = content_type.startswith("image/")

    ext = attachment["filename"].lower().rsplit(".", 1)[-1] if "." in attachment["filename"] else ""
    fmt = {"pdf": "PDF", "jpg": "Image", "jpeg": "Image", "png": "Image",
           "docx": "Word", "doc": "Word", "xlsx": "Excel"}.get(ext, "Autre")

    if is_image and attachment.get("data"):
        return fmt, _classify_image_vision(attachment)
    else:
        return fmt, _classify_by_name(attachment)


def _classify_image_vision(attachment: dict) -> str:
    """
    Envoie l'image au modele vision Groq pour identifier sa nature reelle.
    Modele: llama-3.2-11b-vision-preview
    """
    content_type = attachment.get("content_type", "image/jpeg")
    image_data = attachment.get("data", "")

    prompt = f"""Tu es un expert en assurance et documents officiels tunisiens. Analyse cette image attentivement.

Types de documents et leurs caracteristiques visuelles :
- CIN / Carte d'identite : carte avec photo de visage, nom, prenom, date naissance, numero CIN, drapeau tunisien
- Carte grise / Immatriculation : certificat vehicule, contient marque voiture, numero serie, cylindree, PAS de photo de visage humain
- Constat amiable : formulaire accident avec croquis de vehicules, cases a cocher, deux colonnes conducteurs
- Permis de conduire : petit document avec photo conducteur, categories A B C
- Contrat d'assurance : document texte avec clauses, montants garantie, numero police
- Photos de dommages : photo montrant degats physiques sur vehicule ou propriete
- Facture de reparation : document commercial avec prix, pieces, main d'oeuvre
- Rapport d'expertise : document technique avec estimation des dommages
- Proces-verbal de police : document officiel police avec cachet
- Ordonnance medicale : prescription avec nom medecin, liste medicaments
- Certificat medical : attestation medicale avec diagnostic
- Autre document : tout autre type

Nom du fichier (indice): {attachment['filename']}

Reponds UNIQUEMENT en JSON valide (sans markdown):
{{"nature": "type exact parmi la liste", "description": "elements visuels cles en 15 mots max"}}"""

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="qwen/qwen3.6-27b",  # modele vision (remplace llama-4-scout, deprecie le 17/06/2026)
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{image_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }],
                max_tokens=400,
                temperature=0.1,
                reasoning_effort="none",   # mode non-thinking : reponse directe, evite un content vide
                reasoning_format="hidden",
            )
            text = response.choices[0].message.content.strip()
            result = _parse_json(text)
            nature = result.get("nature", "Autre document")
            description = result.get("description", "")
            logger.info(f"Vision [{attachment['filename']}]: {nature} — {description}")
            return nature
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                wait = 10 * (attempt + 1)
                logger.warning(f"Rate limit vision, attente {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Erreur vision pour {attachment['filename']}: {e}")
                break

    return _classify_by_name(attachment)


def _classify_by_name(attachment: dict) -> str:
    """Fallback : classification par nom de fichier et type MIME."""
    prompt = f"""Classifie cette piece jointe d'un sinistre assurance.
Fichier: {attachment['filename']}
MIME: {attachment.get('content_type', '')}
Types possibles: {', '.join(ATTACHMENT_TYPES)}

Reponds UNIQUEMENT en JSON valide (sans markdown):
{{"nature": "type parmi la liste"}}"""

    try:
        result = _parse_json(_call_groq(prompt, max_tokens=200))
        return result.get("nature", "Autre document")
    except Exception:
        return "Autre document"