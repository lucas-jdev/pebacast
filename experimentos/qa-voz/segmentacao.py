"""Spike #27: separa os turnos de um episódio publicado guiando-se pelo roteiro, sem modelo de fala.

1. Recalcula os turnos (persona, caracteres, bloco) com o mesmo código da publicação:
   `falas_do_episodio` (roteiro + dicionário de pronúncia) e `agrupar_em_blocos`.
2. Acha as pausas com um VAD de energia em numpy.
3. Uma programação dinâmica escolhe K-1 pausas para dividir a fala em K turnos, com a duração
   esperada de cada turno proporcional aos caracteres (mais uma folga fixa por turno).
4. Mede só o miolo de cada turno: corta as bordas e descarta os curtos e o primeiro (sob a vinheta).

Código de spike: não é mergeado no main (#27).
"""

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

TAXA = 16_000
# Abertura de 9 s com a primeira fala entrando 1,5 s antes do fim; encerramento de 11 s depois da
# última fala (config/pipeline.yaml, iguais em todos os episódios publicados).
INICIO_DA_FALA_S = 7.5
ENCERRAMENTO_S = 11.0

QUADRO_S = 0.010
JANELA_S = 0.025
PAUSA_MIN_S = 0.12
PESO_DA_PAUSA = 0.2  # calibrado em sw-002 e in-001 (platô de 0,15 a 0,3)
PESO_DA_VOZ = 0.1  # calibrado nos 7 episódios com referência: de 0,05 a 1,0 dá 99,4% a 100%
FOLGA_CARACTERES = 12  # turnos curtos ("Isso!") demoram mais que o proporcional aos caracteres
BORDA_DO_MIOLO = 0.2
MIOLO_MIN_S = 2.0


@dataclass
class Turno:
    indice: int
    persona: str
    bloco: int
    caracteres: int
    inicio: float = 0.0
    fim: float = 0.0
    miolo: tuple[float, float] | None = None


def decodificar(mp3: Path) -> np.ndarray:
    saida = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(TAXA), "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(saida, dtype=np.float32).copy()


def turnos_do_roteiro(raiz: Path, episodio: str) -> list[Turno]:
    import sys

    sys.path.insert(0, str(raiz / "src"))
    from podcast.personas import carregar_personas
    from podcast.publicacao import falas_do_episodio
    from podcast.roteiro import Projeto
    from podcast.tts.gemini import agrupar_em_blocos

    projeto = Projeto(raiz)
    config = projeto.config()
    personas = carregar_personas(raiz / "curriculum" / "personas")
    falas = falas_do_episodio(projeto.episodios / episodio, personas, config["tts"])
    turnos, indice = [], 0
    for numero, bloco in enumerate(agrupar_em_blocos(falas, config["tts"]["max_caracteres_por_bloco"])):
        for fala in bloco:
            turnos.append(Turno(indice, fala.persona.id, numero, len(fala.texto)))
            indice += 1
    return turnos


def energia_db(x: np.ndarray) -> np.ndarray:
    passo, janela = int(QUADRO_S * TAXA), int(JANELA_S * TAXA)
    quadros = np.lib.stride_tricks.sliding_window_view(x, janela)[::passo]
    return 10 * np.log10(np.mean(quadros.astype(np.float64) ** 2, axis=1) + 1e-12)


def pausas(db: np.ndarray, inicio_s: float) -> list[tuple[float, float]]:
    """Trechos silenciosos de pelo menos PAUSA_MIN_S, em segundos absolutos."""
    limiar = np.percentile(db, 95) - 35
    silencio = db < limiar
    trechos, comeco = [], None
    for i, s in enumerate(np.append(silencio, False)):
        if s and comeco is None:
            comeco = i
        elif not s and comeco is not None:
            if (i - comeco) * QUADRO_S >= PAUSA_MIN_S:
                trechos.append((inicio_s + comeco * QUADRO_S, inicio_s + i * QUADRO_S))
            comeco = None
    return trechos


def _programacao_dinamica(esperado, log_dur, valido, bonus, k, n, voz=None, personas=None) -> list[int]:
    """`voz[p]` (opcional): custo acumulado, ponto a ponto, de pôr a fala até ali no turno da persona p."""
    custo = np.full(n, np.inf)
    custo[0] = 0.0
    anterior = np.zeros((k, n), dtype=np.int32)
    for t in range(k):
        termo = (log_dur - np.log(esperado[t])) ** 2
        if voz is not None:
            acumulado = voz[personas[t]]
            termo = termo + (acumulado[None, :] - acumulado[:, None])
        total = np.where(valido, custo[:, None] + termo, np.inf) - bonus[None, :]
        anterior[t] = np.argmin(total, axis=0)
        custo = total[anterior[t], np.arange(n)]
    cortes, j = [n - 1], n - 1
    for t in range(k - 1, -1, -1):
        j = int(anterior[t, j])
        cortes.append(j)
    cortes.reverse()
    return cortes


