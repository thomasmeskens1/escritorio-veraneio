"""Trabalhos do Max além da produção: ler anexos do chat (Claude Code) e reler o site para o Cérebro."""

from pathlib import Path

import comum
import site_casaveraneio
from comum import log

TEMPO_ANEXO = 170          # o backend espera até 180 s pela descrição


# --- anexo ---------------------------------------------------------------------------------

def arquivo_do_anexo(payload: dict) -> Path:
    """Caminho local do anexo (relativo a backend/), sempre dentro de backend/dados/anexos."""
    pasta = (comum.DADOS / "anexos").resolve()
    arquivo = (comum.BACKEND_DIR / payload["arquivo"]).resolve()
    if arquivo.parent != pasta:
        raise RuntimeError("Caminho de anexo fora da pasta de anexos.")
    if not arquivo.is_file():
        raise RuntimeError(f"Anexo não encontrado neste PC: {arquivo.name}")
    return arquivo


def montar_anexo(payload: dict) -> tuple[list[str], str, Path]:
    """(comando, prompt, pasta de trabalho) para o Claude Code ler o anexo."""
    arquivo = arquivo_do_anexo(payload)
    comando = [comum.claude_exe(), "-p", "--output-format", "json", "--max-turns", "4", "--allowedTools", "Read"]
    tipo = "PDF" if payload.get("mime") == "application/pdf" else "imagem"
    prompt = (f"{payload.get('prompt') or 'Descreva o anexo em português do Brasil, de forma objetiva.'}\n\n"
              f"Arquivo ({tipo}): ./{arquivo.name} (nome original: {payload.get('nome', arquivo.name)}). "
              "Abra-o com a ferramenta Read e responda apenas com a descrição.")
    return comando, prompt, arquivo.parent


def executar_anexo(payload: dict) -> str:
    comando, prompt, pasta = montar_anexo(payload)
    descricao = comum.rodar_claude(comando, prompt, pasta, TEMPO_ANEXO).strip()
    if not descricao:
        raise RuntimeError("O Claude Code não devolveu descrição.")
    return descricao


# --- site ----------------------------------------------------------------------------------

def executar_site(payload: dict) -> str:
    """O site é renderizado pelo Chrome e lido direto (sem o Claude Code): números exatos e sem custo."""
    log("   lendo o site com o Chrome")
    return site_casaveraneio.resumo_texto(site_casaveraneio.sincronizar())


EXECUTORES = {"anexo": executar_anexo, "site": executar_site}


def executar(trabalho: dict) -> None:
    """Roda o trabalho e informa o backend (concluir/falhar), sem nunca derrubar o trabalhador."""
    log(f"Trabalho #{trabalho['id']} ({trabalho['tipo']})")
    try:
        executor = EXECUTORES.get(trabalho["tipo"])
        if not executor:
            raise RuntimeError(f"Tipo de trabalho desconhecido: {trabalho['tipo']}")
        resultado = executor(trabalho.get("payload") or {})
        comum.chamar("POST", f"/api/producao/trabalhos/{trabalho['id']}/concluir", {"resultado": resultado})
        log(f"   concluído ({len(resultado)} caracteres)")
    except Exception as erro:
        log(f"   falhou: {erro}")
        try:
            comum.chamar("POST", f"/api/producao/trabalhos/{trabalho['id']}/falhar", {"erro": str(erro)})
        except Exception as erro_api:
            log(f"   não foi possível avisar a falha ao backend: {erro_api}")
