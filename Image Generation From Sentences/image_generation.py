"""
Image Generation From Sentences (version Unsplash / Pexels)
============================================================

Pour chaque phrase en francais, ce script :
  1. Traduit la phrase en anglais (les moteurs de recherche d'images marchent
     mieux en anglais)
  2. Extrait les mots-cles principaux
  3. Telecharge une photo correspondante depuis Unsplash ou Pexels
  4. Sauvegarde l'image dans le dossier `outputs/`

Deux fournisseurs sont supportes :

  --provider unsplash  (DEFAUT, AUCUNE CLE REQUISE)
      Utilise https://source.unsplash.com qui renvoie directement une photo
      a partir de mots-cles, sans inscription.

  --provider pexels    (CLE GRATUITE REQUISE)
      Utilise l'API officielle https://api.pexels.com.
      Inscris-toi sur https://www.pexels.com/api/ pour obtenir une cle gratuite,
      puis fournis-la via :
        - la variable d'environnement PEXELS_API_KEY
        - ou l'argument --api-key TA_CLE

Dependances :
    pip install -r requirements.txt
    (requests, pillow, deep-translator)

Utilisation :
    # Mode par defaut : Unsplash, lit phrases.txt
    python image_generation.py

    # Phrases en argument
    python image_generation.py "un chat roux qui dort" "coucher de soleil"

    # Fichier de phrases personnalise
    python image_generation.py --file mes_phrases.txt

    # Utiliser Pexels au lieu de Unsplash
    python image_generation.py --provider pexels --api-key TA_CLE
"""

import argparse
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"
DEFAULT_PHRASES_FILE = SCRIPT_DIR / "phrases.txt"

DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 800
REQUEST_TIMEOUT = 60          # secondes
DELAY_BETWEEN_REQUESTS = 1    # seconde, pour rester poli avec les serveurs

# Mots tres frequents qu'on retire de la requete pour garder l'essentiel
STOPWORDS_EN = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "but",
    "is", "are", "was", "were", "be", "to", "for", "from", "by", "that",
    "this", "these", "those", "it", "its", "as", "into", "over", "under",
    "his", "her", "their", "our", "my", "your",
}


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

def load_phrases_from_file(path: Path) -> list:
    """Charge les phrases depuis un fichier texte (une phrase par ligne)."""
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def translate_fr_to_en(text: str) -> str:
    """Traduit du francais vers l'anglais. Retourne le texte original si echec."""
    if GoogleTranslator is None:
        print("  [Avertissement] deep-translator non installe, traduction ignoree.")
        return text
    try:
        return GoogleTranslator(source="fr", target="en").translate(text)
    except Exception as e:
        print(f"  [Avertissement] Traduction echouee : {e}")
        return text


def extract_keywords(text_en: str, max_keywords: int = 5) -> list:
    """Extrait les mots-cles principaux d'une phrase anglaise."""
    words = re.findall(r"[A-Za-z]+", text_en.lower())
    keywords = [w for w in words if w not in STOPWORDS_EN and len(w) > 2]
    # Supprime les doublons en gardant l'ordre
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_keywords]


def slugify(text: str, max_len: int = 60) -> str:
    """Convertit un texte en nom de fichier sur."""
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    return text[:max_len] or "image"


# ---------------------------------------------------------------------------
# Fournisseur 1 : Unsplash Source (sans cle API)
# ---------------------------------------------------------------------------

