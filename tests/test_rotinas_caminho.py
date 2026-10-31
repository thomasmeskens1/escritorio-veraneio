"""Rotina agendada segue o mesmo caminho do pedido manual (conserto 14, 31/10/2026): estudo com pesquisa na web pelo
Max, prospecção pelo comercial, e a resposta volta ao chat do agente da rotina. Antes, toda rotina ia ao
orquestrador e virava conversa num modelo gratuito, sem web (prospectador-07, estrategista-20).

Tudo com fakes: nenhum Max, Monday ou prospecção real; banco temporário (tests/conftest.py).
"""

import asyncio

import pytest

import agendamentos
import atividade
import comercial
import config
import estudos
import orquestrador
import tarefas
from estado import buscar_agente

tarefas.iniciar()
DONO = "usuario.teste@exemplo.com"


class Fila:
    """Captura o que iria para cada caminho e as entregas no chat (sem rodar modelo nenhum)."""

    def __init__(self, monkeypatch):
        self.chamadas, self.avisos, self.entregues, self._fundo = [], [], [], []
        monkeypatch.setattr(config, "usa_max", lambda _login: True)
        monkeypatch.setattr(orquestrador, "nova_tarefa",
                            self._anotar("conversa"))
        monkeypatch.setattr(agendamentos.gerenciador, "enviar_para_usuario", self._aviso)
        monkeypatch.setattr(orquestrador, "_em_segundo_plano", self._fundo.append)
        monkeypatch.setattr(orquestrador, "_concluir", self._concluir)
        monkeypatch.setattr(atividade, "transmitir_estado", self._nada)

    def _anotar(self, caminho):
        async def anotar(*args, **kwargs):
            self.chamadas.append((caminho, args, kwargs))
        return anotar

    async def _aviso(self, usuario, mensagem):
        self.avisos.append((usuario, mensagem))

    async def _concluir(self, tarefa_id, modelo, resultado):
        self.entregues.append((tarefas.obter(tarefa_id), modelo, resultado.texto))

    @staticmethod
    async def _nada(*_a, **_k):
        return None

    async def terminar(self):
        while self._fundo:
            await self._fundo.pop(0)


def _linha(andar, agente, texto, empresa=None):
    return {"usuario": DONO, "andar": andar, "agente": agente, "tarefa": texto, "empresa": empresa}


def test_estudo_agendado_vai_ao_max_com_web_e_volta_ao_chat_do_agente(monkeypatch):
    fila = Fila(monkeypatch)
    pedidos = []
    monkeypatch.setattr(estudos, "prompt", lambda agente_id, texto, empresa, *a, **k: f"[{agente_id}|{empresa}] {texto}")
    monkeypatch.setattr(comercial, "pedir_ao_max", lambda prompt, limite_s=0, web=True: pedidos.append(
        (prompt, web)) or "Estudo fictício com fontes.")
    agente = buscar_agente("comercial", "estrategista")

    async def rodar():
        await agendamentos._encaminhar(_linha("comercial", "estrategista", "Faça a Matriz BCG das três empresas"),
                                       agente)
        await fila.terminar()

    asyncio.run(rodar())
    assert pedidos == [("[estrategista|*] Faça a Matriz BCG das três empresas", True)]  # pesquisa na web, no Max
    tarefa, modelo, texto = fila.entregues[0]
    assert (tarefa["usuario"], tarefa["andar"], tarefa["agente"]) == (DONO, "comercial", "estrategista")
    assert modelo == "claude-code/max" and texto == "Estudo fictício com fontes." and not fila.chamadas


def test_tendencias_agendado_usa_a_empresa_da_rotina(monkeypatch):
    fila = Fila(monkeypatch)
    iniciados = []

    async def iniciar(login, andar, agente, texto, empresa):
        iniciados.append((login, andar, agente.id, empresa))

    monkeypatch.setattr(estudos, "iniciar", iniciar)
    asyncio.run(agendamentos._encaminhar(_linha("marketing", "analista_tendencias", "Estudo das tendências do mercado",
                                                "casa_vero"), buscar_agente("marketing", "analista_tendencias")))
    assert iniciados == [(DONO, "marketing", "analista_tendencias", "casa_vero")] and not fila.chamadas


