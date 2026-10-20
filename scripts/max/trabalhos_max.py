"""Trabalhos do Max além da produção: ler anexos do chat e ler o site da Casa Veraneio para o Cérebro."""

from pathlib import Path

import comum
from comum import log

TEMPO_ANEXO = 170          # o backend espera até 180 s pela descrição
TEMPO_SITE = 40 * 60
PASTA_SITE = comum.CEREBRO / "SITE"
DOMINIOS_SITE = ("casaveraneio.com", "www.casaveraneio.com")
FERRAMENTAS_SITE = ",".join([*(f"WebFetch(domain:{d})" for d in DOMINIOS_SITE), "Read", "Write", "Glob"])

PROMPT_SITE = """Você é o pesquisador do Escritório Veraneio. Leia o site oficial https://www.casaveraneio.com \
(ÚNICO site permitido: não acesse nenhum outro domínio) e registre o conhecimento para o Cérebro da empresa.

1. Comece pela página inicial e siga os links internos do próprio site: páginas principais, cada lodge/casa, \
preços e tarifas, capacidade (hóspedes, quartos, camas, banheiros), comodidades e serviços, regras e políticas \
(reserva, pagamento, cancelamento, check-in/out, pets, eventos), localização, perguntas frequentes e contatos.
2. Grave na pasta atual um arquivo .md por assunto ou página (nomes curtos, minúsculos, com hífen, \
ex.: lodge-01-jundiai.md, precos.md, politicas.md, contatos.md). Cada arquivo começa com "# Título", \
depois "Fonte: <URL>" e o conteúdo em português do Brasil, em tópicos objetivos, com números exatos \
(valores, datas, capacidades, telefones, e-mails) como aparecem no site.
3. Se um arquivo com o mesmo assunto já existir, substitua pelo conteúdo atual do site. Não invente nada: \
o que não estiver no site fica de fora.
4. Grave somente arquivos .md e somente na pasta atual.

Ao terminar, responda com um resumo curto (até 6 linhas): quantas páginas leu e quais arquivos gravou."""


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

def montar_site(payload: dict) -> tuple[list[str], str, Path]:
    comando = [comum.claude_exe(), "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
               "--max-turns", "120", "--allowedTools", FERRAMENTAS_SITE]
    prompt = PROMPT_SITE
    if (extra := str(payload.get("instrucoes") or "").strip()):
        prompt += f"\n\nInstruções adicionais do dono: {extra[:1000]}"
    return comando, prompt, PASTA_SITE


def documentos_do_site(pasta: Path) -> list[dict]:
    """Um documento do Cérebro por .md gravado na pasta SITE."""
    documentos = []
    for arquivo in sorted(pasta.glob("*.md")):
        conteudo = arquivo.read_text(encoding="utf-8", errors="replace").strip()
        if not conteudo:
            continue
        primeira = conteudo.splitlines()[0].strip()
        titulo = primeira.lstrip("#").strip() if primeira.startswith("#") else arquivo.stem.replace("-", " ")
        documentos.append({"fonte_tipo": "site", "fonte_ref": f"site/{arquivo.name}",
                           "titulo": titulo[:200], "conteudo": conteudo})
    return documentos


def executar_site(payload: dict, enviar=comum.enviar_ao_cerebro) -> str:
    comando, prompt, pasta = montar_site(payload)
    pasta.mkdir(parents=True, exist_ok=True)
    log(f"   lendo o site -> {pasta}")
    resumo = comum.rodar_claude(comando, prompt, pasta, TEMPO_SITE).strip()
    documentos = documentos_do_site(pasta)
    if not documentos:
        raise RuntimeError("Nenhum arquivo .md foi gravado a partir do site.")
    enviado = enviar(documentos)
    situacao = (f"{len(documentos)} documento(s) enviados ao Cérebro." if enviado else
                f"{len(documentos)} documento(s) gravados em CÉREBRO/SITE; o envio ao Cérebro ficou pendente.")
    return f"{resumo}\n\n{situacao}"


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
