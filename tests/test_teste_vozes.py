import json
import random

import pytest
import yaml

from podcast.dominio import Fala
from podcast.teste_vozes import (
    ARQUIVO_AVALIACAO,
    ARQUIVO_GABARITO,
    CRITERIOS,
    carregar_trecho,
    formatar_relatorio,
    gerar,
    main,
    revelar,
)
from tests.conftest import ProvedorFalso, ProvedorQuebrado


@pytest.fixture
def falas(davi, helena):
    return [Fala(davi, "Fala, pessoal!"), Fala(helena, "Tá, e qual é o trade-off?")]


@pytest.fixture
def provedores():
    return [ProvedorFalso("alfa", 300), ProvedorFalso("beta", 500), ProvedorFalso("gama", 700, 22_050)]


def preencher_avaliacao(saida, notas_por_candidato):
    gabarito = json.loads((saida / ARQUIVO_GABARITO).read_text())
    arquivo = saida / ARQUIVO_AVALIACAO
    avaliacao = yaml.safe_load(arquivo.read_text())
    for amostra, candidato in gabarito.items():
        avaliacao["amostras"][amostra].update(notas_por_candidato[candidato])
    arquivo.write_text(yaml.safe_dump(avaliacao, allow_unicode=True))


def test_gerar_cria_uma_amostra_anonima_por_candidato(tmp_path, falas, provedores):
    gerar(falas, provedores, tmp_path, bitrate_kbps=64, sorteio=random.Random(42))

    gabarito = json.loads((tmp_path / ARQUIVO_GABARITO).read_text())
    assert sorted(gabarito.values()) == ["alfa", "beta", "gama"]
    assert sorted(p.name for p in (tmp_path / "amostras").iterdir()) == ["A.mp3", "B.mp3", "C.mp3"]


def test_ficha_de_avaliacao_nao_revela_os_candidatos(tmp_path, falas, provedores):
    gerar(falas, provedores, tmp_path, bitrate_kbps=64)

    ficha = (tmp_path / ARQUIVO_AVALIACAO).read_text()
    assert not any(nome in ficha for nome in ("alfa", "beta", "gama"))
    assert set(yaml.safe_load(ficha)["amostras"]["A"]) == {*CRITERIOS, "observacoes"}


def test_gerar_nao_sobrescreve_teste_existente(tmp_path, falas, provedores):
    gerar(falas, provedores, tmp_path, bitrate_kbps=64)

    with pytest.raises(FileExistsError):
        gerar(falas, provedores, tmp_path, bitrate_kbps=64)


def test_falha_de_um_candidato_nao_gera_nenhuma_amostra(tmp_path, falas):
    with pytest.raises(RuntimeError, match="quebrado"):
        gerar(falas, [ProvedorFalso("alfa"), ProvedorQuebrado()], tmp_path, bitrate_kbps=64)

    assert not any(tmp_path.iterdir())


def test_gerar_recusa_candidatos_repetidos(tmp_path, falas):
    with pytest.raises(ValueError, match="repetidos"):
        gerar(falas, [ProvedorFalso("alfa"), ProvedorFalso("alfa")], tmp_path, bitrate_kbps=64)


def test_revelar_aponta_todas_as_notas_faltantes(tmp_path, falas, provedores):
    gerar(falas, provedores, tmp_path, bitrate_kbps=64)

    with pytest.raises(ValueError) as erro:
        revelar(tmp_path)

    assert str(erro.value).count("fora da escala") == len(provedores) * len(CRITERIOS)


def test_revelar_recusa_nota_fora_da_escala(tmp_path, falas, provedores):
    gerar(falas, provedores, tmp_path, bitrate_kbps=64)
    notas_validas = {c: 3 for c in CRITERIOS}
    preencher_avaliacao(tmp_path, {
        "alfa": notas_validas, "beta": notas_validas, "gama": notas_validas | {"naturalidade": 6},
    })

    with pytest.raises(ValueError, match="naturalidade"):
        revelar(tmp_path)


def test_revelar_ordena_por_media_e_aponta_empates(tmp_path, falas, provedores):
    gerar(falas, provedores, tmp_path, bitrate_kbps=64)
    preencher_avaliacao(tmp_path, {
        "alfa": {"naturalidade": 2, "pronuncia_tecnica": 2, "diferenciacao": 2},
        "beta": {"naturalidade": 5, "pronuncia_tecnica": 3, "diferenciacao": 5},
        "gama": {"naturalidade": 4, "pronuncia_tecnica": 3, "diferenciacao": 5},
    })

    resultados = revelar(tmp_path)
    relatorio = formatar_relatorio(resultados)

    assert [r.candidato for r in resultados] == ["beta", "gama", "alfa"]
    assert "Melhor em naturalidade: beta" in relatorio
    assert "Melhor em diferenciacao: beta e gama" in relatorio


def test_trecho_com_persona_inexistente_falha_com_mensagem_clara(tmp_path, davi):
    trecho = tmp_path / "trecho.yaml"
    trecho.write_text("falas:\n  - persona: fantasma\n    texto: Boo\n")

    with pytest.raises(KeyError, match="fantasma"):
        carregar_trecho(trecho, {"davi": davi})


def test_cli_revelar_sem_teste_gerado_retorna_erro(tmp_path, capsys):
    codigo = main(["--saida", str(tmp_path), "revelar"])

    assert codigo == 1
    assert "Erro" in capsys.readouterr().err
