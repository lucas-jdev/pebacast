from pathlib import Path

import yaml

from podcast.dominio import Fala
from podcast.pronuncia import Pronuncia, aplicar_pronuncias, carregar_pronuncias
from podcast.tts.gemini import _montar_turno

RAIZ = Path(__file__).resolve().parents[1]
PEBACAST = Pronuncia("Pebacast", escrever_como="Pébacast", instrucao="E aberto, como em tatu-peba.")


def _estilo_enviado_ao_gemini(fala):
    [metadados] = _montar_turno(fala)["annotations"]
    assert metadados["type"] == "speech_metadata"
    return metadados["style"]


# Composição do estilo (#35): persona, depois "Nesta fala: <estilo>.", depois as instruções de pronúncia.


def test_fala_com_estilo_envia_a_persona_seguida_do_estilo_da_fala(davi):
    fala = Fala(davi, "Essa foi boa.", estilo="rindo")

    assert _estilo_enviado_ao_gemini(fala) == "estilo de Davi Nesta fala: rindo."


def test_fala_sem_estilo_e_sem_termo_envia_so_a_instrucao_da_persona(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Toda decisão é um trade-off.")], [PEBACAST])

    assert _estilo_enviado_ao_gemini(fala) == davi.voz.estilo == "estilo de Davi"


def test_fala_com_estilo_e_termo_envia_cada_instrucao_uma_unica_vez(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Até o próximo pebacast.", estilo="sorrindo")], [PEBACAST])

    estilo = _estilo_enviado_ao_gemini(fala)
    assert fala.texto == "Até o próximo Pébacast."
    assert estilo == "estilo de Davi Nesta fala: sorrindo. E aberto, como em tatu-peba."
    for parte in ("estilo de Davi", "Nesta fala: sorrindo.", "E aberto, como em tatu-peba."):
        assert estilo.count(parte) == 1


def test_aplicar_pronuncias_nao_mexe_no_estilo_do_roteiro(davi):
    original = Fala(davi, "Até o próximo pebacast.", estilo="sorrindo")

    [fala] = aplicar_pronuncias([original], [PEBACAST])
    [de_novo] = aplicar_pronuncias([fala], [])

    assert fala.estilo == "sorrindo"
    assert de_novo.estilo_efetivo.count("estilo de Davi") == 1


def test_troca_a_grafia_e_soma_a_instrucao_ao_estilo_da_persona(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Bem-vindos ao Pebacast!")], [PEBACAST])

    assert fala.texto == "Bem-vindos ao Pébacast!"
    assert fala.estilo is None
    assert fala.instrucoes_de_pronuncia == ("E aberto, como em tatu-peba.",)
    assert fala.estilo_efetivo == "estilo de Davi E aberto, como em tatu-peba."


def test_estilo_da_fala_com_ponto_final_nao_ganha_ponto_duplo(davi):
    assert Fala(davi, "Hum.", estilo="surpreso, mais devagar.").estilo_efetivo == (
        "estilo de Davi Nesta fala: surpreso, mais devagar.")


def test_fala_sem_o_termo_fica_intacta(davi):
    fala = Fala(davi, "Toda decisão é um trade-off.")
    assert aplicar_pronuncias([fala], [PEBACAST]) == [fala]


def test_so_casa_a_palavra_inteira(davi):
    fala = Fala(davi, "Os Pebacasters gostam disso.")
    assert aplicar_pronuncias([fala], [PEBACAST]) == [fala]


def test_so_instrucao_mantem_o_texto(davi):
    [fala] = aplicar_pronuncias([Fala(davi, "Pebacast")], [Pronuncia("Pebacast", instrucao="E aberto.")])
    assert fala.texto == "Pebacast" and fala.estilo is None
    assert fala.estilo_efetivo == "estilo de Davi E aberto."


def test_config_real_tem_a_pronuncia_do_pebacast():
    config = yaml.safe_load((RAIZ / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    termos = {pronuncia.termo: pronuncia for pronuncia in carregar_pronuncias(config["tts"])}
    assert "tatu-peba" in termos["Pebacast"].instrucao
