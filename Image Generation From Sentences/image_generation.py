"""
Image Generation From Sentences (Unsplash / Pexels / Pollinations)
==================================================================

Pour chaque phrase en francais :
  1. Traduit la phrase en anglais
  2. Telecharge ou GENERE une image
  3. Sauvegarde dans `outputs/`

Trois fournisseurs supportes :

  --provider unsplash      Photos reelles (banque d'images)
                           Cle gratuite : https://unsplash.com/developers (50/h)

  --provider pexels        Photos reelles (banque d'images)
                           Cle gratuite : https://www.pexels.com/api/ (200/h)

  --provider pollinations  Images GENEREES par IA (FLUX)
                           AUCUNE CLE REQUISE.
                           Recommande pour phrases abstraites ou figurees.

Fournir la cle (Unsplash / Pexels uniquement) :
  set UNSPLASH_ACCESS_KEY=ta_cle    (ou PEXELS_API_KEY)
  ou : --api-key ta_cle

Dependances :
  pip install -r requirements.txt

USAGES COURANTS
---------------

  # Telecharger toutes les phrases (saute celles deja faites)
  python image_generation.py --provider pollinations

  # Forcer le re-telechargement de TOUT
  python image_generation.py --force

  # Re-generer UNIQUEMENT la phrase n.4
  python image_generation.py --phrase 4

  # Avec Pollinations, --seed change l'image (different de --page)
  python image_generation.py --phrase 4 --provider pollinations --seed 42

  # Avec Unsplash/Pexels, --page choisit la 2eme photo, la 3eme, etc.
  python image_generation.py --phrase 4 --provider unsplash --page 2

  # Re-generer avec mes propres mots
  python image_generation.py --phrase 4 --query "old library books"

  # Lister les phrases avec leur numero
  python image_generation.py --list
"""

import argparse
import os
import random
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

REQUEST_TIMEOUT = 60
DELAY_BETWEEN_REQUESTS = 1

STOPWORDS_EN = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "but",
    "to", "for", "from", "by", "as", "into", "over", "under", "about",
    "between", "through", "during", "before", "after", "above", "below",
    "i", "me", "my", "mine", "myself", "we", "us", "our", "ours",
    "you", "your", "yours", "yourself",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "this", "that", "these", "those", "who", "whom", "whose", "which",
    "what", "where", "when", "why", "how",
    "one", "ones", "some", "any", "all", "each", "every", "no", "none",
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

LOW_VALUE_WORDS = {
    "thing", "things", "something", "someone", "everything", "nothing",
    "way", "ways", "kind", "type", "fact", "case", "lot", "lots",
    "people", "person",
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
    words = re.findall(r"[A-Za-z]+", text_en.lower())
    keywords = [
        w for w in words
        if w not in STOPWORDS_EN and w not in LOW_VALUE_WORDS and len(w) > 2
    ]
    seen, unique = set(), []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_keywords]


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    return text[:max_len] or "image"


def output_path_for(idx: int, fr: str) -> Path:
    return OUTPUT_DIR / f"{idx:02d}_{slugify(fr)}.jpg"


# ---------------------------------------------------------------------------
# Fournisseurs
# ---------------------------------------------------------------------------

def download_from_unsplash(
    query: str,
    output_path: Path,
    access_key: str,
    page: int = 1,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Telecharge la photo Unsplash a la position `page` pour la requete."""
    if not access_key:
        raise ValueError("Cle Unsplash manquante.")

    r = requests.get(
        "https://api.unsplash.com/search/photos",
        headers={"Authorization": f"Client-ID {access_key}"},
        params={"query": query, "per_page": 1, "page": page, "orientation": "landscape"},
        timeout=timeout,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise RuntimeError(f"Aucune photo Unsplash pour {query!r} (page {page}).")

    photo = results[0]
    photo_url = photo["urls"].get("regular") or photo["urls"]["small"]
    photographer = photo["user"].get("name", "inconnu")

    img = requests.get(photo_url, timeout=timeout)
    img.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(img.content)
    print(f"    Photo par : {photographer} (Unsplash, page {page})")
    return output_path


def download_from_pexels(
    query: str,
    output_path: Path,
    api_key: str,
    page: int = 1,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Telecharge la photo Pexels a la position `page` pour la requete."""
    if not api_key:
        raise ValueError("Cle Pexels manquante.")

    r = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={"query": query, "per_page": 1, "page": page, "orientation": "landscape"},
        timeout=timeout,
    )
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if not photos:
        raise RuntimeError(f"Aucune photo Pexels pour {query!r} (page {page}).")

    photo_url = photos[0]["src"].get("large2x") or photos[0]["src"]["large"]
    photographer = photos[0].get("photographer", "inconnu")

    img = requests.get(photo_url, timeout=timeout)
    img.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(img.content)
    print(f"    Photo par : {photographer} (Pexels, page {page})")
    return output_path


