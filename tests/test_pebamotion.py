"""Cálculos do pebamotion (scripts/pebamotion.py): configuração, linha do tempo, corte no silêncio e mixagem.
Nenhum teste abre navegador ou chama o ffmpeg: os sinais são matrizes numpy."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

_ARQUIVO = Path(__file__).resolve().parents[1] / "scripts" / "pebamotion.py"
_spec = importlib.util.spec_from_file_location("pebamotion", _ARQUIVO)
pm = importlib.util.module_from_spec(_spec)
sys.modules["pebamotion"] = pm
_spec.loader.exec_module(pm)

SR = pm.SR


def _episodio(**mudancas):
    dados = {
        "episodio": "xx-001",
        "duracao": 10.0,
        "inicio": 0.5,
        "cortes": [
            {"id": "a", "persona": "davi", "entrada": 10.0, "saida": 12.0, "respiro": 0.0, "texto": "um dois três"},
            {"id": "b", "persona": "camila", "entrada": 30.0, "saida": 33.0, "respiro": 0.25, "texto": "quatro cinco"},
        ],
        "trilha": {"nivel": 0.3, "efeitos": 0.5, "trechos": []},
        "encerramento": {"nivel": 0.5, "efeitos": 0.5, "trechos": []},
        "limites_de_render": [3.0, 6.0],
        "variantes": {"": {}},
    }
    dados.update(mudancas)
    return dados


# ---------------------------------------------------------------- configuração

def test_episodio_valido_passa():
    assert pm.validar_episodio(_episodio())["episodio"] == "xx-001"


@pytest.mark.parametrize("chave", ["cortes", "trilha", "variantes", "limites_de_render"])
def test_episodio_sem_chave_obrigatoria(chave):
    dados = _episodio()
    del dados[chave]
    with pytest.raises(ValueError, match=chave):
        pm.validar_episodio(dados)


@pytest.mark.parametrize("mudanca, mensagem", [
    ({"id": "a"}, "repetido"),
    ({"persona": "helena"}, "persona"),
    ({"entrada": 40.0}, "entrada depois"),
    ({"texto": "  "}, "sem texto"),
])
def test_recorte_invalido(mudanca, mensagem):
    dados = _episodio()
    dados["cortes"][1].update(mudanca)
    with pytest.raises(ValueError, match=mensagem):
        pm.validar_episodio(dados)


def test_voz_que_nao_cabe_na_duracao():
    with pytest.raises(ValueError, match="não cabe"):
        pm.validar_episodio(_episodio(duracao=5.0))


@pytest.mark.parametrize("limites", [[6.0, 3.0], [0.0, 3.0], [3.0, 10.0]])
def test_limites_de_render_fora_de_ordem_ou_da_duracao(limites):
    with pytest.raises(ValueError, match="limites_de_render"):
        pm.validar_episodio(_episodio(limites_de_render=limites))


def test_da_001_e_valido_e_a_linha_segue_os_recortes():
    dados = pm.carregar_episodio("da-001")
    linha = json.loads((pm.MODULO / "episodios" / "da-001" / "linha.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in linha["clipes"]] == [c["id"] for c in dados["cortes"]]
    cursor = dados["inicio"]
    for i, (corte, clipe) in enumerate(zip(dados["cortes"], linha["clipes"])):
        cursor += corte["respiro"] if i else 0
        assert clipe["inicio"] == pytest.approx(cursor, abs=1e-3)
        assert clipe["fim"] - clipe["inicio"] == pytest.approx(corte["saida"] - corte["entrada"], abs=1e-3)
        assert " ".join(p[0] for p in clipe["palavras"]) == corte["texto"]
        cursor += corte["saida"] - corte["entrada"]


def test_da_001_fala_literal_do_roteiro():
    """Todo recorte é trecho do roteiro publicado, sem edição (comparando sem pontuação nem caixa)."""
    roteiro = json.loads((pm.RAIZ / "episodios" / "da-001" / "roteiro.json").read_text(encoding="utf-8"))
    normalizar = lambda s: re.sub(r"[^\w\s]", "", s.lower()).split()
    falas = [" ".join(normalizar(f["texto"])) for f in roteiro["falas"]]
    for corte in pm.carregar_episodio("da-001")["cortes"]:
        trecho = " ".join(normalizar(corte["texto"]))
        assert any(trecho in fala for fala in falas), corte["id"]


# ---------------------------------------------------------------- linha do tempo

def test_alinhar_com_mesmo_numero_de_palavras_herda_os_tempos():
    ouvidas = [["para", 1.0, 1.2], ["o", 1.2, 1.3], ["banco", 1.3, 1.8]]
    assert pm.alinhar("pra o banco.", ouvidas) == [["pra", 1.0, 1.2], ["o", 1.2, 1.3], ["banco.", 1.3, 1.8]]


def test_alinhar_com_contagem_diferente_reparte_o_intervalo_pelo_tamanho():
    ouvidas = [["para", 2.0, 2.2], ["o", 2.2, 2.3], ["banco", 2.3, 3.0]]
    saida = pm.alinhar("pro banco", ouvidas)
    assert [p[0] for p in saida] == ["pro", "banco"]
    assert saida[0][1] == 2.0 and saida[-1][2] == pytest.approx(3.0)
    assert saida[0][2] == pytest.approx(saida[1][1])
    assert saida[1][2] - saida[1][1] > saida[0][2] - saida[0][1]


def test_alinhar_sem_palavras_ouvidas_falha():
    with pytest.raises(ValueError):
        pm.alinhar("algo", [])


def test_montar_linha_posiciona_com_respiro_e_desloca_as_palavras():
    palavras = [["um", 10.1, 10.4], ["dois", 10.5, 10.9], ["três", 11.0, 11.8],
                ["quatro", 30.2, 30.9], ["cinco", 31.0, 32.5], ["fora", 40.0, 40.5]]
    linha = pm.montar_linha(_episodio(), palavras)
    a, b = linha["clipes"]
    assert (a["inicio"], a["fim"]) == (0.5, 2.5)
    assert (b["inicio"], b["fim"]) == (2.75, 5.75)
    assert a["palavras"][0] == ["um", 0.6, 0.9]
    assert b["palavras"][0] == ["quatro", 2.95, 3.65]
    assert linha["fim_da_voz"] == 5.75


def test_palavras_no_intervalo_tolera_o_arredondamento_do_reconhecedor():
    palavras = [["antes", 9.0, 9.9], ["borda", 9.97, 10.3], ["fim", 11.9, 12.1], ["depois", 12.3, 12.6]]
    assert [p[0] for p in pm.palavras_no_intervalo(palavras, 10.0, 12.0)] == ["borda", "fim"]


def test_vale_de_energia_acha_o_silencio_entre_palavras():
    sr = 16_000
    t = np.arange(int(2.0 * sr)) / sr
    sinal = np.sin(2 * np.pi * 220 * t) * 0.5
    sinal[int(0.95 * sr):int(1.15 * sr)] = 0
    db = pm.energia_db(sinal, sr)
    corte = pm.vale_de_energia(db, 1.2, antes=0.35, depois=0.02)
    assert 0.95 <= corte <= 1.15


# ---------------------------------------------------------------- mixagem

def test_envelope_de_voz_fica_em_zero_no_silencio_e_sobe_com_a_voz():
    voz = np.zeros(SR * 2)
    voz[SR // 2: SR] = np.sin(2 * np.pi * 200 * np.arange(SR // 2) / SR) * 0.3
    env = pm.envelope_de_voz(voz)
    assert env[: SR // 4].max() == 0
    assert env[int(0.8 * SR)] > 0.95
    assert 0.2 < env[int(1.2 * SR)] < 0.9, "a soltura é lenta: 200 ms depois ainda segura a trilha"


def test_colocar_aplica_rampas_e_corta_no_fim_da_pista():
    pista = np.zeros((SR, 2))
    trecho = np.ones((SR // 2, 2))
    pm.colocar(pista, trecho, em=0.75, fade_in=0.1, fade_out=0.0)
    inicio = int(0.75 * SR)
    assert pista[inicio - 1].sum() == 0
    assert pista[inicio, 0] == 0
    assert pista[inicio + int(0.1 * SR), 0] == pytest.approx(1.0)
    assert pista[-1, 0] == 1.0


def test_camada_de_efeitos_soma_no_instante_e_ignora_fora_da_duracao():
    pedidos = []

    def impulso(nome, variacao):
        pedidos.append((nome, variacao))
        return np.array([1.0, 0.5])

    eventos = [{"t": 0.5, "tipo": "carimbo", "ganho": 0.8}, {"t": 0.51, "tipo": "papel", "ganho": 1.0},
               {"t": 2.0, "tipo": "carimbo", "ganho": 1.0}]
    pista = pm.camada_de_efeitos(eventos, 1.0, impulso)
    assert pista[int(0.5 * SR)] == pytest.approx(0.8)
    assert pista[int(0.5 * SR) + 1] == pytest.approx(0.4)
    assert pedidos == [("carimbo", 2), ("papel", 0)]


def test_mixar_abaixa_a_trilha_sob_a_voz_e_a_versao_sem_trilha_nao_tem_musica():
    n = SR * 2
    voz = np.zeros(n)
    voz[SR:] = 0.3 * np.sin(2 * np.pi * 200 * np.arange(SR) / SR)
    musica = np.full((n, 2), 0.5)
    com, sem = pm.mixar(voz, musica, np.zeros(n), nivel_musica=0.4, ducking=0.6, nivel_efeitos=0.5)
    assert com[SR // 2, 0] == pytest.approx(0.2)
    assert np.abs(com[int(1.8 * SR):] - sem[int(1.8 * SR):]).max() == pytest.approx(0.5 * 0.4 * 0.4, rel=0.05)
    assert np.abs(sem[: SR // 2]).max() == 0


def test_todo_evento_das_cenas_tem_efeito_sintetizado():
    pytest.importorskip("scipy")
    cenas = (pm.MODULO / "episodios" / "da-001" / "cenas.js").read_text(encoding="utf-8")
    chamadas = [linha for linha in cenas.splitlines() if re.search(r"\be\(", linha)]
    tipos = {t for linha in chamadas for t in re.findall(r"[\w)],\s*'([a-z]+)'", linha)}
    assert {"carimbo", "corte", "puxao", "cava"} <= tipos
    for tipo in sorted(tipos):
        som = pm.sintetizar_efeito(tipo, np.random.default_rng(0))
        assert np.isfinite(som).all() and 0 < np.abs(som).max() <= 1.0, tipo


def test_efeito_desconhecido_falha():
    pytest.importorskip("scipy")
    with pytest.raises(ValueError, match="desconhecido"):
        pm.sintetizar_efeito("trovão", np.random.default_rng(0))
