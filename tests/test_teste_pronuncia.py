import json
import random
from pathlib import Path

import pytest

from podcast.dominio import Fala
from podcast.pronuncia import Pronuncia
from podcast.teste_pronuncia import ARQUIVO_GABARITO, Experimento, carregar_experimento, gerar, main, revelar
from tests.conftest import ProvedorFalso

ARQUIVO_DO_EXPERIMENTO = Path("experimentos/teste-pronuncia/pebacast.yaml")


class ProvedorQueAnota(ProvedorFalso):
    def __init__(self) -> None:
        super().__init__("anotador")
        self.pedidos: list[list[Fala]] = []

    def sintetizar(self, falas):
        self.pedidos.append(list(falas))
        return super().sintetizar(falas)


@pytest.fixture
def teste(davi):
    return Experimento(
        falas=[Fala(davi, "Bem-vindos ao Pebacast."), Fala(davi, "Este foi o Pebacast.")],
        variantes={
            "instrucao": Pronuncia("Pebacast", instrucao="E aberto."),
            "grafia": Pronuncia("Pebacast", escrever_como="Péba-cast"),
        },
    )


def test_cada_variante_e_uma_requisicao_com_todas_as_frases(tmp_path, teste):
    provedor = ProvedorQueAnota()

    gerar(teste, provedor, tmp_path, bitrate_kbps=64, sorteio=random.Random(1))

    assert len(provedor.pedidos) == 2
    textos = sorted(tuple(fala.texto for fala in pedido) for pedido in provedor.pedidos)
    assert textos == [("Bem-vindos ao Pebacast.", "Este foi o Pebacast."), ("Bem-vindos ao Péba-cast.", "Este foi o Péba-cast.")]
    instrucoes = [fala.instrucoes_de_pronuncia for pedido in provedor.pedidos for fala in pedido]
    assert instrucoes.count(("E aberto.",)) == 2


def test_amostras_saem_anonimas_e_o_gabarito_fica_a_parte(tmp_path, teste):
    gerar(teste, ProvedorFalso("x"), tmp_path, bitrate_kbps=64, sorteio=random.Random(1))

    gabarito = json.loads((tmp_path / ARQUIVO_GABARITO).read_text())
    assert gabarito["frases"] == 2
    assert sorted(gabarito["amostras"].values()) == ["grafia", "instrucao"]
    assert sorted(p.name for p in (tmp_path / "amostras").iterdir()) == ["A.mp3", "B.mp3"]


def test_gerar_nao_sobrescreve_teste_existente(tmp_path, teste):
    gerar(teste, ProvedorFalso("x"), tmp_path, bitrate_kbps=64)

    with pytest.raises(FileExistsError):
        gerar(teste, ProvedorFalso("x"), tmp_path, bitrate_kbps=64)


def test_revelar_ordena_pelos_acertos(tmp_path, teste):
    gerar(teste, ProvedorFalso("x"), tmp_path, bitrate_kbps=64, sorteio=random.Random(1))
    gabarito = json.loads((tmp_path / ARQUIVO_GABARITO).read_text())["amostras"]
    amostra_da_grafia = next(amostra for amostra, nome in gabarito.items() if nome == "grafia")
    outra = next(amostra for amostra in gabarito if amostra != amostra_da_grafia)

    relatorio = revelar(tmp_path, {amostra_da_grafia: 2, outra: 0})

    assert relatorio.splitlines()[0] == f"{amostra_da_grafia} = grafia: 2 de 2"


@pytest.mark.parametrize("acertos", [{"A": 1}, {"A": 1, "B": 3}, {"A": 1, "B": 1, "C": 0}])
def test_revelar_recusa_acertos_incompletos_ou_fora_da_escala(tmp_path, teste, acertos):
    gerar(teste, ProvedorFalso("x"), tmp_path, bitrate_kbps=64)

    with pytest.raises(ValueError):
        revelar(tmp_path, acertos)


def test_cli_revelar_le_pares_amostra_acertos(tmp_path, teste, capsys):
    gerar(teste, ProvedorFalso("x"), tmp_path, bitrate_kbps=64)

    assert main(["--saida", str(tmp_path), "revelar", "a=1", "B=2"]) == 0
    assert "de 2" in capsys.readouterr().out


def test_experimento_do_pebacast_carrega_com_as_personas_reais():
    from podcast.personas import carregar_personas

    experimento = carregar_experimento(ARQUIVO_DO_EXPERIMENTO, carregar_personas(Path("curriculum/personas")))

    assert len(experimento.variantes) == 3
    assert all("Pebacast" in fala.texto for fala in experimento.falas)
    assert sum(len(fala.texto) for fala in experimento.falas) < 4_000
