import argparse
import json
import random
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import ascii_uppercase

import yaml

from podcast.audio import Audio, exportar_mp3
from podcast.dominio import Fala, Persona
from podcast.personas import carregar_personas
from podcast.tts.provedor import TtsProvider

CANDIDATOS = ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "kokoro", "piper")
CRITERIOS = {
    "naturalidade": "Soa como uma pessoa conversando, e não como uma leitura de máquina?",
    "pronuncia_tecnica": "Os termos em inglês (deploy, trade-off, Spring Boot, Kubernetes) soam corretos?",
    "diferenciacao": "Dá para distinguir Davi e Helena só pela voz e pelo jeito de falar?",
}
NOTA_MINIMA, NOTA_MAXIMA = 1, 5
ARQUIVO_GABARITO = ".gabarito.json"
ARQUIVO_AVALIACAO = "avaliacao.yaml"
PASTA_AMOSTRAS = "amostras"


@dataclass(frozen=True)
class Resultado:
    candidato: str
    amostra: str
    notas: Mapping[str, int]

    @property
    def media(self) -> float:
        return statistics.mean(self.notas.values())


def carregar_trecho(arquivo: Path, personas: Mapping[str, Persona]) -> list[Fala]:
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    return [_criar_fala(item, personas) for item in dados["falas"]]


def gerar(
    falas: Sequence[Fala],
    provedores: Sequence[TtsProvider],
    saida: Path,
    bitrate_kbps: int,
    sorteio: random.Random | None = None,
) -> None:
    if (saida / ARQUIVO_GABARITO).exists():
        raise FileExistsError(f"Já existe um teste em {saida}. Apague a pasta para gerar outro.")
    _validar_nomes_unicos(provedores)

    audios = {provedor.nome: _sintetizar(provedor, falas) for provedor in provedores}
    candidatos = list(audios)
    (sorteio or random.SystemRandom()).shuffle(candidatos)
    gabarito = dict(zip(ascii_uppercase, candidatos))

    for amostra, candidato in gabarito.items():
        exportar_mp3(audios[candidato], saida / PASTA_AMOSTRAS / f"{amostra}.mp3", bitrate_kbps)
    _escrever_avaliacao(saida / ARQUIVO_AVALIACAO, gabarito)
    (saida / ARQUIVO_GABARITO).write_text(json.dumps(gabarito, indent=2), encoding="utf-8")


def revelar(saida: Path) -> list[Resultado]:
    gabarito = json.loads((saida / ARQUIVO_GABARITO).read_text(encoding="utf-8"))
    avaliacao = yaml.safe_load((saida / ARQUIVO_AVALIACAO).read_text(encoding="utf-8"))["amostras"]

    problemas = [
        problema
        for amostra in gabarito
        for problema in _problemas_da_avaliacao(amostra, avaliacao.get(amostra) or {})
    ]
    if problemas:
        raise ValueError("Avaliação incompleta:\n" + "\n".join(f"- {p}" for p in problemas))

    resultados = [
        Resultado(candidato, amostra, {criterio: avaliacao[amostra][criterio] for criterio in CRITERIOS})
        for amostra, candidato in gabarito.items()
    ]
    return sorted(resultados, key=lambda resultado: resultado.media, reverse=True)


def formatar_relatorio(resultados: Sequence[Resultado]) -> str:
    cabecalho = ["candidato", "amostra", *CRITERIOS, "media"]
    linhas = [
        [r.candidato, r.amostra, *(str(r.notas[c]) for c in CRITERIOS), f"{r.media:.2f}"]
        for r in resultados
    ]
    larguras = [max(len(celula) for celula in coluna) for coluna in zip(cabecalho, *linhas)]
    tabela = [
        "  ".join(celula.ljust(largura) for celula, largura in zip(linha, larguras))
        for linha in [cabecalho, *linhas]
    ]
    vencedores = [f"Melhor em {criterio}: {_melhores_em(criterio, resultados)}" for criterio in CRITERIOS]
    return "\n".join([*tabela, "", *vencedores])


def _criar_fala(item: Mapping[str, str], personas: Mapping[str, Persona]) -> Fala:
    persona_id = item["persona"]
    if persona_id not in personas:
        raise KeyError(f"Persona '{persona_id}' não existe em curriculum/personas.")
    return Fala(persona=personas[persona_id], texto=item["texto"].strip(), estilo=item.get("estilo"))