def download_one(
    query: str,
    output_path: Path,
    provider: str,
    api_key: str,
    page: int = 1,
    seed: int = None,
) -> Path:
    if provider == "unsplash":
        return download_from_unsplash(query, output_path, api_key, page=page)
    if provider == "pexels":
        return download_from_pexels(query, output_path, api_key, page=page)
    if provider == "pollinations":
        return generate_from_pollinations(query, output_path, seed=seed)
    raise ValueError(f"Fournisseur inconnu : {provider}")


# ---------------------------------------------------------------------------
# Fournisseur 3 : Pollinations.ai (IA generative, sans cle)
# ---------------------------------------------------------------------------

def generate_from_pollinations(
    prompt: str,
    output_path: Path,
    seed: int = None,
    width: int = 1024,
    height: int = 768,
    model: str = "flux",
    timeout: int = 180,
) -> Path:
    """Genere une image via Pollinations.ai (aucune cle API requise).

    `seed` est l'equivalent de `page` pour les fournisseurs photo : pour
    obtenir une image differente sur le meme prompt, change la seed.
    """
    if seed is None:
        seed = random.randint(1, 2**31 - 1)

    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&model={model}"
        f"&seed={seed}&nologo=true"
    )

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()

    if not r.content or len(r.content) < 1000:
        raise RuntimeError("Reponse Pollinations vide ou trop petite.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(r.content)
    print(f"    Image generee par IA (Pollinations FLUX, seed={seed})")
    return output_path


# ---------------------------------------------------------------------------
# Traitement d'une phrase
# ---------------------------------------------------------------------------

def process_one_phrase(
    idx: int,
    fr: str,
    total: int,
    provider: str,
    api_key: str,
    page: int = 1,
    seed: int = None,
    custom_query: str = "",
    skip_existing: bool = False,
    show: bool = False,
) -> bool:
    """Traite une seule phrase. Retourne True si telechargee."""
    output_path = output_path_for(idx, fr)
    print(f"[{idx}/{total}] {fr}")

    if skip_existing and output_path.exists():
        print(f"    Deja presente, ignoree : {output_path.name}")
        print(f"    (--force pour re-telecharger)\n")
        return False

    # Construction du prompt / requete
    if custom_query:
        query = custom_query
        print(f"    Requete personnalisee : {query}")
    else:
        en = translate_fr_to_en(fr)
        if provider == "pollinations":
            # Pour l'IA, on garde la PHRASE COMPLETE traduite : c'est un
            # prompt descriptif, pas une simple recherche par mots-cles.
            query = en
            print(f"    Prompt EN : {en}")
        else:
            keywords = extract_keywords(en)
            query = " ".join(keywords) if keywords else en
            print(f"    Prompt EN : {en}")
            print(f"    Requete   : {query}")

    try:
        download_one(query, output_path, provider, api_key, page=page, seed=seed)
        print(f"    Sauvegardee : {output_path}\n")
        if show:
            try:
                Image.open(output_path).show()
            except Exception as e:
                print(f"    [Avertissement] Affichage impossible : {e}")
        return True
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status == 401:
            print("    [Erreur 401] Cle API invalide.\n")
        elif status == 403:
            print("    [Erreur 403] Quota depasse ou cle invalide.\n")
        else:
            print(f"    [Erreur HTTP {status}] {e}\n")
    except requests.exceptions.RequestException as e:
        print(f"    [Erreur reseau] {e}\n")
    except Exception as e:
        print(f"    [Erreur] {e}\n")
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Telecharge une photo (Unsplash / Pexels) par phrase.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("phrases", nargs="*", help="Phrases en argument (sinon lit --file)")
    p.add_argument(
        "--file", "-f",
        type=Path, default=DEFAULT_PHRASES_FILE,
        help=f"Fichier phrases (defaut : {DEFAULT_PHRASES_FILE.name})",
    )
    p.add_argument(
        "--provider", "-p",
        choices=["unsplash", "pexels", "pollinations"], default="pollinations",
        help="Source des images (defaut : pollinations - IA, sans cle)",
    )
    p.add_argument("--api-key", default="", help="Cle API (Unsplash/Pexels uniquement)")

    # Selection / regeneration
    p.add_argument(
        "--phrase", "-n",
        type=int, default=None,
        help="Traiter UNIQUEMENT la phrase numero N (1-base)",
    )
    p.add_argument(
        "--page",
        type=int, default=1,
        help="[Unsplash/Pexels] N-ieme photo a recuperer pour la meme requete (defaut 1).",
    )
    p.add_argument(
        "--seed",
        type=int, default=None,
        help="[Pollinations] graine de l'IA, change pour obtenir une autre image. "
             "Si non specifiee, une seed aleatoire est utilisee.",
    )
    p.add_argument(
        "--query", "-q",
        default="",
        help="Requete personnalisee (remplace l'extraction automatique).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-telecharger meme si l'image existe deja",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="Lister les phrases avec leur numero, sans rien telecharger",
    )
    p.add_argument("--show", action="store_true", help="Ouvrir chaque image")
    return p.parse_args()


def resolve_api_key(provider: str, cli_key: str) -> str:
    if provider == "pollinations":
        return ""  # pas de cle API
    if cli_key:
        return cli_key
    return os.environ.get(
        "UNSPLASH_ACCESS_KEY" if provider == "unsplash" else "PEXELS_API_KEY",
        "",
    )


def load_phrases(args) -> list:
    if args.phrases:
        print(f"Phrases en argument : {len(args.phrases)}\n")
        return args.phrases
    if not args.file.exists():
        print(f"[Erreur] Fichier introuvable : {args.file}", file=sys.stderr)
        return []
    phrases = load_phrases_from_file(args.file)
    print(f"Phrases chargees depuis {args.file.name} : {len(phrases)}\n")
    return phrases


def main() -> int:
    args = parse_args()

    phrases = load_phrases(args)
    if not phrases:
        return 1

    if args.list:
        print("Phrases disponibles :")
        for i, p in enumerate(phrases, start=1):
            path = output_path_for(i, p)
            mark = "[OK]" if path.exists() else "[--]"
            print(f"  {mark} {i:>2}. {p}")
        print("\nUtilise --phrase N pour (re)generer la phrase numero N.")
        return 0

    api_key = resolve_api_key(args.provider, args.api_key)
    if args.provider in ("unsplash", "pexels") and not api_key:
        env_var = "UNSPLASH_ACCESS_KEY" if args.provider == "unsplash" else "PEXELS_API_KEY"
        signup = ("https://unsplash.com/developers"
                  if args.provider == "unsplash"
                  else "https://www.pexels.com/api/")
        print(f"[Erreur] Cle API manquante pour --provider {args.provider}.", file=sys.stderr)
        print(f"  1. Inscription gratuite : {signup}")
        print(f"  2. set {env_var}=ta_cle  (puis relancer)")
        print(f"     OU : --api-key ta_cle")
        print(f"  Astuce : --provider pollinations ne necessite aucune cle.")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fournisseur : {args.provider}")
    print(f"Dossier de sortie : {OUTPUT_DIR}\n")

    # Mode 1 : une phrase precise
    if args.phrase is not None:
        if args.phrase < 1 or args.phrase > len(phrases):
            print(f"[Erreur] --phrase {args.phrase} hors limites (1..{len(phrases)})",
                  file=sys.stderr)
            return 1
        idx = args.phrase
        fr = phrases[idx - 1]
        # En mode --phrase, on suppose qu'on veut retelecharger : skip_existing=False
        ok = process_one_phrase(
            idx=idx, fr=fr, total=len(phrases),
            provider=args.provider, api_key=api_key,
            page=args.page, seed=args.seed, custom_query=args.query,
            skip_existing=False, show=args.show,
        )
        print(f"Termine : {'1' if ok else '0'}/1 image telechargee.")
        return 0

    # Mode 2 : toutes les phrases
    skip_existing = not args.force
    if skip_existing:
        print("(Saute les images deja presentes. --force pour tout retelecharger.)\n")

    success = 0
    for i, fr in enumerate(phrases, start=1):
        if process_one_phrase(
            idx=i, fr=fr, total=len(phrases),
            provider=args.provider, api_key=api_key,
            page=args.page, seed=args.seed, custom_query=args.query,
            skip_existing=skip_existing, show=args.show,
        ):
            success += 1
        time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"Termine : {success}/{len(phrases)} image(s) telechargee(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
