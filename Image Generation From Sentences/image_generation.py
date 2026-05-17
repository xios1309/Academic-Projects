"""
Image Generation From Sentences
================================

Pour chaque phrase en francais, ce script :
  1. Traduit la phrase en anglais (les modeles d'IA generent mieux en anglais)
  2. Genere une image via l'API publique et gratuite Pollinations.ai
  3. Sauvegarde l'image dans le dossier `outputs/`

Dependances :
    pip install requests pillow deep-translator

Utilisation :
    # Lit les phrases depuis phrases.txt (une phrase par ligne) :
    python image_generation.py

    # Ou passer des phrases directement en argument :
    python image_generation.py "un chat roux qui dort" "un coucher de soleil sur la mer"

    # Ou specifier un autre fichier :
    python image_generation.py --file mes_phrases.txt
"""

import argparse
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

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 768
DEFAULT_MODEL = "flux"  # autres options : "turbo"
REQUEST_TIMEOUT = 120   # secondes
DELAY_BETWEEN_REQUESTS = 1  # seconde, pour ne pas saturer l'API


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

def load_phrases_from_file(path: Path) -> list[str]:
    """Charge les phrases depuis un fichier texte (une phrase par ligne)."""
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def translate_fr_to_en(text: str) -> str:
    """Traduit du francais vers l'anglais. Retourne le texte original en cas d'echec."""
    if GoogleTranslator is None:
        print("  [Avertissement] deep-translator non installe, traduction ignoree.")
        return text
    try:
        return GoogleTranslator(source="fr", target="en").translate(text)
    except Exception as e:
        print(f"  [Avertissement] Traduction echouee : {e}")
        return text


def slugify(text: str, max_len: int = 60) -> str:
    """Convertit un texte en nom de fichier sur (sans accents ni caracteres speciaux)."""
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    return text[:max_len] or "image"


def generate_image(
    prompt: str,
    output_path: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    model: str = DEFAULT_MODEL,
    seed: int | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> Path:
    """Genere une image via Pollinations.ai et la sauvegarde sur disque."""
    encoded_prompt = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&model={model}&nologo=true"
    )
    if seed is not None:
        url += f"&seed={seed}"

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)

    return output_path


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def process_phrases(phrases: list[str], show: bool = False) -> None:
    """Traduit chaque phrase, genere l'image correspondante, et la sauvegarde."""
    if not phrases:
        print("Aucune phrase a traiter.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Dossier de sortie : {OUTPUT_DIR}")
    print(f"{len(phrases)} phrase(s) a traiter.\n")

    success_count = 0

    for idx, fr in enumerate(phrases, start=1):
        print(f"[{idx}/{len(phrases)}] {fr}")

        en = translate_fr_to_en(fr)
        print(f"    Prompt EN : {en}")

        filename = f"{idx:02d}_{slugify(fr)}.png"
        output_path = OUTPUT_DIR / filename

        try:
            generate_image(en, output_path)
            print(f"    Sauvegardee : {output_path}\n")
            success_count += 1

            if show:
                try:
                    Image.open(output_path).show()
                except Exception as e:
                    print(f"    [Avertissement] Impossible d'afficher l'image : {e}")

        except requests.exceptions.RequestException as e:
            print(f"    [Erreur reseau] {e}\n")
        except Exception as e:
            print(f"    [Erreur] {e}\n")

        time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"Termine : {success_count}/{len(phrases)} image(s) generee(s) dans {OUTPUT_DIR}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genere une image par phrase via Pollinations.ai",
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
        "--show",
        action="store_true",
        help="Ouvrir chaque image generee dans la visionneuse par defaut",
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

    process_phrases(phrases, show=args.show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
