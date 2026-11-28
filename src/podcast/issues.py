"""Issues `incidente` que a pipeline abre pelo `gh`: uma por episódio, achada pelo título exato.

O título nunca termina em ": <id>": esse é o padrão das issues de roteiro reprovado, que o
`publicar.yml` fecha sozinho quando o episódio sai.
"""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ROTULO = "incidente"


@dataclass(frozen=True)
class IssuesDeIncidente:
    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def abrir_ou_comentar(self, titulo: str, corpo_novo: str, comentario: str) -> None:
        """Abre a issue com `corpo_novo`; se já houver uma aberta com o título, só comenta."""
        abertas = self.abertas(titulo)
        if abertas:
            self._gh("issue", "comment", str(abertas[0]), "--body", self.com_execucao(comentario))
        else:
            self._gh("issue", "create", "--title", titulo, "--label", ROTULO, "--body", self.com_execucao(corpo_novo))

    def comentar(self, titulo: str, comentario: str) -> bool:
        """Comenta na issue aberta com o título, se houver. Não abre nenhuma."""
        abertas = self.abertas(titulo)
        for numero in abertas:
            self._gh("issue", "comment", str(numero), "--body", self.com_execucao(comentario))
        return bool(abertas)

    def fechar(self, titulo: str, comentario: str) -> None:
        for numero in self.abertas(titulo):
            self._gh("issue", "close", str(numero), "--reason", "completed", "--comment", self.com_execucao(comentario))

    def abertas(self, titulo: str) -> list[int]:
        saida = self._gh("issue", "list", "--state", "open", "--label", ROTULO,
                         "--search", f'"{titulo}" in:title', "--json", "number,title", capture_output=True, text=True)
        return [issue["number"] for issue in json.loads(saida.stdout or "[]") if issue["title"] == titulo]

    def com_execucao(self, texto: str) -> str:
        return f"{texto}\n\nExecução: {self.execucao}" if self.execucao else texto

    def _gh(self, *argumentos: str, **opcoes: Any) -> subprocess.CompletedProcess:
        return self.executar(["gh", *argumentos, "--repo", self.repositorio], check=True, **opcoes)
