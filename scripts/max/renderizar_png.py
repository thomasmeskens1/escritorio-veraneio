"""Renderiza um layout HTML em PNG com o Chrome headless.

Uso: python renderizar_png.py layout.html saida.png 1080x1350
"""

import shutil
import subprocess
import sys
from pathlib import Path

CHROMES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def chrome() -> str:
    for caminho in CHROMES:
        if Path(caminho).exists():
            return caminho
    encontrado = shutil.which("chrome") or shutil.which("msedge")
    if not encontrado:
        sys.exit("Chrome não encontrado.")
    return encontrado


def main() -> None:
    if len(sys.argv) != 4 or "x" not in sys.argv[3]:
        sys.exit(__doc__)
    html, saida, tamanho = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
    largura, altura = tamanho.lower().split("x")
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    f"--window-size={largura},{altura}", f"--screenshot={saida}", html.as_uri()],
                   check=True, capture_output=True, timeout=120)
    print(f"PNG gerado: {saida} ({largura}x{altura})")


if __name__ == "__main__":
    main()
