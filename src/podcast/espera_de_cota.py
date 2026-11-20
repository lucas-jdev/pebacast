"""Episódio que aguarda a cota diária do Gemini renovar (ADR 0011).

Com a cota do dia esgotada, o episódio não vai para o Kokoro: fica com `aguardando_cota.json`
na pasta, o site avisa que ele sai em breve, e o `publicar.yml` agendado tenta de novo depois
da renovação. Uma issue `incidente` por episódio acompanha a espera e fecha quando ele sai.
"""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from podcast.validacao import ESPERA_DE_COTA


def marcar_espera(pasta: Path, agora: datetime) -> None:
    """Grava o início da espera; numa nova falha, o início continua o da primeira."""
    arquivo = pasta / ESPERA_DE_COTA
    if arquivo.exists():
        return
    arquivo.write_text(json.dumps({"desde": agora.isoformat(timespec="seconds")}) + "\n", encoding="utf-8")


def encerrar_espera(pasta: Path) -> bool:
    """Apaga a marca de espera e diz se o episódio estava aguardando."""
    arquivo = pasta / ESPERA_DE_COTA
    if not arquivo.exists():
        return False
    arquivo.unlink()
    return True


class RegistroDeEspera(Protocol):
    def registrar(self, episodio_id: str, erro: str) -> None:
        """Abre a issue do episódio que passou a aguardar, ou comenta na que já está aberta."""
        ...

    def resolver(self, episodio_id: str) -> None:
        """Fecha a issue do episódio que foi publicado."""
        ...


@dataclass(frozen=True)
class IncidentesDeCota:
    """Uma issue `incidente` por episódio aguardando, no padrão das outras abertas pela pipeline."""

    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def registrar(self, episodio_id: str, erro: str) -> None:
        abertas = self._abertas(episodio_id)
        if abertas:
            self._gh("issue", "comment", str(abertas[0]), "--body",
                     self._com_execucao(f"A cota continuava esgotada nesta tentativa.\n\n```\n{erro}\n```"))
            return
        self._gh("issue", "create", "--title", self.titulo(episodio_id), "--label", "incidente",
                 "--body", self._corpo(episodio_id, erro))

    def resolver(self, episodio_id: str) -> None:
        for numero in self._abertas(episodio_id):
            self._gh("issue", "close", str(numero), "--reason", "completed", "--comment",
                     self._com_execucao(f"O {episodio_id} foi publicado com o Gemini."))

    @staticmethod
    def titulo(episodio_id: str) -> str:
        # Sem terminar em ": <id>": esse é o padrão das issues de roteiro, que o workflow fecha sozinho.
        return f"Cota do Gemini esgotada: {episodio_id} aguardando"

    def _corpo(self, episodio_id: str, erro: str) -> str:
        return self._com_execucao("\n".join([
            f"A cota diária do Gemini acabou e o {episodio_id} não foi publicado. Ele não vai para o Kokoro: "
            "aguarda a cota renovar, e o site avisa que sai em breve (ADR 0011).",
            "",
            "O `publicar.yml` agendado tenta de novo às 08:15 UTC (5h15 em Natal), depois da renovação. "
            "Para tentar antes, rode o workflow **Publicar episódio** à mão.",
            "",
            "A issue fecha sozinha quando o episódio for publicado.",
            "",
            f"```\n{erro}\n```",
        ]))

    def _com_execucao(self, texto: str) -> str:
        return f"{texto}\n\nExecução: {self.execucao}" if self.execucao else texto

    def _abertas(self, episodio_id: str) -> list[int]:
        titulo = self.titulo(episodio_id)
        saida = self._gh("issue", "list", "--state", "open", "--label", "incidente",
                         "--search", f'"{titulo}" in:title', "--json", "number,title", capture_output=True, text=True)
        return [issue["number"] for issue in json.loads(saida.stdout or "[]") if issue["title"] == titulo]

    def _gh(self, *argumentos: str, **opcoes: Any) -> subprocess.CompletedProcess:
        return self.executar(["gh", *argumentos, "--repo", self.repositorio], check=True, **opcoes)
