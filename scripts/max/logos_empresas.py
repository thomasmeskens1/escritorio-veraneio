"""Logo certo de cada empresa (Onda 1 de novembro, 11/11/2026; moviemaker-18, editor_video-18 e gestor_trafego-04).

Uma tabela só, com os arquivos de CÉREBRO/MARCAS de cada empresa, para o motion.py (apelidos "clara" e "escura",
iguais nas três marcas) e para a conferência da entrega no trabalhador: a peça que sai com o logo de outra empresa,
ou numa pasta com o prefixo de outra empresa, ganha um aviso antes do Drive. Sem reconhecer imagem: compara o nome e
o conteúdo (hash) dos arquivos da peça com os logos oficiais das outras marcas.
"""

import hashlib
import os
import re
from pathlib import Path

# empresa: pasta em CÉREBRO/MARCAS, nome no aviso e os apelidos. "clara" = logo claro, para foto ou fundo escuro
# (Verde); "escura" = logo escuro, para fundo Creme ou claro; "caramelo" = versão em cor sobre Verde.
LOGOS = {
    "casa_veraneio": {"pasta": "CASA_VERANEIO", "nome": "Casa Veraneio", "clara": "logo_branca.png",
                      "caramelo": "logo_caramelo_texto_creme.png", "escura": "logo_preta.png"},
    "cv_corporativo": {"pasta": "CORPORATIVO", "nome": "Corporativo", "clara": "logo_corp_branca.png",
                       "caramelo": "logo_corp_caramelo_texto_branco.png", "escura": "logo_corp_verde.png"},
    "casa_vero": {"pasta": "CASA_VERO", "nome": "Casa Vero", "clara": "logo_vero_caramelo_creme.png",
                  "caramelo": "logo_vero_caramelo_creme.png", "escura": "logo_vero_verde_caramelo.png"},
}
APELIDOS = ("clara", "escura", "caramelo")
ANTIGOS = {"branca": "clara"}  # motion.json antigo: "branca" vale como a "clara" da empresa da peça
# Casa Veraneio não tem logo completo em Verde (manual 01): em fundo claro sai o preto monocromático, com aviso.
SUBSTITUTOS = {("casa_veraneio", "escura"): "não há logo completo em Verde da Casa Veraneio; usei logo_preta.png "
                                            "(monocromático). Em fundo claro prefira simbolo_verde.png + nome em texto"}
SIGLAS = {"casa_veraneio": "VERANEIO", "cv_corporativo": "CORP", "casa_vero": "VERO"}
PADRAO = "casa_veraneio"
VARIAVEL = "VERANEIO_EMPRESA"  # o trabalhador põe no ambiente da produção: a empresa da peça manda


def empresa_valida(empresa: str | None) -> str:
    return empresa if empresa in LOGOS else PADRAO


def arquivo_do_apelido(empresa: str, apelido: str) -> tuple[str, str]:
    """("logo_corp_branca.png", aviso ou "") para o apelido ("clara", "escura", "caramelo" ou o antigo "branca")."""
    empresa = empresa_valida(empresa)
    apelido = ANTIGOS.get(apelido, apelido)
    if apelido not in APELIDOS:
        raise ValueError(f"logo desconhecido: {apelido!r} (use {', '.join(APELIDOS)})")
    return LOGOS[empresa][apelido], SUBSTITUTOS.get((empresa, apelido), "")


def nomes_da_empresa(empresa: str) -> set[str]:
    return {LOGOS[empresa][a] for a in APELIDOS}


def dono_do_nome(nome: str) -> str | None:
    """Empresa dona de um arquivo de logo pelo nome (logo_corp_*, logo_vero_* ou os da Casa Veraneio); None = outro."""
    nome = Path(nome).name.lower()
    if nome.startswith("logo_corp"):
        return "cv_corporativo"
    if nome.startswith("logo_vero"):
        return "casa_vero"
    return "casa_veraneio" if nome in nomes_da_empresa("casa_veraneio") else None


def logo_de_outra(empresa: str, caminho: str) -> str | None:
    """Empresa (outra que não `empresa`) dona do logo citado pelo caminho: pelo nome ou pela pasta da marca."""
    empresa = empresa_valida(empresa)
    dono = dono_do_nome(caminho)
    partes = {p.upper() for p in Path(str(caminho).replace("\\", "/")).parts[:-1]}
    for outra, dados in LOGOS.items():
        if outra != empresa and (dono == outra or dados["pasta"] in partes):
            return outra
    return None