def download_from_unsplash(
    keywords: list,
    output_path: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Telecharge une photo depuis source.unsplash.com (aucune cle requise)."""
    if not keywords:
        raise ValueError("Aucun mot-cle pour la recherche Unsplash.")

    query = ",".join(urllib.parse.quote(k) for k in keywords)
    url = f"https://source.unsplash.com/{width}x{height}/?{query}"

    response = requests.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    if not response.content or len(response.content) < 1000:
        raise RuntimeError("Reponse Unsplash vide ou trop petite.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path


# ---------------------------------------------------------------------------
# Fournisseur 2 : Pexels API (cle gratuite requise)
# ---------------------------------------------------------------------------

def download_from_pexels(
    query: str,
    output_path: Path,
    api_key: str,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Telecharge la 1ere photo correspondant a `query` via l'API Pexels."""
    if not api_key:
        raise ValueError(
            "Cle API Pexels manquante. Definis PEXELS_API_KEY ou utilise --api-key."
        )

    search_url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 1, "orientation": "landscape"}

    r = requests.get(search_url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    photos = data.get("photos", [])
    if not photos:
        raise RuntimeError(f"Aucune photo trouvee sur Pexels pour : {query!r}")

    photo_url = photos[0]["src"].get("large2x") or photos[0]["src"]["large"]
    photographer = photos[0].get("photographer", "inconnu")

    img = requests.get(photo_url, timeout=timeout)
    img.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(img.content)

    print(f"    Photo par : {photographer} (via Pexels)")
    return output_path


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def process_phrases(
    phrases: list,
    provider: str = "unsplash",
    api_key: str = "",
    show: bool = False,
) -> None:
    """Traduit chaque phrase et telecharge une image correspondante."""
    if not phrases:
        print("Aucune phrase a traiter.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fournisseur : {provider}")
    print(f"Dossier de sortie : {OUTPUT_DIR}")
    print(f"{len(phrases)} phrase(s) a traiter.\n")

    success_count = 0

    for idx, fr in enumerate(phrases, start=1):
        print(f"[{idx}/{len(phrases)}] {fr}")

        en = translate_fr_to_en(fr)
        keywords = extract_keywords(en)
        print(f"    Prompt EN : {en}")
        print(f"    Mots-cles : {keywords}")

        filename = f"{idx:02d}_{slugify(fr)}.jpg"
        output_path = OUTPUT_DIR / filename

        try:
            if provider == "unsplash":
                download_from_unsplash(keywords, output_path)
            elif provider == "pexels":
                # Pexels accepte une requete textuelle complete
                query = " ".join(keywords) if keywords else en
                download_from_pexels(query, output_path, api_key=api_key)
            else:
                raise ValueError(f"Fournisseur inconnu : {provider}")

            print(f"    Sauvegardee : {output_path}\n")
            success_count += 1

            if show:
                try:
                    Image.open(output_path).show()
                except Exception as e:
                    print(f"    [Avertissement] Impossible d'afficher : {e}")

        except requests.exceptions.RequestException as e:
            print(f"    [Erreur reseau] {e}\n")
        except Exception as e:
            print(f"    [Erreur] {e}\n")

        time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"Termine : {success_count}/{len(phrases)} image(s) telechargee(s) dans {OUTPUT_DIR}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telecharge une photo (Unsplash / Pexels) par phrase.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "phrases",
        nargs="*",
        help="Phrases a traiter (si absentes, lit le fichier --file)",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        default=DEFAULT_PHRASES_FILE,
        help=f"Fichier texte avec une phrase par ligne (defaut : {DEFAULT_PHRASES_FILE.name})",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["unsplash", "pexels"],
        default="unsplash",
        help="Source des images (defaut : unsplash, sans cle API)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("PEXELS_API_KEY", ""),
        help="Cle API Pexels (ou definir PEXELS_API_KEY dans l'environnement)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Ouvrir chaque image dans la visionneuse par defaut",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.phrases:
        phrases = args.phrases
        print(f"Phrases recues en argument : {len(phrases)}\n")
    else:
        if not args.file.exists():
            print(f"[Erreur] Fichier introuvable : {args.file}", file=sys.stderr)
            print("Cree un fichier phrases.txt (une phrase par ligne) ou passe les phrases en argument.")
            return 1
        phrases = load_phrases_from_file(args.file)
        print(f"Phrases chargees depuis {args.file.name} : {len(phrases)}\n")

    if args.provider == "pexels" and not args.api_key:
        print("[Erreur] --provider pexels requiert une cle API.", file=sys.stderr)
        print("  -> Inscription gratuite : https://www.pexels.com/api/")
        print("  -> Puis : python image_generation.py --provider pexels --api-key TA_CLE")
        print("  -> Ou : set PEXELS_API_KEY=TA_CLE  (sous Windows CMD)")
        return 1

    process_phrases(
        phrases,
        provider=args.provider,
        api_key=args.api_key,
        show=args.show,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
