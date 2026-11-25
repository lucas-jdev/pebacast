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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol

from podcast.audio import Trechos
from podcast.dominio import Fala
from podcast.issues import IssuesDeIncidente
from podcast.retentativa import tentar

PROMPT = (
    "Transcreva literalmente este áudio, em português do Brasil. Escreva exatamente as palavras faladas, "
    "mesmo que pareçam erradas: não corrija, não resuma, não identifique quem fala e não comente. "
    "Devolva só o texto."
)
CONTEXTO_PALAVRAS = 3
# Trecho divergente maior que isso aparece resumido no laudo: uma transcrição cortada no meio
# virava uma linha com o resto do episódio inteiro (se-002, 21/11).
MAXIMO_PALAVRAS_NO_TRECHO = 12
JANELA_MAXIMA_PADRAO_S = 300.0
COBERTURA_MINIMA_PADRAO = 0.85


class TranscricaoIncompleta(Exception):
    """A transcrição cobre pouco do roteiro: comparar daria um alarme falso do tamanho do que faltou."""
STATUS_TRANSITORIOS = frozenset({408, 429})
PALAVRA = re.compile(r"\w+")
# Artigo, conjunção e interjeição soltos (#132): nos 4 primeiros incidentes, 18 de 48 divergências eram
# só isso ("[] a", "[e] (nada)"), e nenhuma mudava o que o ouvinte entende. A comparação já é sem acento.
# "não", "nem" e "sem" ficam de fora de propósito: um deles sumido inverte a frase.
PALAVRAS_DE_FUNCAO = frozenset({
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "e", "ou", "mas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "num", "numa",
    "ah", "eh", "oh", "ai", "ei", "hum",
})


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
            resposta = self._cliente.models.generate_content(model=self.nome, contents=[parte, PROMPT])
            if cortada_por_limite(resposta):
                raise TranscricaoIncompleta(f"{self.nome} parou no limite de tokens de saída")
            return resposta.text or ""

        # Os modelos que entendem áudio deram 503 em série no teste do Prumo: 5xx e 429 esperam e tentam de novo.
        return tentar(chamar, rotulo=f"Transcrição ({self.nome})", tentativas=self._tentativas,
                      espera_inicial_s=self._espera_inicial_s, dormir=self._dormir, desistir=desistir_de_repetir)


def cortada_por_limite(resposta: Any) -> bool:
    candidatos = getattr(resposta, "candidates", None) or []
    return any("MAX_TOKENS" in str(getattr(candidato, "finish_reason", "")) for candidato in candidatos)


def janelas(trecho_fala: tuple[float, float], trocas_s: Sequence[float], maximo_s: float) -> list[tuple[float, float]]:
    """Corta a fala em janelas de até `maximo_s`, sempre numa troca de bloco quando dá.

    Cortar no meio de uma palavra faz os dois modelos errarem igual na borda, e isso seria
    confirmado como divergência. Só corta fora de uma troca quando não há nenhuma na janela.
    """
    inicio, fim = trecho_fala
    cortes = sorted(troca for troca in trocas_s if inicio < troca < fim)
    resultado = []
    while fim - inicio > maximo_s:
        candidatas = [troca for troca in cortes if inicio < troca <= inicio + maximo_s]
        corte = candidatas[-1] if candidatas else inicio + maximo_s
        resultado.append((inicio, corte))
        inicio = corte
    resultado.append((inicio, fim))
    return resultado


def desistir_de_repetir(erro: Exception) -> Exception | None:
    if isinstance(erro, TranscricaoIncompleta):
        return erro  # mesmo áudio, mesmo limite: repetir só gasta cota
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
        if tag != "equal" and not e_ruido(roteiro[i1:i2], transcricao[j1:j2]):
            trechos.append(Trecho(i1, i2, " ".join(transcricao[j1:j2])))
    return trechos


