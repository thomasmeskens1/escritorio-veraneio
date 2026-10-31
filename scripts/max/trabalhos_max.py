"""Trabalhos do Max além da produção: ler anexos do chat, reler o site e responder tarefas de texto (no lugar da API)."""

import shutil
import tempfile
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


def comando_anexo() -> list[str]:
    """Só a ferramenta Read, liberada só dentro da pasta temporária do anexo (brainstorm de 31/10/2026,
    despachante-25): antes "Read" sem caminho deixava um PDF com instrução escondida levar a leitura ao .env do PC."""
    return [comum.claude_exe(), "-p", "--output-format", "json", "--max-turns", "4", "--tools", "Read",
            "--allowedTools", "Read(./**)"]


def montar_anexo(payload: dict) -> tuple[list[str], str, Path]:
    """(comando, prompt, pasta de trabalho) para o Claude Code ler o anexo. Revisão de 30/10/2026: a pasta de trabalho
    era a dos anexos de TODOS os usuários; agora é uma pasta temporária só com este arquivo (apagada no fim)."""
    original = arquivo_do_anexo(payload)
    pasta = Path(tempfile.mkdtemp(prefix="anexo-", dir=comum.TRABALHO))
    arquivo = pasta / original.name
    shutil.copy2(original, arquivo)
    comando = comando_anexo()
    tipo ="PDF" if payload.get("mime") == "application/pdf" else "imagem"
    prompt = (f"{payload.get('prompt') or 'Descreva o anexo em português do Brasil, de forma objetiva.'}\n\n"
              f"Arquivo ({tipo}): ./{arquivo.name} (nome original: {payload.get('nome', arquivo.name)}). "
              "Abra-o com a ferramenta Read e responda apenas com a descrição.")
    return comando, prompt, arquivo.parent


def executar_anexo(payload: dict) -> str:
    comando, prompt, pasta = montar_anexo(payload)
    try:
        descricao = comum.rodar_claude(comando, prompt, pasta, TEMPO_ANEXO, cancelado=_cancelado,
                                     tipo="anexo").strip()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    if not descricao:
        raise RuntimeError("O Claude Code não devolveu descrição.")
    return descricao


# --- site ----------------------------------------------------------------------------------

def executar_site(payload: dict) -> str:
    """O site é renderizado pelo Chrome e lido direto (sem o Claude Code): números exatos e sem custo."""
    log("   lendo o site com o Chrome")
    return site_casaveraneio.resumo_texto(site_casaveraneio.sincronizar())


# --- texto (tarefa de agente pelo plano Max, no lugar da API) -------------------------------

PASTA_TEXTO = comum.TRABALHO / "max_texto"  # fora do repositório (sem .claude/ do projeto)


def executar_texto(payload: dict) -> str:
    """O pedido já vem completo (persona, diretrizes, Cérebro e tarefa); o Claude Code só escreve a resposta."""
    PASTA_TEXTO.mkdir(parents=True, exist_ok=True)
    # Só escreve a resposta: nenhuma ferramenta (lista de permissão vazia, não lista de bloqueio) e nenhum MCP.
    comando = [comum.claude_exe(), "-p", "--output-format", "json", "--max-turns", "3", "--tools", ""]
    texto = comum.rodar_claude(comando, payload["prompt"], PASTA_TEXTO, min(int(payload.get("limite_s", 900)), 900),
                               cancelado=_cancelado, tipo="texto")
    if not texto.strip():
        raise RuntimeError("O Claude Code não devolveu texto.")
    return texto.strip()


# --- prospecção (Prospectador do Comercial: pesquisa de empresas na web) --------------------------------------

PASTA_PROSPECCAO = comum.TRABALHO / "prospeccao"  # fora do repositório


def executar_prospeccao(payload: dict) -> str:
    """O pedido vem pronto do backend (comercial.py); o Claude Code só pesquisa em páginas públicas e devolve o
    bloco JSON. Ferramentas: só WebSearch e WebFetch (sem arquivos, Bash nem MCP). Quem cria os leads e valida os
    contatos (LGPD) é o backend. `web: false` (pedido com a carteira nominal, ex.: persona): nenhuma ferramenta."""
    PASTA_PROSPECCAO.mkdir(parents=True, exist_ok=True)
    if payload.get("web", True) is False:
        comando = [comum.claude_exe(), "-p", "--output-format", "json", "--max-turns", "3", "--tools", ""]
    else:
        comando = [comum.claude_exe(), "-p", "--output-format", "json", "--max-turns", "80",
                   "--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch"]
    texto = comum.rodar_claude(comando, payload["prompt"], PASTA_PROSPECCAO, min(int(payload.get("limite_s", 2400)), 2400),
                               cancelado=_cancelado, tipo="prospeccao")
    if not texto.strip():
        raise RuntimeError("O Claude Code não devolveu a pesquisa.")
    return texto.strip()


EXECUTORES = {"anexo": executar_anexo, "site": executar_site, "texto": executar_texto,
              "prospeccao": executar_prospeccao}


_em_execucao: int | None = None  # trabalho rodando agora (um por vez)


def _cancelado() -> bool:
    """O backend cancelou o trabalho em execução? (tempo esgotado ou reinício: ninguém espera mais o resultado)"""
    try:
        return comum.chamar("GET", f"/api/producao/trabalhos/{_em_execucao}/status").get("status") == "cancelado"
    except Exception:
        return False  # sem resposta do backend: segue (o tempo limite continua valendo)


def executar(trabalho: dict) -> None:
    """Roda o trabalho e informa o backend (concluir/falhar). Só repassa comum.MaxSemCota (o trabalhador pausa)."""
    global _em_execucao
    _em_execucao = trabalho["id"]
    log(f"Trabalho #{trabalho['id']} ({trabalho['tipo']})")
    comum.zerar_uso()  # medição do Max: o consumo deste trabalho vai junto com a conclusão/falha
    try:
        executor = EXECUTORES.get(trabalho["tipo"])
        if not executor:
            raise RuntimeError(f"Tipo de trabalho desconhecido: {trabalho['tipo']}")
        resultado = executor(trabalho.get("payload") or {})
        comum.chamar("POST", f"/api/producao/trabalhos/{trabalho['id']}/concluir", {"resultado": resultado,
                                                                                   "uso": comum.uso_acumulado()})
        log(f"   concluído ({len(resultado)} caracteres)")
    except Exception as erro:
        log(f"   falhou: {erro}")
        try:
            comum.chamar("POST", f"/api/producao/trabalhos/{trabalho['id']}/falhar", {"erro": str(erro),
                                                                                  "uso": comum.uso_acumulado()})
        except Exception as erro_api:
            log(f"   não foi possível avisar a falha ao backend: {erro_api}")
        if isinstance(erro, comum.MaxSemCota):
            raise  # o trabalhador pausa a fila até a cota voltar
