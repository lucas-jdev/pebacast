"""Validação dos artefatos que a rotina do roteirista grava em episodios/<id>/.

É o portão do roteiro: o GitHub Actions só sintetiza um episódio cuja pasta passa por aqui
sem nenhum problema. A validação não confia no que a rotina diz de si mesma; ela confere
os arquivos.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROTEIRO = "roteiro.json"
NOTICIA = "noticia.json"
PASTA_REVISOES = "revisoes"
PUBLICACAO = "publicacao.json"

VEREDITOS = frozenset({"correta", "incorreta", "imprecisa", "nao_verificavel"})
TIPOS_DE_CONTEXTO = frozenset({"noticia", "hipotetico"})
AVISO_IA = re.compile(r"\bIA\b|intelig[êe]ncia artificial", re.IGNORECASE)
PALAVRA = re.compile(r"\w+")
# O apresentador apresenta o podcast e a pessoa convidada logo no começo, antes de entrar no tema.
FALAS_DA_APRESENTACAO = 3


@dataclass(frozen=True)
class Regras:
    episodio_id: str
    nome_podcast: str
    apresentador: str
    expert: str
    nome_expert: str
    personas_permitidas: frozenset[str]
    palavras_min: int
    palavras_max: int
    max_ciclos: int
    vereditos_reprovam: frozenset[str]
    nota_minima_relevancia: float
    urls_ja_usadas: frozenset[str]

    @property
    def max_revisoes(self) -> int:
        # Cada ciclo é uma revisão seguida de correção; a última correção precisa de uma revisão final.
        return self.max_ciclos + 1


def hash_do_roteiro(roteiro: Any) -> str:
    """Hash do conteúdo do roteiro, independente de formatação e quebras de linha."""
    canonico = json.dumps(roteiro, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def contar_palavras(roteiro: dict[str, Any]) -> int:
    return sum(len(PALAVRA.findall(fala.get("texto", ""))) for fala in roteiro.get("falas", []))


def roteiro_aprovado(pasta: Path, regras: Regras) -> bool:
    return (pasta / ROTEIRO).exists() and not validar_episodio(pasta, regras)


def validar_episodio(pasta: Path, regras: Regras) -> list[str]:
    roteiro, problemas = _ler_json(pasta / ROTEIRO)
    if roteiro is None:
        return problemas

    problemas += _validar_roteiro(roteiro, regras)

    noticia, problemas_noticia = _ler_json(pasta / NOTICIA)
    problemas += problemas_noticia
    if noticia is not None:
        problemas += _validar_noticia(noticia, regras)

    problemas += _validar_revisoes(pasta / PASTA_REVISOES, roteiro, regras)
    return problemas


def _ler_json(arquivo: Path) -> tuple[Any, list[str]]:
    if not arquivo.exists():
        return None, [f"{arquivo.name}: arquivo não encontrado"]
    try:
        return json.loads(arquivo.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as erro:
        return None, [f"{arquivo.name}: JSON inválido ({erro})"]


def _validar_roteiro(roteiro: Any, regras: Regras) -> list[str]:
    if not isinstance(roteiro, dict):
        return [f"{ROTEIRO}: precisa ser um objeto"]

    problemas = []
    if roteiro.get("episodio") != regras.episodio_id:
        problemas.append(f"{ROTEIRO}: episodio {roteiro.get('episodio')!r}, esperado {regras.episodio_id!r}")

    falas = roteiro.get("falas")
    if not isinstance(falas, list) or not falas:
        return problemas + [f"{ROTEIRO}: falas precisa ser uma lista não vazia"]

    for indice, fala in enumerate(falas):
        problemas += _validar_fala(indice, fala, regras)

    primeira = falas[0] if isinstance(falas[0], dict) else {}
    if primeira.get("persona") != regras.apresentador:
        problemas.append(f"{ROTEIRO}: a primeira fala precisa ser do apresentador ({regras.apresentador})")
    if not AVISO_IA.search(str(primeira.get("texto", ""))):
        problemas.append(f"{ROTEIRO}: a primeira fala precisa trazer o aviso de conteúdo gerado por IA")
    if not _menciona(primeira.get("texto"), regras.nome_podcast):
        problemas.append(f"{ROTEIRO}: a primeira fala precisa apresentar o {regras.nome_podcast}")
    problemas += _validar_apresentacao_do_expert(falas[:FALAS_DA_APRESENTACAO], regras)

    if not _texto_preenchido(roteiro.get("desafio")):
        problemas.append(f"{ROTEIRO}: desafio vazio")

    fontes = roteiro.get("fontes")
    if not isinstance(fontes, list) or not fontes or not all(_texto_preenchido(f) for f in fontes):
        problemas.append(f"{ROTEIRO}: fontes precisa ser uma lista não vazia de textos")

    if not problemas:
        palavras = contar_palavras(roteiro)
        if not regras.palavras_min <= palavras <= regras.palavras_max:
            problemas.append(
                f"{ROTEIRO}: {palavras} palavras, fora da faixa {regras.palavras_min}-{regras.palavras_max}"
            )
    return problemas


def _validar_apresentacao_do_expert(inicio: list[Any], regras: Regras) -> list[str]:
    falas = [fala for fala in inicio if isinstance(fala, dict)]
    problemas = []
    apresentou = any(
        fala.get("persona") == regras.apresentador and _menciona(fala.get("texto"), regras.nome_expert)
        for fala in falas
    )
    if not apresentou:
        problemas.append(
            f"{ROTEIRO}: o apresentador precisa apresentar {regras.nome_expert} pelo nome "
            f"nas {FALAS_DA_APRESENTACAO} primeiras falas"
        )
    if not any(fala.get("persona") == regras.expert for fala in falas):
        problemas.append(f"{ROTEIRO}: {regras.nome_expert} precisa falar nas {FALAS_DA_APRESENTACAO} primeiras falas")
    return problemas


def _menciona(texto: Any, nome: str) -> bool:
    return isinstance(texto, str) and re.search(rf"\b{re.escape(nome)}\b", texto, re.IGNORECASE) is not None


def _validar_fala(indice: int, fala: Any, regras: Regras) -> list[str]:
    if not isinstance(fala, dict):
        return [f"{ROTEIRO}: fala {indice} precisa ser um objeto"]
    problemas = []
    if fala.get("persona") not in regras.personas_permitidas:
        problemas.append(f"{ROTEIRO}: fala {indice} com persona {fala.get('persona')!r} fora do episódio")
    if not _texto_preenchido(fala.get("texto")):
        problemas.append(f"{ROTEIRO}: fala {indice} sem texto")
    if "estilo" in fala and not _texto_preenchido(fala["estilo"]):
        problemas.append(f"{ROTEIRO}: fala {indice} com estilo vazio")
    return problemas


def _validar_noticia(noticia: Any, regras: Regras) -> list[str]:
    if not isinstance(noticia, dict) or noticia.get("tipo") not in TIPOS_DE_CONTEXTO:
        return [f"{NOTICIA}: tipo precisa ser um de {sorted(TIPOS_DE_CONTEXTO)}"]

    if noticia["tipo"] == "hipotetico":
        return [] if _texto_preenchido(noticia.get("cenario")) else [f"{NOTICIA}: cenário hipotético vazio"]

    problemas = [
        f"{NOTICIA}: campo {campo} vazio"
        for campo in ("titulo", "url", "fonte", "data", "justificativa")
        if not _texto_preenchido(noticia.get(campo))
    ]
    nota = noticia.get("nota_relevancia")
    if not isinstance(nota, int | float) or isinstance(nota, bool):
        problemas.append(f"{NOTICIA}: nota_relevancia precisa ser um número")
    elif nota < regras.nota_minima_relevancia:
        problemas.append(f"{NOTICIA}: nota de relevância {nota} abaixo do mínimo {regras.nota_minima_relevancia}")
    if noticia.get("url") in regras.urls_ja_usadas:
        problemas.append(f"{NOTICIA}: notícia já usada em outro episódio ({noticia['url']})")
    return problemas


def _validar_revisoes(pasta: Path, roteiro: Any, regras: Regras) -> list[str]:
    arquivos = sorted(pasta.glob("*.json"), key=lambda a: (len(a.stem), a.stem)) if pasta.is_dir() else []
    if not arquivos:
        return [f"{PASTA_REVISOES}/: nenhuma revisão encontrada"]

    esperados = [f"{numero}.json" for numero in range(1, len(arquivos) + 1)]
    if [arquivo.name for arquivo in arquivos] != esperados:
        return [f"{PASTA_REVISOES}/: revisões precisam ser numeradas em sequência (1.json, 2.json, ...)"]

    problemas = []
    if len(arquivos) > regras.max_revisoes:
        problemas.append(
            f"{PASTA_REVISOES}/: {len(arquivos)} revisões, acima do limite de {regras.max_revisoes} "
            f"({regras.max_ciclos} ciclos de correção)"
        )

    for arquivo in arquivos:
        revisao, problemas_leitura = _ler_json(arquivo)
        problemas += [f"{PASTA_REVISOES}/{p}" for p in problemas_leitura]
        if revisao is not None:
            problemas += _validar_revisao(arquivo.name, revisao, regras)

    ultima, _ = _ler_json(arquivos[-1])
    if isinstance(ultima, dict):
        problemas += _validar_revisao_final(arquivos[-1].name, ultima, roteiro)
    return problemas


def _validar_revisao(nome: str, revisao: Any, regras: Regras) -> list[str]:
    prefixo = f"{PASTA_REVISOES}/{nome}"
    if not isinstance(revisao, dict):
        return [f"{prefixo}: precisa ser um objeto"]

    afirmacoes = revisao.get("afirmacoes")
    if not isinstance(revisao.get("aprovado"), bool) or not isinstance(afirmacoes, list):
        return [f"{prefixo}: precisa ter aprovado (booleano) e afirmacoes (lista)"]

    problemas = []
    for indice, afirmacao in enumerate(afirmacoes):
        if not isinstance(afirmacao, dict) or afirmacao.get("veredito") not in VEREDITOS:
            problemas.append(f"{prefixo}: afirmação {indice} com veredito inválido")

    reprovadas = [a for a in afirmacoes if isinstance(a, dict) and a.get("veredito") in regras.vereditos_reprovam]
    if revisao["aprovado"] and reprovadas:
        problemas.append(f"{prefixo}: marcada como aprovada, mas tem {len(reprovadas)} afirmação(ões) reprovada(s)")
    return problemas


def _validar_revisao_final(nome: str, revisao: dict[str, Any], roteiro: Any) -> list[str]:
    prefixo = f"{PASTA_REVISOES}/{nome}"
    problemas = []
    if revisao.get("aprovado") is not True:
        problemas.append(f"{prefixo}: a última revisão não aprovou o roteiro")
    if not revisao.get("afirmacoes"):
        problemas.append(f"{prefixo}: a última revisão não verificou nenhuma afirmação")
    if revisao.get("roteiro_sha256") != hash_do_roteiro(roteiro):
        problemas.append(f"{prefixo}: o roteiro mudou depois da última revisão (roteiro_sha256 não confere)")

    falas = roteiro.get("falas", []) if isinstance(roteiro, dict) else []
    for indice, afirmacao in enumerate(revisao.get("afirmacoes") or []):
        fala = afirmacao.get("fala") if isinstance(afirmacao, dict) else None
        if not isinstance(fala, int) or isinstance(fala, bool) or not 0 <= fala < len(falas):
            problemas.append(f"{prefixo}: afirmação {indice} aponta para uma fala inexistente ({fala!r})")
    return problemas


def _texto_preenchido(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())
