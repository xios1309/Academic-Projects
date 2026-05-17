"""
Image Generation From Sentences (Unsplash / Pexels)
====================================================

Pour chaque phrase en francais, ce script :
  1. Traduit la phrase en anglais
  2. Extrait les mots-cles principaux (en retirant les mots vides)
  3. Telecharge une photo correspondante depuis Unsplash ou Pexels via leur
     API officielle
  4. Sauvegarde l'image dans le dossier `outputs/`

IMPORTANT : Une cle API gratuite est necessaire (l'ancienne URL publique
source.unsplash.com a ete arretee en 2024). L'inscription prend 2 minutes.

  --provider unsplash  (DEFAUT, recommande)
      Inscription gratuite : https://unsplash.com/developers
      -> Cree une nouvelle application "Demo" -> recopie l'Access Key
      Limite gratuite : 50 requetes par heure

  --provider pexels
      Inscription gratuite : https://www.pexels.com/api/
      Limite gratuite : 200 requetes par heure

Fournir la cle :
  - via la variable d'environnement UNSPLASH_ACCESS_KEY ou PEXELS_API_KEY
  - ou via l'argument --api-key TA_CLE

Dependances :
    pip install -r requirements.txt   (requests, pillow, deep-translator)

Utilisation :
    set UNSPLASH_ACCESS_KEY=ta_cle_ici
    python image_generation.py

    python image_generation.py --provider pexels --api-key TA_CLE
    python image_generation.py "un chat roux qui dort" "coucher de soleil"
    python image_generation.py --file mes_phrases.txt
"""

import argparse
import os
import re
import sys
import time
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

REQUEST_TIMEOUT = 60          # secondes
DELAY_BETWEEN_REQUESTS = 1    # seconde

# Liste etendue de mots vides en anglais (stopwords).
# On les retire pour ne garder que les mots porteurs de sens.
STOPWORDS_EN = {
    # articles, prepositions, conjonctions
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "but",
    "to", "for", "from", "by", "as", "into", "over", "under", "about",
    "between", "through", "during", "before", "after", "above", "below",
    # pronoms et possessifs
    "i", "me", "my", "mine", "myself", "we", "us", "our", "ours",
    "you", "your", "yours", "yourself",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "this", "that", "these", "those", "who", "whom", "whose", "which",
    "what", "where", "when", "why", "how",
    "one", "ones", "some", "any", "all", "each", "every", "no", "none",
    # verbes auxiliaires et tres frequents
    "is", "are", "was", "were", "be", "been", "being", "am",
    "have", "has", "had", "having",
    "do", "does", "did", "doing",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "get", "got", "make", "made", "go", "goes", "went", "come", "came",
    "take", "took", "felt", "feel", "feels",
    "if", "then", "than", "so", "because", "while",
    "not", "yes", "very", "much", "many", "more", "most", "less",
    "just", "only", "also", "too", "even", "still", "again",
    "there", "here", "now", "today", "yesterday", "tomorrow",
    "decided", "showed", "show", "shown", "seen", "see",
}

# Mots qui ne donnent jamais de bonnes images, on les exclut explicitement
LOW_VALUE_WORDS = {
    "thing", "things", "something", "someone", "everything", "nothing",
    "way", "ways", "kind", "type", "fact", "case", "lot", "lots",
}


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def load_phrases_from_file(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def translate_fr_to_en(text: str) -> str:
    if GoogleTranslator is None:
        print("  [Avertissement] deep-translator non installe, traduction ignoree.")
        return text
    try:
        return GoogleTranslator(source="fr", target="en").translate(text)
    except Exception as e:
        print(f"  [Avertissement] Traduction echouee : {e}")
        return text


def extract_keywords(text_en: str, max_keywords: int = 4) -> list:
    """Extrait les mots-cles porteurs de sens d'une phrase anglaise."""
    words = re.findall(r"[A-Za-z]+", text_en.lower())
    keywords = [
        w for w in words
        if w not in STOPWORDS_EN
        and w not in LOW_VALUE_WORDS
        and len(w) > 2
    ]
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_keywords]


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    return text[:max_len] or "image"


# ---------------------------------------------------------------------------
# Fournisseur 1 : Unsplash API officielle
# ---------------------------------------------------------------------------

