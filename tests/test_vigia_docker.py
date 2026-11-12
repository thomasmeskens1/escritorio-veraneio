"""Vigia do escritório (12/11/2026): religa Docker, API e trabalhador do Max depois de queda. Tudo simulado: nenhum
comando de verdade roda e nada toca o Docker."""

import sys
from pathlib import Path

import pytest


@pytest.fixture
def vigia(monkeypatch, tmp_path):
    for pasta in (Path("/repo/scripts"), Path(__file__).resolve().parents[1] / "scripts"):
        if (pasta / "vigia_docker.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            break
    else:
        pytest.skip("scripts não montado")
    import vigia_docker as v

    monkeypatch.setattr(v, "PAUSADO", tmp_path / "vigia_pausado")
    monkeypatch.setattr(v, "MANUTENCAO", tmp_path / "manutencao")
    monkeypatch.setattr(v, "LOG", tmp_path / "vigia.log")
    monkeypatch.setattr(v.time, "sleep", lambda s: None)
    monkeypatch.setattr(v, "esperar", lambda condicao, limite_s, passo_s=10: condicao())
    v.comandos = []
    monkeypatch.setattr(v, "_rodar", lambda comando, timeout=60: v.comandos.append(comando[1:3]))
    monkeypatch.setattr(v, "_powershell", lambda comando: v.comandos.append(comando))
    return v


def _estado(v, monkeypatch, docker=(True,), api=(True,), trabalhador=True):
    docker, api = list(docker), list(api)
    monkeypatch.setattr(v, "docker_ok", lambda: docker.pop(0) if len(docker) > 1 else docker[0])
    monkeypatch.setattr(v, "api_ok", lambda: api.pop(0) if len(api) > 1 else api[0])
    monkeypatch.setattr(v, "trabalhador_ok", lambda: trabalhador)


def test_tudo_no_ar_nao_faz_nada(vigia, monkeypatch):
    _estado(vigia, monkeypatch)
    assert vigia.rodada() == "ok" and vigia.comandos == []


def test_docker_caiu_liga_e_espera_a_api(vigia, monkeypatch):
    _estado(vigia, monkeypatch, docker=(False, True), api=(False, True))
    assert vigia.rodada() == "docker,api"
    assert vigia.comandos == [["desktop", "start"]]  # a API voltou sozinha: sem compose


def test_api_parada_sobe_os_conteineres(vigia, monkeypatch):
    _estado(vigia, monkeypatch, api=(False, False, True))
    assert vigia.rodada() == "api" and ["compose", "up"] in vigia.comandos


def test_respeita_manutencao_e_pausa(vigia, monkeypatch):
    _estado(vigia, monkeypatch, api=(False,))
    vigia.MANUTENCAO.write_text("")
    assert vigia.rodada() == "manutencao" and vigia.comandos == []
    vigia.PAUSADO.write_text("")
    assert vigia.rodada() == "pausado"


def test_trabalhador_parado_dispara_a_tarefa(vigia, monkeypatch):
    _estado(vigia, monkeypatch, trabalhador=False)
    assert vigia.rodada() == "trabalhador" and "Start-ScheduledTask" in vigia.comandos[0]
