"""Renderiza um layout HTML em PNG com o Chrome headless.

Uso: python renderizar_png.py layout.html saida.png 1080x1350

O HTML é servido por um servidor local preso à pasta dele (127.0.0.1), não aberto como arquivo: uma página
file:// lê qualquer arquivo do PC (ex.: um <iframe> com o .env) e o print levaria isso para a entrega (revisão de
30/10/2026). Imagens e fontes precisam estar na pasta do HTML (caminhos relativos); fontes da web continuam valendo.
"""

import functools
import http.server
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote

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
    # Caminho absoluto file:/// para a própria pasta (peça #81) vira relativo, numa cópia apagada no fim.
    texto = html.read_text(encoding="utf-8", errors="replace")
    base = re.compile(re.escape(html.parent.as_uri() + "/"), re.IGNORECASE)
    pagina = html
    if base.search(texto):
        pagina = html.with_name(f"_render_{html.name}")
        pagina.write_text(base.sub("", texto), encoding="utf-8")
    quieto = type("Quieto", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *_a: None})
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(quieto, directory=str(html.parent)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        endereco = f"http://127.0.0.1:{servidor.server_address[1]}/{quote(pagina.name)}"
        subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        f"--window-size={largura},{altura}", f"--screenshot={saida}", endereco],
                       check=True, capture_output=True, timeout=120)
    finally:
        servidor.shutdown()
        if pagina != html:
            pagina.unlink(missing_ok=True)
    print(f"PNG gerado: {saida} ({largura}x{altura})")


if __name__ == "__main__":
    main()
