"""Dicionário de pronúncia aplicado só ao texto que vai para o TTS.

O roteiro, as show notes e o feed continuam com a grafia original. Cada termo pode ter uma
grafia alternativa (útil para qualquer provedor) e uma instrução em linguagem natural, que entra
em `Fala.instrucoes_de_pronuncia` e é somada à instrução de voz pelo `Fala.estilo_efetivo` (só o
Gemini interpreta). `fala.estilo` continua sendo o que o roteiro escreveu.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from podcast.dominio import Fala


@dataclass(frozen=True)
class Pronuncia:
    termo: str
    escrever_como: str | None = None
    instrucao: str | None = None

    @property
    def padrao(self) -> re.Pattern[str]:
        return re.compile(rf"\b{re.escape(self.termo)}\b", re.IGNORECASE)


def carregar_pronuncias(config_tts: Mapping[str, Any]) -> list[Pronuncia]:
    return [Pronuncia(**item) for item in config_tts.get("pronuncia") or []]


def aplicar_pronuncias(falas: Sequence[Fala], pronuncias: Sequence[Pronuncia]) -> list[Fala]:
    return [_aplicar(fala, pronuncias) for fala in falas]


def _aplicar(fala: Fala, pronuncias: Sequence[Pronuncia]) -> Fala:
    texto, instrucoes = fala.texto, []
    for pronuncia in pronuncias:
        if not pronuncia.padrao.search(texto):
            continue
        if pronuncia.escrever_como:
            texto = pronuncia.padrao.sub(lambda _: pronuncia.escrever_como, texto)
        if pronuncia.instrucao:
            instrucoes.append(pronuncia.instrucao)

    if texto == fala.texto and not instrucoes:
        return fala
    return replace(fala, texto=texto, instrucoes_de_pronuncia=(*fala.instrucoes_de_pronuncia, *instrucoes))
