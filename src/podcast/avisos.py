"""Avisos da publicação: o que saiu diferente do normal sem segurar o episódio.

Cada aviso diz se é de fallback de voz. O fallback vai para o `avisos.md`, que o `publicar.yml`
transforma na issue "Episódio publicado com fallback de voz". Os outros (vinheta, QA do áudio que
não rodou, issue da cota que não abriu ou fechou) abrem a issue `incidente` "Avisos na publicação
do <id>", uma por episódio, que só ganha comentário se já estiver aberta. Quem fecha é o Lucas.
"""

import logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from podcast.issues import IssuesDeIncidente

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Aviso:
    episodio_id: str
    texto: str
    fallback: bool = False

    def __str__(self) -> str:
        return f"{self.episodio_id}: {self.texto}"


class RegistroDeAvisos(Protocol):
    def registrar(self, episodio_id: str, textos: Sequence[str]) -> None:
        """Abre a issue de avisos do episódio, ou comenta na que já está aberta."""
        ...


@dataclass(frozen=True)
class IncidentesDeAvisos:
    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def registrar(self, episodio_id: str, textos: Sequence[str]) -> None:
        lista = "\n".join(f"- {texto}" for texto in textos)
        IssuesDeIncidente(self.repositorio, self.execucao, self.executar).abrir_ou_comentar(
            self.titulo(episodio_id),
            f"A publicação do {episodio_id} deixou avisos. Nenhum deles segurou o episódio:\n\n{lista}\n\n"
            "Esta issue não fecha sozinha: feche depois de conferir.",
            f"Novos avisos na publicação do {episodio_id}:\n\n{lista}",
        )

    @staticmethod
    def titulo(episodio_id: str) -> str:
        # Sem terminar em ": <id>": esse é o padrão das issues de roteiro, que o workflow fecha sozinho.
        return f"Avisos na publicação do {episodio_id}"


def encaminhar_avisos(avisos: Sequence[Aviso], arquivo_fallback: Path, registro: RegistroDeAvisos) -> None:
    """Fallback no `avisos.md`; o resto na issue de avisos do episódio. Uma falha do `gh` não derruba a publicação."""
    fallbacks = [aviso for aviso in avisos if aviso.fallback]
    if fallbacks:
        arquivo_fallback.write_text("\n".join(f"- {aviso}" for aviso in fallbacks) + "\n", encoding="utf-8")

    por_episodio: dict[str, list[str]] = {}
    for aviso in avisos:
        if not aviso.fallback:
            por_episodio.setdefault(aviso.episodio_id, []).append(aviso.texto)
    for episodio_id, textos in por_episodio.items():
        try:
            registro.registrar(episodio_id, textos)
        except Exception as erro:
            log.exception("A issue de avisos de %s não foi aberta.", episodio_id)
            print(f"::warning::{episodio_id}: a issue de avisos não foi aberta. {type(erro).__name__}: {erro}")
