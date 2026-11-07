from collections.abc import Sequence

import numpy as np
import pytest

from podcast.audio import Audio
from podcast.dominio import Fala, Persona, Voz


class ProvedorFalso:
    def __init__(self, nome: str, frequencia_hz: float = 440.0, taxa_amostragem: int = 24_000) -> None:
        self.nome = nome
        self._frequencia = frequencia_hz
        self._taxa = taxa_amostragem

    def sintetizar(self, falas: Sequence[Fala]) -> Audio:
        tempo = np.arange(self._taxa) / self._taxa
        return Audio.de_float(0.3 * np.sin(2 * np.pi * self._frequencia * tempo), self._taxa)


class ProvedorQuebrado:
    nome = "quebrado"

    def sintetizar(self, falas: Sequence[Fala]) -> Audio:
        raise ConnectionError("API fora do ar")


def criar_persona(id_: str, nome: str) -> Persona:
    return Persona(id=id_, nome=nome, voz=Voz(gemini=f"voz-{id_}", kokoro="pf_dora", piper="pt_BR-faber-medium", estilo=f"estilo de {nome}"))


@pytest.fixture
def davi() -> Persona:
    return criar_persona("davi", "Davi")


@pytest.fixture
def helena() -> Persona:
    return criar_persona("helena", "Helena")


@pytest.fixture
def bruno() -> Persona:
    return criar_persona("bruno", "Bruno")
