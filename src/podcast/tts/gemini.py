import base64
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

from podcast.audio import Audio, concatenar
from podcast.dominio import Fala, Persona
from podcast.tts.provedor import RequisicaoRecusada

TAXA_AMOSTRAGEM = 24_000
MAX_FALANTES_POR_REQUISICAO = 2

VOZES = frozenset({
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe", "Callirrhoe",
    "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux", "Iapetus", "Kore",
    "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima", "Rasalgethi", "Sadachbia",
    "Sadaltager", "Schedar", "Sulafat", "Umbriel", "Vindemiatrix", "Zephyr", "Zubenelgenubi",
})
STATUS_TRANSITORIOS = frozenset({408, 429})
STATUS_DE_ACESSO = frozenset({401, 403})

log = logging.getLogger(__name__)


class GeminiTts:
    def __init__(
        self,
        modelo: str,
        idioma: str = "pt-BR",
        max_caracteres_por_bloco: int = 4_000,
        pausa_entre_blocos_ms: int = 300,
        cliente: Any = None,
        tentativas: int = 4,
        espera_inicial_s: float = 15.0,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.nome = modelo
        self._modelo = modelo
        self._idioma = idioma
        self._max_caracteres = max_caracteres_por_bloco
        self._pausa_ms = pausa_entre_blocos_ms
        self._cliente = cliente if cliente is not None else _criar_cliente()
        self._tentativas = tentativas
        self._espera_inicial_s = espera_inicial_s
        self._dormir = dormir

    def sintetizar(self, falas: Sequence[Fala]) -> Audio:
        blocos = agrupar_em_blocos(falas, self._max_caracteres)
        return concatenar([self._sintetizar_bloco(bloco) for bloco in blocos], self._pausa_ms)

    def _sintetizar_bloco(self, bloco: Sequence[Fala]) -> Audio:
        requisicao = montar_requisicao(bloco, self._modelo, self._idioma)
        for tentativa in range(1, self._tentativas + 1):
            try:
                interacao = self._cliente.interactions.create(**requisicao)
                return Audio(base64.b64decode(interacao.output_audio.data), TAXA_AMOSTRAGEM)
            except Exception as erro:
                if _recusa_do_pedido(erro):
                    raise RequisicaoRecusada(str(erro)) from erro
                # O free tier devolve 429 com frequência; espera exponencial antes de desistir.
                if tentativa == self._tentativas or _falha_de_acesso(erro):
                    raise
                espera = self._espera_inicial_s * 2 ** (tentativa - 1)
                log.warning("Gemini falhou (tentativa %d de %d): %s. Nova tentativa em %.0f s.",
                            tentativa, self._tentativas, erro, espera)
                self._dormir(espera)
        raise AssertionError("inalcançável")


def _recusa_do_pedido(erro: Exception) -> bool:
    status = getattr(erro, "status_code", None)
    return (
        status is not None
        and 400 <= status < 500
        and status not in STATUS_TRANSITORIOS | STATUS_DE_ACESSO
    )


def _falha_de_acesso(erro: Exception) -> bool:
    return getattr(erro, "status_code", None) in STATUS_DE_ACESSO


def agrupar_em_blocos(falas: Sequence[Fala], max_caracteres: int) -> list[list[Fala]]:
    blocos: list[list[Fala]] = []
    atual: list[Fala] = []
    for fala in falas:
        if atual and _nao_cabe(atual, fala, max_caracteres):
            blocos.append(atual)
            atual = []
        atual.append(fala)
    if atual:
        blocos.append(atual)
    return blocos


def montar_requisicao(bloco: Sequence[Fala], modelo: str, idioma: str) -> dict[str, Any]:
    personas = _personas_em_ordem(bloco)
    if len(personas) == 1:
        # Com "speaker", a API trata o pedido como multi-falante e exige dois.
        speech_config: Any = [{"voice": personas[0].voz.gemini, "language": idioma}]
    else:
        speech_config = {"speakers": [_configurar_falante(persona, idioma) for persona in personas]}
    return {
        "model": modelo,
        "input": [_montar_turno(fala) for fala in bloco],
        "response_format": {"type": "audio", "mime_type": "audio/l16", "sample_rate": TAXA_AMOSTRAGEM},
        "generation_config": {"speech_config": speech_config},
        "store": False,
    }


def _nao_cabe(bloco: Sequence[Fala], fala: Fala, max_caracteres: int) -> bool:
    falantes = {item.persona.id for item in bloco} | {fala.persona.id}
    caracteres = sum(len(item.texto) for item in bloco) + len(fala.texto)
    return len(falantes) > MAX_FALANTES_POR_REQUISICAO or caracteres > max_caracteres


def _personas_em_ordem(bloco: Sequence[Fala]) -> list[Persona]:
    return list(dict.fromkeys(fala.persona for fala in bloco))


def _configurar_falante(persona: Persona, idioma: str) -> dict[str, str]:
    return {"speaker": persona.nome, "voice": persona.voz.gemini, "language": idioma}


def _montar_turno(fala: Fala) -> dict[str, Any]:
    metadados = {"type": "speech_metadata", "speaker": fala.persona.nome, "style": fala.estilo_efetivo}
    return {"type": "text", "text": fala.texto, "annotations": [metadados]}


def _criar_cliente() -> Any:
    from google import genai

    # Os modelos de TTS só existem na v1beta; o padrão do SDK 3.x é a v1.
    return genai.Client(http_options={"api_version": "v1beta"})
