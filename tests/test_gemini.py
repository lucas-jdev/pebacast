import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from podcast.dominio import Fala
from podcast.personas import carregar_personas
from podcast.tts.gemini import VOZES, GeminiTts, agrupar_em_blocos, montar_requisicao
from podcast.tts.provedor import RequisicaoRecusada


class ClienteFalso:
    def __init__(self, duracao_ms: int = 100) -> None:
        self.requisicoes: list[dict] = []
        pcm = bytes(24_000 * duracao_ms // 1000 * 2)
        self._resposta = SimpleNamespace(output_audio=SimpleNamespace(data=base64.b64encode(pcm).decode()))
        self.interactions = self

    def create(self, **requisicao):
        self.requisicoes.append(requisicao)
        return self._resposta


def test_bloco_nunca_tem_mais_de_dois_falantes(davi, helena, bruno):
    falas = [Fala(davi, "a"), Fala(helena, "b"), Fala(bruno, "c"), Fala(davi, "d")]

    blocos = agrupar_em_blocos(falas, max_caracteres=1_000)

    assert all(len({fala.persona.id for fala in bloco}) <= 2 for bloco in blocos)
    assert [fala for bloco in blocos for fala in bloco] == falas


def test_bloco_respeita_limite_de_caracteres(davi, helena):
    falas = [Fala(davi, "x" * 60), Fala(helena, "y" * 60), Fala(davi, "z" * 60)]

    blocos = agrupar_em_blocos(falas, max_caracteres=100)

    assert [len(bloco) for bloco in blocos] == [1, 1, 1]


def test_fala_maior_que_o_limite_vai_sozinha_num_bloco(davi):
    blocos = agrupar_em_blocos([Fala(davi, "x" * 500)], max_caracteres=100)

    assert len(blocos) == 1


def test_requisicao_com_um_falante_usa_lista_de_vozes(davi):
    requisicao = montar_requisicao([Fala(davi, "Oi")], "gemini-3.8-flash-tts", "pt-BR")

    assert requisicao["generation_config"]["speech_config"] == [
        {"voice": "voz-davi", "language": "pt-BR"}
    ]


def test_requisicao_com_dois_falantes_usa_configuracao_multi_falante(davi, helena):
    requisicao = montar_requisicao([Fala(davi, "Oi"), Fala(helena, "Olá")], "gemini-3.8-flash-tts", "pt-BR")

    falantes = requisicao["generation_config"]["speech_config"]["speakers"]
    assert [falante["speaker"] for falante in falantes] == ["Davi", "Helena"]


def test_estilo_da_fala_sobrescreve_o_estilo_da_persona(davi):
    requisicao = montar_requisicao([Fala(davi, "Hum", estilo="pensativo")], "modelo", "pt-BR")

    assert requisicao["input"][0]["annotations"][0]["style"] == "pensativo"


def test_requisicao_pede_pcm_bruto_e_nao_armazena_interacao(davi):
    requisicao = montar_requisicao([Fala(davi, "Oi")], "modelo", "pt-BR")

    assert requisicao["response_format"]["mime_type"] == "audio/l16"
    assert requisicao["store"] is False


def test_sintetizar_faz_uma_requisicao_por_bloco_e_concatena(davi, helena, bruno):
    cliente = ClienteFalso(duracao_ms=100)
    tts = GeminiTts("modelo", pausa_entre_blocos_ms=300, cliente=cliente)

    audio = tts.sintetizar([Fala(davi, "a"), Fala(helena, "b"), Fala(bruno, "c")])

    assert len(cliente.requisicoes) == 2
    assert audio.duracao_segundos == pytest.approx(0.5)


class ClienteInstavel(ClienteFalso):
    def __init__(self, falhas: int) -> None:
        super().__init__()
        self._falhas = falhas

    def create(self, **requisicao):
        if self._falhas:
            self._falhas -= 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return super().create(**requisicao)


def test_tenta_de_novo_com_espera_exponencial_quando_a_api_falha(davi):
    esperas = []
    tts = GeminiTts("modelo", cliente=ClienteInstavel(falhas=2), espera_inicial_s=10, dormir=esperas.append)

    tts.sintetizar([Fala(davi, "Oi")])

    assert esperas == [10, 20]


def test_desiste_depois_do_limite_de_tentativas(davi):
    esperas = []
    tts = GeminiTts("modelo", cliente=ClienteInstavel(falhas=9), tentativas=3, dormir=esperas.append)

    with pytest.raises(RuntimeError, match="429"):
        tts.sintetizar([Fala(davi, "Oi")])
    assert len(esperas) == 2


class ErroDaApi(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Error code: {status_code}")
        self.status_code = status_code


class ClienteQueFalhaCom(ClienteFalso):
    def __init__(self, status_code: int) -> None:
        super().__init__()
        self.status_code = status_code

    def create(self, **requisicao):
        raise ErroDaApi(self.status_code)


def test_pedido_recusado_nao_tenta_de_novo(davi):
    esperas = []
    tts = GeminiTts("modelo", cliente=ClienteQueFalhaCom(400), dormir=esperas.append)

    with pytest.raises(RequisicaoRecusada, match="400"):
        tts.sintetizar([Fala(davi, "Oi")])
    assert esperas == []


def test_falha_de_acesso_sobe_sem_tentar_de_novo_para_o_fallback_cobrir(davi):
    esperas = []
    tts = GeminiTts("modelo", cliente=ClienteQueFalhaCom(403), dormir=esperas.append)

    with pytest.raises(ErroDaApi):
        tts.sintetizar([Fala(davi, "Oi")])
    assert esperas == []


@pytest.mark.parametrize("status_code", [429, 503])
def test_erro_transitorio_tenta_de_novo(davi, status_code):
    esperas = []
    tts = GeminiTts("modelo", cliente=ClienteQueFalhaCom(status_code), tentativas=3, dormir=esperas.append)

    with pytest.raises(ErroDaApi):
        tts.sintetizar([Fala(davi, "Oi")])
    assert len(esperas) == 2


def test_toda_persona_do_curriculo_tem_voz_do_gemini_valida():
    personas = carregar_personas(Path(__file__).parent.parent / "curriculum" / "personas")

    invalidas = {p.id: p.voz.gemini for p in personas.values() if p.voz.gemini not in VOZES}
    assert invalidas == {}
