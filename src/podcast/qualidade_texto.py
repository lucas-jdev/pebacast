"""QA de texto (#69): o TTS falou o que o roteiro diz?

Depois de publicar, o trecho de fala do MP3 vai para dois modelos que entendem áudio, e cada
transcrição é alinhada palavra por palavra com o roteiro original. Só conta a divergência que
aparece nas duas: erro de um modelo só é ruído de transcrição. Em modo aviso, nunca segura a
publicação; com divergência confirmada, abre uma issue `incidente` para o Lucas ouvir o trecho.
"""

import re
import subprocess
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol

from podcast.dominio import Fala
from podcast.issues import IssuesDeIncidente
from podcast.retentativa import tentar

PROMPT = (
    "Transcreva literalmente este áudio, em português do Brasil. Escreva exatamente as palavras faladas, "
    "mesmo que pareçam erradas: não corrija, não resuma, não identifique quem fala e não comente. "
    "Devolva só o texto."
)
CONTEXTO_PALAVRAS = 3
STATUS_TRANSITORIOS = frozenset({408, 429})
PALAVRA = re.compile(r"\w+")


class Transcritor(Protocol):
    nome: str

    def transcrever(self, audio_mp3: bytes) -> str: ...


class GeminiTranscritor:
    def __init__(
        self,
        modelo: str,
        cliente: Any = None,
        tentativas: int = 3,
        espera_inicial_s: float = 15.0,
        timeout_s: float = 300.0,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.nome = modelo
        self._cliente = cliente
        self._tentativas = tentativas
        self._espera_inicial_s = espera_inicial_s
        self._timeout_s = timeout_s
        self._dormir = dormir

    def transcrever(self, audio_mp3: bytes) -> str:
        from google.genai import types

        if self._cliente is None:
            from podcast.tts.gemini import criar_cliente

            self._cliente = criar_cliente(self._timeout_s)
        parte = types.Part.from_bytes(data=audio_mp3, mime_type="audio/mpeg")

        def chamar() -> str:
            return self._cliente.models.generate_content(model=self.nome, contents=[parte, PROMPT]).text or ""

        # Os modelos que entendem áudio deram 503 em série no teste do Prumo: 5xx e 429 esperam e tentam de novo.
        return tentar(chamar, rotulo=f"Transcrição ({self.nome})", tentativas=self._tentativas,
                      espera_inicial_s=self._espera_inicial_s, dormir=self._dormir, desistir=_desistir)


def _desistir(erro: Exception) -> Exception | None:
    status = getattr(erro, "code", None) or getattr(erro, "status_code", None)
    pedido_errado = isinstance(status, int) and 400 <= status < 500 and status not in STATUS_TRANSITORIOS
    return erro if pedido_errado else None


def normalizar(texto: str, equivalencias: Mapping[str, str] | None = None) -> list[str]:
    """Minúsculas, sem acento e sem pontuação; formas de fala trocadas pela forma escrita."""
    equivalencias = equivalencias or {}
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    palavras: list[str] = []
    for palavra in PALAVRA.findall(sem_acento):
        palavras.extend(equivalencias.get(palavra, palavra).split())
    return palavras


@dataclass(frozen=True)
class Trecho:
    """Uma divergência de uma transcrição: as palavras [inicio, fim) do roteiro e o que se ouviu no lugar."""

    inicio: int
    fim: int
    ouvido: str


def divergencias(roteiro: Sequence[str], transcricao: Sequence[str]) -> list[Trecho]:
    trechos = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, roteiro, transcricao, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        ouvidas = transcricao[j1:j2]
        # Número por extenso transcrito como algarismo é ruído, não erro do áudio.
        if ouvidas and all(palavra.isdigit() for palavra in ouvidas):
            continue
        trechos.append(Trecho(i1, i2, " ".join(ouvidas)))
    return trechos


def confirmadas(primeira: Sequence[Trecho], segunda: Sequence[Trecho]) -> list[tuple[Trecho, Trecho]]:
    """Para cada divergência da primeira transcrição, a da segunda que cai no mesmo trecho do roteiro."""
    pares = []
    for a in primeira:
        par = next((b for b in segunda if a.inicio <= b.fim and b.inicio <= a.fim), None)
        if par is not None:
            pares.append((a, par))
    return pares


@dataclass(frozen=True)
class Divergencia:
    persona: str
    fala: str
    trecho: str
    ouvido: Mapping[str, str]


@dataclass(frozen=True)
class LaudoDeTexto:
    modelos: tuple[str, ...]
    divergencias: tuple[Divergencia, ...]

    @property
    def aprovado(self) -> bool:
        return not self.divergencias

    def markdown(self, titulo: str) -> str:
        linhas = [f"### {titulo}", ""]
        if self.aprovado:
            linhas.append(f"Nenhuma divergência confirmada pelos dois modelos ({', '.join(self.modelos)}).")
            return "\n".join(linhas) + "\n"
        linhas += [
            f"{len(self.divergencias)} divergência(s) confirmada(s) pelos dois modelos. "
            "O trecho divergente do roteiro está entre colchetes.",
            "",
            f"| Persona | Roteiro | {' | '.join(self.modelos)} |",
            f"|---|---|{'---|' * len(self.modelos)}",
        ]
        for divergencia in self.divergencias:
            ouvidos = " | ".join(_celula(divergencia.ouvido[modelo]) for modelo in self.modelos)
            linhas.append(f"| {divergencia.persona} | {_celula(divergencia.trecho)} | {ouvidos} |")
        return "\n".join(linhas) + "\n"


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|") if texto else "(nada)"


class RegistroDeTexto(Protocol):
    def registrar(self, episodio_id: str, laudo: LaudoDeTexto) -> None: ...


@dataclass(frozen=True)
class IncidentesDeTexto:
    """Uma issue `incidente` por episódio com divergência. Em modo aviso, quem fecha é o Lucas."""

    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def registrar(self, episodio_id: str, laudo: LaudoDeTexto) -> None:
        if laudo.aprovado:
            return
        relatorio = laudo.markdown(f"Texto do {episodio_id}")
        issues = IssuesDeIncidente(self.repositorio, self.execucao, self.executar)
        issues.abrir_ou_comentar(self.titulo(episodio_id), "\n".join([
            f"O {episodio_id} foi publicado, mas o áudio diverge do roteiro em trechos que os dois modelos de "
            "transcrição ouviram igual.",
            "",
            relatorio,
            "O QA de texto está em modo aviso (#69). Ouça cada trecho e comente aqui se o aviso **acertou** ou foi "
            "**alarme falso**: é o que calibra a regeneração automática (#70). Depois, feche a issue.",
        ]), f"Nova verificação do {episodio_id}.\n\n{relatorio}")

    @staticmethod
    def titulo(episodio_id: str) -> str:
        return f"Texto do {episodio_id} diverge do roteiro"


@dataclass(frozen=True)
class QaDeTexto:
    transcritores: tuple[Transcritor, Transcritor]
    equivalencias: Mapping[str, str]
    incidentes: RegistroDeTexto | None = None
    recortar: Callable[[Path, tuple[float, float]], bytes] = lambda mp3, trecho: recortar_mp3(mp3, trecho)

    @classmethod
    def de_config(cls, config: Mapping[str, Any], incidentes: RegistroDeTexto | None = None,
                  criar_transcritor: Callable[[str], Transcritor] | None = None) -> "QaDeTexto":
        criar = criar_transcritor or (lambda modelo: GeminiTranscritor(modelo, timeout_s=config.get("timeout_s", 300)))
        primeiro, segundo = config["modelos"]
        equivalencias = {}
        for forma, escrita in (config.get("equivalencias") or {}).items():
            [palavra] = normalizar(forma)  # a forma falada é uma palavra só; a escrita pode ter várias
            equivalencias[palavra] = " ".join(normalizar(escrita))
        return cls((criar(primeiro), criar(segundo)), equivalencias, incidentes)

    def rodar(self, episodio_id: str, mp3: Path, trecho_fala: tuple[float, float], falas: Sequence[Fala]) -> LaudoDeTexto:
        audio = self.recortar(mp3, trecho_fala)
        laudo = self.comparar(falas, [transcritor.transcrever(audio) for transcritor in self.transcritores])
        if self.incidentes is not None:
            self.incidentes.registrar(episodio_id, laudo)
        return laudo

    def comparar(self, falas: Sequence[Fala], transcricoes: Sequence[str]) -> LaudoDeTexto:
        palavras, fala_da_palavra = [], []
        for indice, fala in enumerate(falas):
            normalizadas = normalizar(fala.texto, self.equivalencias)
            palavras += normalizadas
            fala_da_palavra += [indice] * len(normalizadas)

        primeira, segunda = (divergencias(palavras, normalizar(t, self.equivalencias)) for t in transcricoes)
        modelos = tuple(transcritor.nome for transcritor in self.transcritores)
        achadas = []
        for a, b in confirmadas(primeira, segunda):
            inicio, fim = min(a.inicio, b.inicio), max(a.fim, b.fim)
            fala = falas[fala_da_palavra[min(inicio, len(palavras) - 1)]]
            achadas.append(Divergencia(fala.persona.nome, fala.texto, _contexto(palavras, inicio, fim),
                                       dict(zip(modelos, (a.ouvido, b.ouvido)))))
        return LaudoDeTexto(modelos, tuple(achadas))


def _contexto(palavras: Sequence[str], inicio: int, fim: int) -> str:
    antes = palavras[max(0, inicio - CONTEXTO_PALAVRAS):inicio]
    depois = palavras[fim:fim + CONTEXTO_PALAVRAS]
    return " ".join([*antes, f"[{' '.join(palavras[inicio:fim])}]", *depois])


def recortar_mp3(mp3: Path, trecho: tuple[float, float]) -> bytes:
    """Só a fala, sem a vinheta: a música atrapalha a transcrição e não está no roteiro."""
    inicio, fim = trecho
    comando = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{inicio:.3f}", "-i", str(mp3),
               "-t", f"{fim - inicio:.3f}", "-c", "copy", "-f", "mp3", "pipe:1"]
    return subprocess.run(comando, capture_output=True, check=True).stdout