def _validar_nomes_unicos(provedores: Sequence[TtsProvider]) -> None:
    nomes = [provedor.nome for provedor in provedores]
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"Candidatos repetidos: {nomes}")


def _sintetizar(provedor: TtsProvider, falas: Sequence[Fala]) -> Audio:
    try:
        return provedor.sintetizar(falas)
    except Exception as erro:
        raise RuntimeError(
            f"Falha ao sintetizar com {provedor.nome}: {erro}\n"
            f"Nenhuma amostra foi gerada. Corrija o erro ou remova o candidato com --candidatos."
        ) from erro


def _escrever_avaliacao(arquivo: Path, gabarito: Mapping[str, str]) -> None:
    modelo_de_notas = {criterio: None for criterio in CRITERIOS} | {"observacoes": ""}
    conteudo = {
        "escala": f"{NOTA_MINIMA} (ruim) a {NOTA_MAXIMA} (ótimo)",
        "criterios": CRITERIOS,
        "amostras": {amostra: dict(modelo_de_notas) for amostra in gabarito},
    }
    arquivo.write_text(yaml.safe_dump(conteudo, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _problemas_da_avaliacao(amostra: str, notas: Mapping[str, object]) -> list[str]:
    return [
        f"amostra {amostra}, {criterio}: nota {notas.get(criterio)!r} fora da escala {NOTA_MINIMA}-{NOTA_MAXIMA}"
        for criterio in CRITERIOS
        if not _nota_valida(notas.get(criterio))
    ]


def _nota_valida(nota: object) -> bool:
    return isinstance(nota, int) and not isinstance(nota, bool) and NOTA_MINIMA <= nota <= NOTA_MAXIMA


def _melhores_em(criterio: str, resultados: Sequence[Resultado]) -> str:
    maior = max(resultado.notas[criterio] for resultado in resultados)
    return " e ".join(r.candidato for r in resultados if r.notas[criterio] == maior)


def _criar_provedor(nome: str, diretorio_vozes_piper: Path) -> TtsProvider:
    if nome.startswith("gemini-"):
        from podcast.tts.gemini import GeminiTts

        return GeminiTts(modelo=nome)
    if nome == "kokoro":
        from podcast.tts.kokoro import KokoroTts

        return KokoroTts()
    if nome == "piper":
        from podcast.tts.piper import PiperTts

        return PiperTts(diretorio_vozes_piper)
    raise ValueError(f"Candidato desconhecido: {nome}")


def _ler_bitrate(arquivo_config: Path) -> int:
    config = yaml.safe_load(arquivo_config.read_text(encoding="utf-8"))
    return config["audio"]["bitrate_kbps"]


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teste_vozes", description="Teste cego de provedores de voz.")
    parser.add_argument("--saida", type=Path, default=Path("experimentos/teste-vozes/saida"))
    comandos = parser.add_subparsers(dest="comando", required=True)

    gerar_cmd = comandos.add_parser("gerar", help="Gera as amostras anônimas e a ficha de avaliação.")
    gerar_cmd.add_argument("--candidatos", nargs="+", choices=CANDIDATOS, default=list(CANDIDATOS))
    gerar_cmd.add_argument("--trecho", type=Path, default=Path("experimentos/teste-vozes/trecho.yaml"))
    gerar_cmd.add_argument("--personas", type=Path, default=Path("curriculum/personas"))
    gerar_cmd.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))
    gerar_cmd.add_argument("--vozes-piper", type=Path, default=Path("experimentos/teste-vozes/vozes-piper"))

    comandos.add_parser("revelar", help="Valida a avaliação e revela quem é quem.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _criar_parser().parse_args(argv)
    try:
        if args.comando == "gerar":
            falas = carregar_trecho(args.trecho, carregar_personas(args.personas))
            provedores = [_criar_provedor(nome, args.vozes_piper) for nome in args.candidatos]
            gerar(falas, provedores, args.saida, _ler_bitrate(args.config))
            print(f"Amostras em {args.saida / PASTA_AMOSTRAS}. Preencha {args.saida / ARQUIVO_AVALIACAO}.")
        else:
            print(formatar_relatorio(revelar(args.saida)))
    except (FileExistsError, FileNotFoundError, KeyError, ValueError, RuntimeError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
