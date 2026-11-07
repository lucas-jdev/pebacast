from pathlib import Path

import yaml

from podcast.dominio import Fala
from podcast.pronuncia import Pronuncia, aplicar_pronuncias, carregar_pronuncias

RAIZ = Path(__file__).resolve().parents[1]
PEBACAST = Pronuncia("Pebacast", escrever_como="Pébacast", instrucao="E aberto, como em tatu-peba.")


def test_troca_a_grafia_e_soma_a_instrucao_ao_estilo_da_persona(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Bem-vindos ao Pebacast!")], [PEBACAST])

    assert fala.texto == "Bem-vindos ao Pébacast!"
    assert fala.estilo_efetivo == "estilo de Davi E aberto, como em tatu-peba."


def test_soma_a_instrucao_ao_estilo_proprio_da_fala(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Até o próximo pebacast.", estilo="sorrindo")], [PEBACAST])

    assert fala.texto == "Até o próximo Pébacast."
    assert fala.estilo == "sorrindo E aberto, como em tatu-peba."


def test_fala_sem_o_termo_fica_intacta(davi):
    fala = Fala(davi, "Toda decisão é um trade-off.")
    assert aplicar_pronuncias([fala], [PEBACAST]) == [fala]


def test_so_casa_a_palavra_inteira(davi):
    fala = Fala(davi, "Os Pebacasters gostam disso.")
    assert aplicar_pronuncias([fala], [PEBACAST]) == [fala]


def test_so_instrucao_mantem_o_texto(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Pebacast")], [Pronuncia("Pebacast", instrucao="E aberto.")])
    assert fala.texto == "Pebacast" and fala.estilo == "estilo de Davi E aberto."


def test_config_real_tem_a_pronuncia_do_pebacast():
    config = yaml.safe_load((RAIZ / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    termos = {pronuncia.termo: pronuncia for pronuncia in carregar_pronuncias(config["tts"])}
    assert "tatu-peba" in termos["Pebacast"].instrucao
