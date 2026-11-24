"""QA de pronúncia (#107): o TTS disse os termos do dicionário como a instrução pede?

O QA de texto não vê esse erro: "Pebacast" com E fechado vira o mesmo texto que o certo (co-002).
Depois de publicar, cada janela da fala vai para dois modelos que entendem áudio, com a lista dos
termos de `tts.pronuncia` que têm `instrucao` e aparecem no roteiro. Cada modelo diz, em cada vez
que ouviu um termo, se soou certo ou errado. Só conta o erro que os dois marcam na mesma janela.
Em modo aviso, nunca segura a publicação; com erro confirmado, abre uma issue `incidente`.

    python -m podcast.qualidade_pronuncia episodio.mp3 episodios/co-002/roteiro.json
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from podcast.audio import Trechos, duracao_mp3
from podcast.dominio import Fala
from podcast.issues import IssuesDeIncidente
from podcast.pronuncia import Pronuncia, carregar_pronuncias
from podcast.qualidade_texto import (
    JANELA_MAXIMA_PADRAO_S,
    TranscricaoIncompleta,
    cortada_por_limite,
    desistir_de_repetir,
    janelas,
    recortar_mp3,
)
from podcast.retentativa import tentar

VEREDITOS = ("certo", "errado")
ESQUEMA = {
    "type": "object",
    "properties": {
        "ocorrencias": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string"},
                    "segundo": {"type": "number"},
                    "veredito": {"type": "string", "enum": list(VEREDITOS)},
                    "ouvido": {"type": "string"},
                },
                "required": ["termo", "segundo", "veredito", "ouvido"],
            },
        },
    },
    "required": ["ocorrencias"],
}


class RespostaInvalida(Exception):
    """A resposta do modelo não segue o esquema ou cita algo fora do pedido."""


@dataclass(frozen=True)
class Ocorrencia:
    termo: str
    segundo: float
    veredito: str
    ouvido: str

    @property
    def errada(self) -> bool:
        return self.veredito == "errado"


class Ouvinte(Protocol):
    nome: str

    def ouvir(self, audio_mp3: bytes, termos: Sequence[Pronuncia]) -> list[Ocorrencia]: ...


def montar_pedido(termos: Sequence[Pronuncia]) -> str:
    lista = "\n".join(f'- "{termo.termo}": {" ".join(termo.instrucao.split())}' for termo in termos)
    return (
        "Ouça este trecho de um podcast em português do Brasil. Para cada termo da lista, encontre cada vez que "
        "ele é dito e julgue a pronúncia pela instrução ao lado:\n"
        f"{lista}\n"
        "Em cada ocorrência, informe o termo exatamente como está na lista, o segundo aproximado desde o início "
        "do trecho, o veredito (certo ou errado) e uma grafia curta de como soou. Não liste termos fora da lista. "
        "Se um termo não for dito, não o inclua."
    )


def ler_resposta(texto: str, termos: Sequence[Pronuncia]) -> list[Ocorrencia]:
    try:
        dados = json.loads(texto)
        itens = dados["ocorrencias"]
        ocorrencias = [
            Ocorrencia(str(item["termo"]), float(item["segundo"]), str(item["veredito"]), str(item["ouvido"]))
            for item in itens
        ]
    except (ValueError, TypeError, KeyError) as erro:
        raise RespostaInvalida(f"resposta fora do esquema: {erro}") from erro

    pedidos = {termo.termo for termo in termos}
    for ocorrencia in ocorrencias:
        if ocorrencia.termo not in pedidos:
            raise RespostaInvalida(f"termo fora da lista: {ocorrencia.termo!r}")
        if ocorrencia.veredito not in VEREDITOS:
            raise RespostaInvalida(f"veredito fora de {VEREDITOS}: {ocorrencia.veredito!r}")
    return ocorrencias


class GeminiOuvinte:
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

    def ouvir(self, audio_mp3: bytes, termos: Sequence[Pronuncia]) -> list[Ocorrencia]:
        from google.genai import types

        if self._cliente is None:
            from podcast.tts.gemini import criar_cliente

            self._cliente = criar_cliente(self._timeout_s)
        parte = types.Part.from_bytes(data=audio_mp3, mime_type="audio/mpeg")
        config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=ESQUEMA)

        def chamar() -> str:
            resposta = self._cliente.models.generate_content(
                model=self.nome, contents=[parte, montar_pedido(termos)], config=config)
            if cortada_por_limite(resposta):
                raise TranscricaoIncompleta(f"{self.nome} parou no limite de tokens de saída")
            return resposta.text or ""

        texto = tentar(chamar, rotulo=f"QA de pronúncia ({self.nome})", tentativas=self._tentativas,
                       espera_inicial_s=self._espera_inicial_s, dormir=self._dormir, desistir=desistir_de_repetir)
        return ler_resposta(texto, termos)


def termos_do_roteiro(falas: Sequence[Fala], pronuncias: Sequence[Pronuncia]) -> dict[str, tuple[Pronuncia, int]]:
    """Os termos com instrução que o roteiro cita, com quantas vezes. Recebe as falas originais, antes da grafia trocada."""
    termos = {}
    for pronuncia in pronuncias:
        if not pronuncia.instrucao:
            continue
        vezes = sum(len(pronuncia.padrao.findall(fala.texto)) for fala in falas)
        if vezes:
            termos[pronuncia.termo] = (pronuncia, vezes)
    return termos


@dataclass(frozen=True)
class Contagem:
    termo: str
    no_roteiro: int
    certas: Mapping[str, int]
    erradas: Mapping[str, int]


@dataclass(frozen=True)
class ErroConfirmado:
    termo: str
    instante_s: float
    ouvido: Mapping[str, str]


@dataclass(frozen=True)
class LaudoDePronuncia:
    modelos: tuple[str, ...]
    contagens: tuple[Contagem, ...]
    erros: tuple[ErroConfirmado, ...]

    @property
    def aprovado(self) -> bool:
        return not self.erros

    def markdown(self, titulo: str) -> str:
        linhas = [f"### {titulo}", ""]
        if self.aprovado:
            linhas.append(f"Nenhum erro de pronúncia confirmado pelos dois modelos ({', '.join(self.modelos)}).")
        else:
            linhas.append(f"{len(self.erros)} erro(s) de pronúncia confirmado(s) pelos dois modelos.")
        linhas += [
            "",
            "Quantas vezes cada modelo ouviu o termo (certas / erradas). Ouvir menos vezes que o roteiro diz "
            "significa que o QA não julgou aquelas ocorrências.",
            "",
            f"| Termo | No roteiro | {' | '.join(self.modelos)} |",
            f"|---|---|{'---|' * len(self.modelos)}",
        ]
        for contagem in self.contagens:
            ouvidas = " | ".join(f"{contagem.certas[modelo]} / {contagem.erradas[modelo]}" for modelo in self.modelos)
            linhas.append(f"| {contagem.termo} | {contagem.no_roteiro} | {ouvidas} |")
        if self.erros:
            linhas += ["", f"| Termo | Por volta de | {' | '.join(self.modelos)} |", f"|---|---|{'---|' * len(self.modelos)}"]
            for erro in self.erros:
                ouvidos = " | ".join(_celula(erro.ouvido[modelo]) for modelo in self.modelos)
                linhas.append(f"| {erro.termo} | {_relogio(erro.instante_s)} | {ouvidos} |")
        return "\n".join(linhas) + "\n"


def confirmar(inicio_s: float, termo: str, por_modelo: Mapping[str, Sequence[Ocorrencia]]) -> ErroConfirmado | None:
    erradas = {modelo: [o for o in ocorrencias if o.termo == termo and o.errada] for modelo, ocorrencias in por_modelo.items()}
    if not all(erradas.values()):
        return None
    primeiro = next(iter(erradas.values()))[0]
    ouvido = {modelo: "; ".join(o.ouvido for o in lista) for modelo, lista in erradas.items()}
    return ErroConfirmado(termo, inicio_s + primeiro.segundo, ouvido)


class RegistroDePronuncia(Protocol):
    def registrar(self, episodio_id: str, laudo: LaudoDePronuncia) -> None: ...


@dataclass(frozen=True)
class IncidentesDePronuncia:
    """Uma issue `incidente` por episódio com erro confirmado. Em modo aviso, quem fecha é o Lucas."""

    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def registrar(self, episodio_id: str, laudo: LaudoDePronuncia) -> None:
        if laudo.aprovado:
            return
        relatorio = laudo.markdown(f"Pronúncia do {episodio_id}")
        issues = IssuesDeIncidente(self.repositorio, self.execucao, self.executar)
        issues.abrir_ou_comentar(self.titulo(episodio_id), "\n".join([
            f"O {episodio_id} foi publicado, mas os dois modelos ouviram um termo do dicionário de pronúncia "
            "dito de um jeito diferente do que a instrução pede.",
            "",
            relatorio,
            "O QA de pronúncia está em modo aviso (#107). Ouça o trecho e comente aqui se o aviso **acertou** ou "
            "foi **alarme falso**. Se acertou, regrave o áudio (workflow Regravar áudio). Depois, feche a issue.",
        ]), f"Nova verificação do {episodio_id}.\n\n{relatorio}")

    @staticmethod
    def titulo(episodio_id: str) -> str:
        return f"Pronúncia do {episodio_id} diverge do dicionário"


@dataclass(frozen=True)
class QaDePronuncia:
    ouvintes: tuple[Ouvinte, Ouvinte]
    pronuncias: tuple[Pronuncia, ...]
    incidentes: RegistroDePronuncia | None = None
    recortar: Callable[[Path, tuple[float, float]], bytes] = lambda mp3, trecho: recortar_mp3(mp3, trecho)
    janela_maxima_s: float = JANELA_MAXIMA_PADRAO_S

    @classmethod
    def de_config(cls, config: Mapping[str, Any], config_tts: Mapping[str, Any],
                  incidentes: RegistroDePronuncia | None = None,
                  criar_ouvinte: Callable[[str], Ouvinte] | None = None) -> "QaDePronuncia":
        criar = criar_ouvinte or (lambda modelo: GeminiOuvinte(modelo, timeout_s=config.get("timeout_s", 300)))
        primeiro, segundo = config["modelos"]
        return cls((criar(primeiro), criar(segundo)), tuple(carregar_pronuncias(config_tts)), incidentes,
                   janela_maxima_s=config.get("janela_maxima_s", JANELA_MAXIMA_PADRAO_S))

    def rodar(self, episodio_id: str, mp3: Path, trechos: Trechos, falas: Sequence[Fala]) -> LaudoDePronuncia | None:
        """Sem nenhum termo com instrução no roteiro, não ouve nada e devolve None."""
        termos = termos_do_roteiro(falas, self.pronuncias)
        if not termos:
            return None
        laudo = self.ouvir(mp3, janelas(trechos.fala, trechos.trocas_s, self.janela_maxima_s), termos)
        if self.incidentes is not None:
            self.incidentes.registrar(episodio_id, laudo)
        return laudo

    def ouvir(self, mp3: Path, cortes: Sequence[tuple[float, float]],
              termos: Mapping[str, tuple[Pronuncia, int]]) -> LaudoDePronuncia:
        pedidos = [pronuncia for pronuncia, _ in termos.values()]
        modelos = tuple(ouvinte.nome for ouvinte in self.ouvintes)
        certas = {termo: dict.fromkeys(modelos, 0) for termo in termos}
        erradas = {termo: dict.fromkeys(modelos, 0) for termo in termos}
        erros = []
        for inicio, fim in cortes:
            audio = self.recortar(mp3, (inicio, fim))
            por_modelo = {ouvinte.nome: ouvinte.ouvir(audio, pedidos) for ouvinte in self.ouvintes}
            for modelo, ocorrencias in por_modelo.items():
                for ocorrencia in ocorrencias:
                    (erradas if ocorrencia.errada else certas)[ocorrencia.termo][modelo] += 1
            erros += [erro for termo in termos if (erro := confirmar(inicio, termo, por_modelo))]
        contagens = tuple(Contagem(termo, vezes, certas[termo], erradas[termo]) for termo, (_, vezes) in termos.items())
        return LaudoDePronuncia(modelos, contagens, tuple(erros))


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|") if texto else "(nada)"


def _relogio(segundos: float) -> str:
    minutos, resto = divmod(max(0, round(segundos)), 60)
    return f"{minutos:02d}:{resto:02d}"


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qualidade_pronuncia",
                                     description="Roda o QA de pronúncia num MP3 qualquer, para calibrar.")
    parser.add_argument("mp3", type=Path)
    parser.add_argument("roteiro", type=Path, help="roteiro.json do episódio")
    parser.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    parser.add_argument("--personas", type=Path, default=Path("curriculum/personas"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from podcast.personas import carregar_personas
    from podcast.publicacao import carregar_falas

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _criar_parser().parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    qa = QaDePronuncia.de_config(config["qualidade_pronuncia"], config["tts"])
    falas = carregar_falas(json.loads(args.roteiro.read_text(encoding="utf-8")), carregar_personas(args.personas))
    termos = termos_do_roteiro(falas, qa.pronuncias)
    if not termos:
        print("O roteiro não cita nenhum termo do dicionário com instrução.")
        return 0
    cortes = janelas((0.0, duracao_mp3(args.mp3)), (), qa.janela_maxima_s)
    print(qa.ouvir(args.mp3, cortes, termos).markdown(f"Pronúncia em {args.mp3.name}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
