import base64
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from podcast.audio import Audio
from podcast.dominio import Fala
from podcast.personas import carregar_personas
from podcast.tts.gemini import VOZES, GeminiTts, agrupar_em_blocos, montar_requisicao
from podcast.tts.provedor import CotaDiariaEsgotada, RequisicaoRecusada


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


def test_estilo_da_fala_se_soma_ao_estilo_da_persona(davi):
    requisicao = montar_requisicao([Fala(davi, "Hum", estilo="pensativo")], "modelo", "pt-BR")

    assert requisicao["input"][0]["annotations"][0]["style"] == "estilo de Davi Nesta fala: pensativo."


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


class ClienteComBordas(ClienteFalso):
    """Cada bloco vem com 400 ms de silêncio antes e depois de 1 s de fala."""

    def __init__(self) -> None:
        super().__init__()
        borda = np.zeros(24_000 * 400 // 1000)
        fala = 0.3 * np.sin(2 * np.pi * 440 * np.arange(24_000) / 24_000)
        pcm = Audio.de_float(np.concatenate([borda, fala, borda]), 24_000).pcm
        self._resposta = SimpleNamespace(output_audio=SimpleNamespace(data=base64.b64encode(pcm).decode()))


def test_sintetizar_apara_as_bordas_e_deixa_so_a_pausa_fixa_entre_blocos(davi, helena, bruno):
    tts = GeminiTts("modelo", pausa_entre_blocos_ms=300, cliente=ClienteComBordas())

    audio = tts.sintetizar([Fala(davi, "a"), Fala(helena, "b"), Fala(bruno, "c")])

    folga = 0.03
    assert audio.duracao_segundos == pytest.approx(2 * (1 + 2 * folga) + 0.3, abs=0.002)
    assert audio.trocas_s == pytest.approx((1 + 2 * folga + 0.15,), abs=0.002)


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
    def __init__(self, status_code: int, body: object = None) -> None:
        super().__init__(f"Error code: {status_code}")
        self.status_code = status_code
        self.body = body


def _corpo_do_429(quota_id: str) -> dict:
    return {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_requests", "quotaId": quota_id}]},
    ]}}


class ClienteQueFalhaCom(ClienteFalso):
    def __init__(self, status_code: int, body: object = None) -> None:
        super().__init__()
        self.status_code = status_code
        self.body = body

    def create(self, **requisicao):
        raise ErroDaApi(self.status_code, self.body)


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


def test_cota_diaria_esgotada_desiste_na_primeira_tentativa_sem_esperar(davi):
    esperas = []
    cliente = ClienteQueFalhaCom(429, _corpo_do_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    tts = GeminiTts("gemini-3.8-flash-tts", cliente=cliente, dormir=esperas.append)

    with pytest.raises(CotaDiariaEsgotada, match="Cota diária do Gemini esgotada"):
        tts.sintetizar([Fala(davi, "Oi")])
    assert esperas == []


def test_cota_por_minuto_esgotada_continua_tentando_de_novo(davi):
    esperas = []
    cliente = ClienteQueFalhaCom(429, _corpo_do_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
    tts = GeminiTts("modelo", cliente=cliente, tentativas=3, espera_inicial_s=10, dormir=esperas.append)

    with pytest.raises(ErroDaApi):
        tts.sintetizar([Fala(davi, "Oi")])
    assert esperas == [10, 20]


class ClienteQueEstouraOTempo(ClienteFalso):
    def __init__(self) -> None:
        super().__init__()
        self._estourou = False

    def create(self, **requisicao):
        if not self._estourou:
            self._estourou = True
            raise TimeoutError("Request timed out.")
        return super().create(**requisicao)


def test_timeout_aparece_no_log_e_entra_na_retentativa(davi, caplog):
    esperas = []
    tts = GeminiTts("modelo", cliente=ClienteQueEstouraOTempo(), espera_inicial_s=10, dormir=esperas.append)

    with caplog.at_level(logging.WARNING, logger="podcast.tts.gemini"):
        tts.sintetizar([Fala(davi, "Oi")])

    assert esperas == [10]
    assert "tentativa 1 de 4" in caplog.text and "timed out" in caplog.text


def test_ultima_tentativa_tambem_fica_no_log(davi, caplog):
    tts = GeminiTts("modelo", cliente=ClienteInstavel(falhas=9), tentativas=2, dormir=lambda _: None)

    with caplog.at_level(logging.WARNING, logger="podcast.tts.gemini"), pytest.raises(RuntimeError):
        tts.sintetizar([Fala(davi, "Oi")])

    assert "tentativa 2 de 2" in caplog.text and "Sem nova tentativa" in caplog.text


def test_cliente_desliga_a_retentativa_do_sdk_e_limita_o_tempo_da_requisicao(monkeypatch):
    from google import genai

    from podcast.tts import gemini

    criados = []
    monkeypatch.setattr(genai, "Client", lambda **opcoes: criados.append(opcoes))

    gemini._criar_cliente(timeout_s=180)

    [opcoes] = criados
    http = opcoes["http_options"]
    assert http.api_version == "v1beta"
    assert http.timeout == 180_000
    assert http.retry_options.attempts == 1