def e_ruido(escritas: Sequence[str], ouvidas: Sequence[str]) -> bool:
    """Diferença que é da transcrição, e não do áudio."""
    # Número por extenso transcrito como algarismo.
    if ouvidas and all(palavra.isdigit() for palavra in ouvidas):
        return True
    # A mesma fala com outra separação: "trade off" e "tradeoff", "senao" e "se nao".
    if "".join(escritas) == "".join(ouvidas):
        return True
    return all(palavra in PALAVRAS_DE_FUNCAO for palavra in (*escritas, *ouvidas))


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
    janela_maxima_s: float = JANELA_MAXIMA_PADRAO_S
    cobertura_minima: float = COBERTURA_MINIMA_PADRAO

    @classmethod
    def de_config(cls, config: Mapping[str, Any], incidentes: RegistroDeTexto | None = None,
                  criar_transcritor: Callable[[str], Transcritor] | None = None) -> "QaDeTexto":
        criar = criar_transcritor or (lambda modelo: GeminiTranscritor(modelo, timeout_s=config.get("timeout_s", 300)))
        primeiro, segundo = config["modelos"]
        equivalencias = {}
        for forma, escrita in (config.get("equivalencias") or {}).items():
            [palavra] = normalizar(forma)  # a forma falada é uma palavra só; a escrita pode ter várias
            equivalencias[palavra] = " ".join(normalizar(escrita))
        return cls((criar(primeiro), criar(segundo)), equivalencias, incidentes,
                   janela_maxima_s=config.get("janela_maxima_s", JANELA_MAXIMA_PADRAO_S),
                   cobertura_minima=config.get("cobertura_minima", COBERTURA_MINIMA_PADRAO))

    def rodar(self, episodio_id: str, mp3: Path, trechos: Trechos, falas: Sequence[Fala]) -> LaudoDeTexto:
        # Episódio inteiro numa requisição só saía cortado: no se-002, os dois modelos pararam em 69% do roteiro.
        audios = [self.recortar(mp3, janela) for janela in janelas(trechos.fala, trechos.trocas_s, self.janela_maxima_s)]
        transcricoes = [" ".join(transcritor.transcrever(audio) for audio in audios) for transcritor in self.transcritores]
        laudo = self.comparar(falas, transcricoes)
        if self.incidentes is not None:
            self.incidentes.registrar(episodio_id, laudo)
        return laudo

    def comparar(self, falas: Sequence[Fala], transcricoes: Sequence[str]) -> LaudoDeTexto:
        palavras, fala_da_palavra = [], []
        for indice, fala in enumerate(falas):
            normalizadas = normalizar(fala.texto, self.equivalencias)
            palavras += normalizadas
            fala_da_palavra += [indice] * len(normalizadas)

        transcritas = [normalizar(transcricao, self.equivalencias) for transcricao in transcricoes]
        modelos = tuple(transcritor.nome for transcritor in self.transcritores)
        for modelo, palavras_transcritas in zip(modelos, transcritas):
            cobertura = len(palavras_transcritas) / max(len(palavras), 1)
            if cobertura < self.cobertura_minima:
                raise TranscricaoIncompleta(
                    f"{modelo} transcreveu {len(palavras_transcritas)} palavras para {len(palavras)} do roteiro "
                    f"({cobertura:.0%}, mínimo {self.cobertura_minima:.0%})")

        primeira, segunda = (divergencias(palavras, transcrita) for transcrita in transcritas)
        achadas = []
        for inicio, fim, ouvidos in _juntar(confirmadas(primeira, segunda)):
            fala = falas[fala_da_palavra[min(inicio, len(palavras) - 1)]]
            achadas.append(Divergencia(fala.persona.nome, fala.texto, _contexto(palavras, inicio, fim),
                                       dict(zip(modelos, ouvidos))))
        return LaudoDeTexto(modelos, tuple(achadas))


def _juntar(pares: Sequence[tuple[Trecho, Trecho]]) -> list[tuple[int, int, tuple[str, str]]]:
    """Pares que se sobrepõem no roteiro viram uma divergência só, com o que cada modelo ouviu ali."""
    grupos: list[list[tuple[Trecho, Trecho]]] = []
    for a, b in pares:
        if grupos and min(a.inicio, b.inicio) <= max(max(x.fim, y.fim) for x, y in grupos[-1]):
            grupos[-1].append((a, b))
        else:
            grupos.append([(a, b)])
    return [
        (min(min(a.inicio, b.inicio) for a, b in grupo), max(max(a.fim, b.fim) for a, b in grupo),
         (_ouvido(a for a, _ in grupo), _ouvido(b for _, b in grupo)))
        for grupo in grupos
    ]


def _ouvido(trechos: Iterable[Trecho]) -> str:
    # O mesmo trecho de um modelo pode casar com vários do outro: entra uma vez só.
    return " ".join(trecho.ouvido for trecho in dict.fromkeys(trechos) if trecho.ouvido)


def _contexto(palavras: Sequence[str], inicio: int, fim: int) -> str:
    antes = palavras[max(0, inicio - CONTEXTO_PALAVRAS):inicio]
    depois = palavras[fim:fim + CONTEXTO_PALAVRAS]
    trecho = list(palavras[inicio:fim])
    if len(trecho) > MAXIMO_PALAVRAS_NO_TRECHO:
        trecho = [*trecho[:MAXIMO_PALAVRAS_NO_TRECHO], f"… (+{len(trecho) - MAXIMO_PALAVRAS_NO_TRECHO} palavras)"]
    return " ".join([*antes, f"[{' '.join(trecho)}]", *depois])


def recortar_mp3(mp3: Path, trecho: tuple[float, float]) -> bytes:
    """Só a fala, sem a vinheta: a música atrapalha a transcrição e não está no roteiro."""
    inicio, fim = trecho
    comando = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{inicio:.3f}", "-i", str(mp3),
               "-t", f"{fim - inicio:.3f}", "-c", "copy", "-f", "mp3", "pipe:1"]
    return subprocess.run(comando, capture_output=True, check=True).stdout