def empresa_do_ambiente(declarada: str | None = None) -> str:
    """Empresa da peça: a do trabalhador (ambiente) manda; o "empresa" do motion.json precisa bater com ela."""
    do_ambiente = os.getenv(VARIAVEL) or ""
    if declarada and do_ambiente and declarada != do_ambiente:
        raise ValueError(f"motion.json diz \"empresa\": \"{declarada}\", mas esta peça é de {LOGOS[empresa_valida(do_ambiente)]['nome']} "
                         f"({do_ambiente}). Nunca use logo ou vinheta de outra empresa.")
    escolhida = do_ambiente or declarada or PADRAO
    if escolhida not in LOGOS:
        raise ValueError(f"empresa desconhecida: {escolhida!r} (use {', '.join(LOGOS)})")
    return escolhida


# ---------------------------------------------------------------- conferência da entrega (trabalhador)

PREFIXO_PASTA = re.compile(r"^\s*([A-ZÀ-Ú]+)\s*｜")
TEXTOS = {".html", ".htm", ".json", ".css", ".py"}
IGNORAR = {"_referencias", "anteriores"}


def _hash(arquivo: Path) -> str:
    return hashlib.sha256(arquivo.read_bytes()).hexdigest()


def hashes_das_outras(empresa: str, marcas: Path) -> dict[str, tuple[str, str]]:
    """hash -> (empresa, nome do arquivo) de todo PNG das pastas das OUTRAS empresas em CÉREBRO/MARCAS."""
    achados = {}
    for outra, dados in LOGOS.items():
        pasta = Path(marcas) / dados["pasta"]
        if outra == empresa or not pasta.is_dir():
            continue
        for arquivo in pasta.glob("*.png"):
            try:
                achados[_hash(arquivo)] = (outra, arquivo.name)
            except OSError:
                continue
    return achados


def conferir(rascunho: Path, empresa: str, pasta_entrega: str, marcas: Path) -> list[str]:
    """Avisos de marca da peça ([] = nada errado): pasta do Drive com prefixo de outra empresa e logo de outra
    empresa no rascunho (arquivo igual ao oficial, com o nome dele ou citado num HTML/JSON)."""
    empresa = empresa_valida(empresa)
    avisos = []
    achado = PREFIXO_PASTA.match(Path(pasta_entrega).name)
    sigla = achado.group(1) if achado else ""
    dono_pasta = next((e for e, s in SIGLAS.items() if s == sigla), None)
    if dono_pasta and dono_pasta != empresa:
        avisos.append(f"a pasta \"{Path(pasta_entrega).name}\" tem o prefixo de {LOGOS[dono_pasta]['nome']}, mas a "
                      f"peça é de {LOGOS[empresa]['nome']}: confira a empresa antes de publicar")
    hashes = hashes_das_outras(empresa, marcas)
    nomes_outras = {n.lower(): e for e, d in LOGOS.items() if e != empresa for n in nomes_da_empresa(e)}
    vistos = set()
    for arquivo in sorted(Path(rascunho).rglob("*")) if Path(rascunho).is_dir() else []:
        relativo = arquivo.relative_to(rascunho)
        if not arquivo.is_file() or any(p in IGNORAR for p in relativo.parts[:-1]):
            continue
        dono = None
        if arquivo.suffix.lower() == ".png":
            dono = logo_de_outra(empresa, arquivo.name)
            if not dono:
                try:
                    dono = hashes.get(_hash(arquivo), (None,))[0]
                except OSError:
                    dono = None
        elif arquivo.suffix.lower() in TEXTOS and arquivo.stat().st_size < 2_000_000:
            try:
                texto = arquivo.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            dono = next((e for n, e in nomes_outras.items() if n in texto), None)
        if dono and (relativo.as_posix(), dono) not in vistos:
            vistos.add((relativo.as_posix(), dono))
            avisos.append(f"{relativo.as_posix()} usa o logo de {LOGOS[dono]['nome']}")
    return avisos


def linha_do_resumo(avisos: list[str], empresa: str) -> str:
    if not avisos:
        return ""
    return (f"🔴 Marca: esta peça é de {LOGOS[empresa_valida(empresa)]['nome']}, mas " + "; ".join(avisos[:6])
            + (f" (e mais {len(avisos) - 6})" if len(avisos) > 6 else "")
            + ". Nunca publique com logo de outra empresa: peça um ajuste.")
