import base64
import json
import math
import time
from collections.abc import Callable, Sequence
from typing import Any

from podcast.audio import Audio, concatenar
from podcast.dominio import Fala, Persona
from podcast.retentativa import tentar
from podcast.tts.provedor import CotaDiariaEsgotada, RequisicaoRecusada

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
TIMEOUT_PADRAO_S = 180.0



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
        timeout_s: float = TIMEOUT_PADRAO_S,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.nome = modelo
        self._modelo = modelo
        self._idioma = idioma
        self._max_caracteres = max_caracteres_por_bloco
        self._pausa_ms = pausa_entre_blocos_ms
        self._cliente = cliente if cliente is not None else criar_cliente(timeout_s)
        self._tentativas = tentativas
        self._espera_inicial_s = espera_inicial_s
        self._dormir = dormir

    def sintetizar(self, falas: Sequence[Fala]) -> Audio:
        blocos = agrupar_em_blocos(falas, self._max_caracteres)
        return concatenar([self._sintetizar_bloco(bloco) for bloco in blocos], self._pausa_ms, aparar=True)

    def _sintetizar_bloco(self, bloco: Sequence[Fala]) -> Audio:
        requisicao = montar_requisicao(bloco, self._modelo, self._idioma)

        def chamar() -> Audio:
            interacao = self._cliente.interactions.create(**requisicao)
            return Audio(base64.b64decode(interacao.output_audio.data), TAXA_AMOSTRAGEM)

        # O free tier devolve 429 por minuto com frequência; o resto não melhora esperando.
        return tentar(chamar, rotulo="Gemini", tentativas=self._tentativas,
                      espera_inicial_s=self._espera_inicial_s, dormir=self._dormir, desistir=self._desistir)

    def _desistir(self, erro: Exception) -> Exception | None:
        if _recusa_do_pedido(erro):
            return RequisicaoRecusada(str(erro))
        if _cota_diaria_esgotada(erro):
            return CotaDiariaEsgotada(f"Cota diária do Gemini esgotada ({self._modelo}): {erro}")
        if _falha_de_acesso(erro):
            return erro
        return None


def _recusa_do_pedido(erro: Exception) -> bool:
    status = getattr(erro, "status_code", None)
    return (
        status is not None
        and 400 <= status < 500
        and status not in STATUS_TRANSITORIOS | STATUS_DE_ACESSO
    )


def _falha_de_acesso(erro: Exception) -> bool:
    return getattr(erro, "status_code", None) in STATUS_DE_ACESSO


def _cota_diaria_esgotada(erro: Exception) -> bool:
    """O 429 da cota por dia cita um quotaId com "PerDay"; o da cota por minuto, não."""
    if getattr(erro, "status_code", None) != 429:
        return False
    corpo = getattr(erro, "body", None)
    return "PerDay" in f"{erro} {json.dumps(corpo, default=str) if corpo is not None else ''}"


def agrupar_em_blocos(falas: Sequence[Fala], max_caracteres: int) -> list[list[Fala]]:
    """Divide as falas no menor número de blocos que o limite permite, com tamanhos parecidos.

    Encher um bloco de cada vez deixava a despedida sozinha num bloco de poucas centenas de
    caracteres (co-002: 518), e o Gemini, sem contexto para firmar as vozes, mudava o timbre na
    última troca. Entre as divisões com o mínimo de blocos, fica a de menor soma dos quadrados
    dos tamanhos, que é a mais equilibrada.
    """
    if not falas:
        return []
    quantidade = len(_encher_em_ordem(falas, max_caracteres))
    custo = [[math.inf] * (len(falas) + 1) for _ in range(quantidade + 1)]
    corte = [[0] * (len(falas) + 1) for _ in range(quantidade + 1)]
    custo[0][0] = 0
    for bloco in range(1, quantidade + 1):
        for fim in range(1, len(falas) + 1):
            caracteres, falantes = 0, set()
            for inicio in range(fim - 1, -1, -1):
                caracteres += len(falas[inicio].texto)
                falantes.add(falas[inicio].persona.id)
                if inicio < fim - 1 and (caracteres > max_caracteres or len(falantes) > MAX_FALANTES_POR_REQUISICAO):
                    break
                candidato = custo[bloco - 1][inicio] + caracteres**2
                if candidato < custo[bloco][fim]:
                    custo[bloco][fim], corte[bloco][fim] = candidato, inicio

    blocos, fim = [], len(falas)
    for bloco in range(quantidade, 0, -1):
        inicio = corte[bloco][fim]
        blocos.append(list(falas[inicio:fim]))
        fim = inicio
    return blocos[::-1]


def _encher_em_ordem(falas: Sequence[Fala], max_caracteres: int) -> list[list[Fala]]:
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


def criar_cliente(timeout_s: float) -> Any:
    from google import genai
    from google.genai import types

    # Os modelos de TTS só existem na v1beta; o padrão do SDK 3.x é a v1. A retentativa do SDK fica
    # desligada (attempts=1): repetir é papel do _sintetizar_bloco, que registra cada tentativa no log.
    return genai.Client(http_options=types.HttpOptions(
        api_version="v1beta",
        timeout=round(timeout_s * 1000),
        retry_options=types.HttpRetryOptions(attempts=1),
    ))