def download_from_unsplash(
    query: str,
    output_path: Path,
    access_key: str,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Recherche puis telecharge la 1ere photo Unsplash correspondant a la requete."""
    if not access_key:
        raise ValueError(
            "Cle Unsplash manquante. Inscris-toi sur https://unsplash.com/developers "
            "puis fournis ta cle via UNSPLASH_ACCESS_KEY ou --api-key."
        )

    search_url = "https://api.unsplash.com/search/photos"
    headers = {"Authorization": f"Client-ID {access_key}"}
    params = {"query": query, "per_page": 1, "orientation": "landscape"}

    r = requests.get(search_url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    results = data.get("results", [])
    if not results:
        raise RuntimeError(f"Aucune photo trouvee sur Unsplash pour : {query!r}")

    photo = results[0]
    photo_url = photo["urls"].get("regular") or photo["urls"]["small"]
    photographer = photo["user"].get("name", "inconnu")

    img = requests.get(photo_url, timeout=timeout)
    img.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(img.content)

    print(f"    Photo par : {photographer} (via Unsplash)")
    return output_path


# ---------------------------------------------------------------------------
# Fournisseur 2 : Pexels API officielle
# ---------------------------------------------------------------------------

def download_from_pexels(
    query: str,
    output_path: Path,
    api_key: str,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Recherche puis telecharge la 1ere photo Pexels correspondant a la requete."""
    if not api_key:
        raise ValueError(
            "Cle Pexels manquante. Inscris-toi sur https://www.pexels.com/api/ "
            "puis fournis ta cle via PEXELS_API_KEY ou --api-key."
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
    provider: str,
    api_key: str,
    show: bool = False,
) -> None:
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
        # Si l'extraction donne trop peu de mots-cles, on retombe sur la phrase EN entiere
        query = " ".join(keywords) if keywords else en
        print(f"    Prompt EN : {en}")
        print(f"    Requete   : {query}")

        filename = f"{idx:02d}_{slugify(fr)}.jpg"
        output_path = OUTPUT_DIR / filename

        try:
            if provider == "unsplash":
                download_from_unsplash(query, output_path, access_key=api_key)
            elif provider == "pexels":
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

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            if status == 401:
                print(f"    [Erreur 401] Cle API invalide ou non autorisee.\n")
            elif status == 403:
                print(f"    [Erreur 403] Quota depasse ou cle non valide.\n")
            else:
                print(f"    [Erreur HTTP {status}] {e}\n")
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
    parser.add_argument("phrases", nargs="*", help="Phrases (sinon lit --file)")
    parser.add_argument(
        "--file", "-f",
        type=Path,
        default=DEFAULT_PHRASES_FILE,
        help=f"Fichier (defaut : {DEFAULT_PHRASES_FILE.name})",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["unsplash", "pexels"],
        default="unsplash",
        help="Source des images (defaut : unsplash)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Cle API. Sinon lue depuis UNSPLASH_ACCESS_KEY ou PEXELS_API_KEY.",
    )
    parser.add_argument("--show", action="store_true", help="Ouvrir chaque image")
    return parser.parse_args()


def resolve_api_key(provider: str, cli_key: str) -> str:
    """Resout la cle API selon le fournisseur : argument CLI puis variables d'environnement."""
    if cli_key:
        return cli_key
    if provider == "unsplash":
        return os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if provider == "pexels":
        return os.environ.get("PEXELS_API_KEY", "")
    return ""


def main() -> int:
    args = parse_args()

    if args.phrases:
        phrases = args.phrases
        print(f"Phrases recues en argument : {len(phrases)}\n")
    else:
        if not args.file.exists():
            print(f"[Erreur] Fichier introuvable : {args.file}", file=sys.stderr)
            return 1
        phrases = load_phrases_from_file(args.file)
        print(f"Phrases chargees depuis {args.file.name} : {len(phrases)}\n")

    api_key = resolve_api_key(args.provider, args.api_key)
    if not api_key:
        env_var = "UNSPLASH_ACCESS_KEY" if args.provider == "unsplash" else "PEXELS_API_KEY"
        signup_url = (
            "https://unsplash.com/developers"
            if args.provider == "unsplash"
            else "https://www.pexels.com/api/"
        )
        print(f"[Erreur] Cle API manquante pour --provider {args.provider}.", file=sys.stderr)
        print(f"  1. Inscris-toi (gratuit) : {signup_url}")
        print(f"  2. Recopie ta cle, puis dans CMD :")
        print(f"        set {env_var}=ta_cle_ici")
        print(f"        python image_generation.py")
        print(f"     OU :  python image_generation.py --api-key ta_cle_ici")
        return 1

    process_phrases(phrases, provider=args.provider, api_key=api_key, show=args.show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