def test_prospeccao_agendada_traz_a_previa_no_chat_sem_criar_leads(tmp_path, monkeypatch):
    fila = Fila(monkeypatch)
    monkeypatch.setattr(comercial, "PASTA_PREVIAS", tmp_path)
    monkeypatch.setattr(comercial, "_evento", lambda *_a: None)
    monkeypatch.setattr(comercial, "prompt_prospeccao", lambda pedido, quantidade: f"{quantidade}: {pedido}")
    monkeypatch.setattr(comercial, "ja_conhecidos", lambda: (set(), set()))
    monkeypatch.setattr(comercial, "criar_lead", lambda _lead: pytest.fail("rotina nunca cria lead no Monday"))
    monkeypatch.setattr(comercial, "pedir_ao_max", lambda prompt, *a, **k: (
        '<<LEADS>>[{"empresa": "Empresa Teste", "site": "https://exemplo.com", "email": "eventos@exemplo.com", '
        '"telefone": "(19) 3333-4444", "motivo": "teste"}]<<FIM>>'))
    agente = buscar_agente("comercial", "prospectador")

    async def rodar():
        await agendamentos._encaminhar(_linha("comercial", "prospectador", "Prospecte 5 indústrias em Campinas"),
                                       agente)
        await fila.terminar()

    asyncio.run(rodar())
    tarefa, modelo, texto = fila.entregues[0]
    assert (tarefa["andar"], tarefa["agente"], tarefa["empresa"]) == ("comercial", "prospectador", "cv_corporativo")
    assert texto.startswith(f"Prévia #{tarefa['id']}: 1 empresa") and "NÃO criadas" in texto
    assert (tmp_path / f"{tarefa['id']}.json").exists() and not fila.chamadas


def test_rotina_nunca_aprova_previa_e_conversa_segue_normal(monkeypatch):
    fila = Fila(monkeypatch)
    monkeypatch.setattr(comercial, "iniciar", lambda *_a: pytest.fail("rotina não aprova prévia"))
    asyncio.run(agendamentos._encaminhar(_linha("comercial", "prospectador", "Crie os leads da prévia #3"),
                                         buscar_agente("comercial", "prospectador")))
    assert fila.avisos and "aprovação é sempre no chat" in fila.avisos[0][1]["texto"]
    asyncio.run(agendamentos._encaminhar(_linha("marketing", "copywriter", "Escreva a legenda do post", "casa_vero"),
                                         buscar_agente("marketing", "copywriter")))
    caminho, args, kwargs = fila.chamadas[0]
    assert caminho == "conversa" and args[1:3] == ("marketing", buscar_agente("marketing", "copywriter"))
    assert kwargs == {"empresa": "casa_vero"}


def test_disparo_da_rotina_usa_o_mesmo_caminho(monkeypatch):
    """_executar (o job do agendador) passa pelas checagens de conta e acesso e chega ao estudo."""
    import auth

    fila = Fila(monkeypatch)
    iniciados = []

    async def iniciar(login, andar, agente, texto, empresa):
        iniciados.append((login, agente.id, texto))

    monkeypatch.setattr(estudos, "iniciar", iniciar)
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: {DONO: {"ativo": True}})
    monkeypatch.setattr(agendamentos.acesso, "pode_usar", lambda *_a: True)
    rotina = agendamentos.criar(DONO, "comercial", "estrategista", "Diagnóstico estratégico do mês",
                                {"tipo": "cron", "hora": "7", "minuto": 0}, "Todo dia 1 do mês às 07:00", None)
    asyncio.run(agendamentos._executar(rotina["id"]))
    assert iniciados == [(DONO, "estrategista", "Diagnóstico estratégico do mês")]
    assert fila.avisos[0][1]["titulo"] == "Rotina em execução"
    agendamentos.desativar(rotina["id"])
