"""Confere a segmentação contra a referência do Vosk.

Um miolo está certo quando a maior parte dele cai dentro de turnos da mesma persona, segundo a
referência. O intervalo de referência de um turno vai da primeira à última palavra reconhecida;
entre dois turnos, o espaço sem palavra é dividido ao meio entre eles.
"""

import json
import sys
from pathlib import Path

import numpy as np


def intervalos_de_referencia(ref: list[dict], fim: float) -> list[tuple[float, float, str, int]]:
    com_tempo = [t for t in ref if t["inicio"] is not None]
    saida = []
    for i, t in enumerate(com_tempo):
        a = t["inicio"] if i == 0 else (com_tempo[i - 1]["fim"] + t["inicio"]) / 2
        b = fim if i == len(com_tempo) - 1 else (t["fim"] + com_tempo[i + 1]["inicio"]) / 2
        saida.append((a, b, t["persona"], t["indice"]))
    return saida


def avaliar(seg: dict, ref: list[dict]) -> dict:
    turnos = seg["turnos"]
    intervalos = intervalos_de_referencia(ref, seg["info"]["fim"])
    certos = errados = mesmo_turno = 0
    exemplos = []
    for t in turnos:
        if not t["miolo"]:
            continue
        a, b = t["miolo"]
        por_persona: dict[str, float] = {}
        por_turno: dict[int, float] = {}
        for ra, rb, persona, indice in intervalos:
            sobra = max(0.0, min(b, rb) - max(a, ra))
            if sobra:
                por_persona[persona] = por_persona.get(persona, 0) + sobra
                por_turno[indice] = por_turno.get(indice, 0) + sobra
        dono = max(por_persona, key=por_persona.get)
        if dono == t["persona"] and por_persona[dono] >= 0.5 * (b - a):
            certos += 1
        else:
            errados += 1
            exemplos.append((t["indice"], t["persona"], dono, round(a, 1), round(b, 1)))
        mesmo_turno += max(por_turno, key=por_turno.get) == t["indice"]
    # Erro de fronteira: início previsto de cada turno contra o início da primeira palavra reconhecida.
    inicio_ref = {t["indice"]: t["inicio"] for t in ref if t["inicio"] is not None and t["casadas"] >= 2}
    erros = np.array([abs(t["inicio"] - inicio_ref[t["indice"]]) for t in turnos[1:] if t["indice"] in inicio_ref])
    return {
        "miolos": certos + errados, "persona_certa": certos, "taxa": certos / (certos + errados),
        "no_turno_certo": mesmo_turno,
        "fronteiras": len(erros),
        "erro_mediano_s": float(np.median(erros)), "erro_p90_s": float(np.percentile(erros, 90)),
        "fronteiras_ate_1s": float(np.mean(erros <= 1.0)),
        "errados": exemplos,
    }


if __name__ == "__main__":
    saida = Path(sys.argv[1])
    for ep in sys.argv[2:]:
        seg = json.loads((saida / f"{ep}.segmentos.json").read_text(encoding="utf-8"))
        ref = json.loads((saida / f"{ep}.referencia.json").read_text(encoding="utf-8"))
        r = avaliar(seg, ref)
        print(ep, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k != "errados"})
        for e in r["errados"]:
            print("   errado:", e)