def _custo_de_voz(x, pontos, turnos, cortes, embedder, peso_voz) -> dict[str, np.ndarray]:
    """Quanto cada trecho entre pausas parece o Davi ou a convidada, pelos centróides da passada anterior.

    Se o TTS emendou dois turnos sem pausa, a duração sozinha erra a fronteira e o erro se propaga
    (si-001). A voz de cada trecho ancora a divisão. Quando as duas vozes se parecem, a diferença
    some e a segmentação volta a depender só da duração, sem esconder o defeito: os miolos misturados
    deixam os centróides ainda mais parecidos.
    """
    personas = sorted({t.persona for t in turnos})
    embs = {p: [] for p in personas}
    for t, turno in enumerate(turnos):
        a, b = pontos[cortes[t]], pontos[cortes[t + 1]]
        borda = (b - a) * BORDA_DO_MIOLO
        if t > 0 and b - a - 2 * borda >= MIOLO_MIN_S:
            embs[turno.persona].append(embedder(x[int((a + borda) * TAXA):int((b - borda) * TAXA)]))
    centroides = {p: _norm(np.mean(v, axis=0)) for p, v in embs.items() if v}
    if len(centroides) < 2:
        return None
    nota = np.zeros(len(pontos) - 1)  # por trecho: cos(Davi-ish) − cos(convidada), vezes a duração
    outra = next(p for p in personas if p != "davi")
    for i in range(len(pontos) - 1):
        a, b = pontos[i], pontos[i + 1]
        if b - a < 0.6:
            continue
        meio, metade = (a + b) / 2, min((b - a) / 2, 3.0)
        e = embedder(x[int((meio - metade) * TAXA):int((meio + metade) * TAXA)])
        nota[i] = (e @ centroides["davi"] - e @ centroides[outra]) * (b - a)
    # Pôr um trecho com cara de Davi no turno da convidada custa; no turno do Davi, rende.
    acumulado = np.concatenate([[0.0], np.cumsum(nota)])
    return {"davi": -peso_voz * acumulado, outra: peso_voz * acumulado}


def _norm(v):
    return v / np.linalg.norm(v)


def segmentar(x: np.ndarray, turnos: list[Turno], folga: float = FOLGA_CARACTERES, peso_pausa: float = PESO_DA_PAUSA,
              passadas: int = 2, embedder=None, peso_voz: float = PESO_DA_VOZ) -> tuple[list[Turno], dict]:
    duracao = len(x) / TAXA
    t0, t1 = INICIO_DA_FALA_S, duracao - ENCERRAMENTO_S
    db = energia_db(x[int(t0 * TAXA):int(t1 * TAXA)])
    candidatas = pausas(db, t0)
    # Pontos de corte possíveis: o início, o meio de cada pausa e o fim.
    pontos = np.array([t0] + [(a + b) / 2 for a, b in candidatas] + [t1])
    largura = np.array([1.0] + [b - a for a, b in candidatas] + [1.0])

    pesos = np.array([t.caracteres + folga for t in turnos], dtype=float)
    esperado = (t1 - t0) * pesos / pesos.sum()
    k, n = len(turnos), len(pontos)
    dur = pontos[None, :] - pontos[:, None]  # dur[i, j]: do ponto i ao j
    valido = dur > 0.2
    log_dur = np.log(np.where(valido, dur, 1.0))
    # Pausa longa é corte mais provável: bônus pela largura da pausa no ponto de chegada.
    bonus = peso_pausa * np.log(largura / PAUSA_MIN_S)

    for passada in range(passadas):
        cortes = _programacao_dinamica(esperado, log_dur, valido, bonus, k, n)
        if passada == passadas - 1:
            break
        # Cada bloco é uma chamada ao TTS, e a velocidade muda de uma para outra (e de voz para voz):
        # reestima a duração esperada com a velocidade por bloco e por persona da passada anterior.
        obtido = np.diff(pontos[cortes])
        blocos = np.array([t.bloco for t in turnos])
        personas = np.array([t.persona for t in turnos])
        fator = np.ones(k)
        for grupo in (blocos, personas):
            for valor in np.unique(grupo):
                m = grupo == valor
                fator[m] *= obtido[m].sum() / (esperado[m] * fator[m]).sum()
        esperado = esperado * fator
        esperado *= (t1 - t0) / esperado.sum()
    if embedder is not None:
        voz = _custo_de_voz(x, pontos, turnos, cortes, embedder, peso_voz)
        if voz is not None:
            personas = [t.persona for t in turnos]
            cortes = _programacao_dinamica(esperado, log_dur, valido, bonus, k, n, voz, personas)
    for t, turno in enumerate(turnos):
        turno.inicio, turno.fim = float(pontos[cortes[t]]), float(pontos[cortes[t + 1]])
        borda = (turno.fim - turno.inicio) * BORDA_DO_MIOLO
        a, b = turno.inicio + borda, turno.fim - borda
        turno.miolo = (a, b) if t > 0 and b - a >= MIOLO_MIN_S else None
    return turnos, {"pausas": len(candidatas), "inicio": t0, "fim": t1, "duracao": duracao}


def salvar(turnos: list[Turno], info: dict, arquivo: Path) -> None:
    arquivo.write_text(json.dumps({"info": info, "turnos": [asdict(t) for t in turnos]}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("raiz", type=Path)
    p.add_argument("audio", type=Path)
    p.add_argument("saida", type=Path)
    p.add_argument("episodios", nargs="+")
    a = p.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    for ep in a.episodios:
        x = decodificar(a.audio / f"pebacast-{ep}.mp3")
        turnos, info = segmentar(x, turnos_do_roteiro(a.raiz, ep))
        salvar(turnos, info, a.saida / f"{ep}.segmentos.json")
        print(ep, info, sum(t.miolo is not None for t in turnos), "miolos de", len(turnos))
