"""Analisa os embeddings dos episódios bons e dos defeitos sintéticos; propõe os limites.

Medidas (cosseno entre vetores normalizados):
- separação: centróide do Davi contra o da convidada, no episódio;
- estabilidade interna: centróide da persona num bloco contra o centróide dela no resto do episódio;
- estabilidade de referência: centróide da persona no bloco contra a impressão de voz da persona,
  a média dos centróides dela nos OUTROS episódios (deixa o episódio de fora);
- defeito 1 (timbre trocado num bloco): os miolos de uma persona num bloco trocados por miolos de
  outra voz do Gemini, tirados de outro episódio (o embedding de um miolo não depende dos vizinhos);
- defeito 2 (vozes confundíveis): os miolos da convidada trocados por miolos do Puck (a voz do Davi)
  de outro episódio, ou da voz mais parecida com o Puck.
"""

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

MIN_MIOLOS_NO_BLOCO = 2
RNG = np.random.default_rng(27)


def norm(v):
    return v / np.linalg.norm(v)


def centroide(e):
    return norm(e.mean(axis=0))


def carregar(pasta: Path, modelo: str) -> dict:
    eps = {}
    for arq in sorted(pasta.glob("*.medidas.npz")):
        d = np.load(arq)
        eps[arq.name.split(".")[0]] = {"persona": d["persona"], "bloco": d["bloco"], "f0": d["f0"],
                                       "emb": d[f"emb_{modelo}"]}
    return eps


def convidada(ep):
    return next(p for p in np.unique(ep["persona"]) if p != "davi")


def referencias(eps, deixar_de_fora: str) -> dict[str, np.ndarray]:
    """Impressão de voz de cada persona com os episódios que não são `deixar_de_fora`."""
    por_persona: dict[str, list] = {}
    for nome, ep in eps.items():
        if nome == deixar_de_fora:
            continue
        for p in np.unique(ep["persona"]):
            por_persona.setdefault(p, []).append(centroide(ep["emb"][ep["persona"] == p]))
    return {p: norm(np.mean(v, axis=0)) for p, v in por_persona.items()}


def pontuar_blocos(persona, bloco, emb, refs, alvo=None):
    """(interno, referência) por bloco da persona com miolos suficientes."""
    saida = []
    pessoas = [alvo] if alvo else np.unique(persona)
    for p in pessoas:
        for b in np.unique(bloco[persona == p]):
            m = (persona == p) & (bloco == b)
            resto = (persona == p) & (bloco != b)
            if m.sum() < MIN_MIOLOS_NO_BLOCO or resto.sum() < MIN_MIOLOS_NO_BLOCO:
                continue
            c = centroide(emb[m])
            saida.append((p, int(b), float(c @ centroide(emb[resto])), float(c @ refs[p]) if p in refs else np.nan))
    return saida


def banco_de_vozes(eps):
    """Miolos de cada persona por episódio, para emendar no lugar de outra voz."""
    return {(nome, p): ep["emb"][ep["persona"] == p] for nome, ep in eps.items() for p in np.unique(ep["persona"])}


def resumo(valores):
    v = np.array([x for x in valores if not np.isnan(x)])
    return {"n": int(len(v)), "min": float(v.min()), "p5": float(np.percentile(v, 5)), "media": float(v.mean()),
            "dp": float(v.std()), "max": float(v.max())}


def analisar(eps):
    r = {"episodios": sorted(eps)}
    # 1. Separação e acerto por miolo.
    sep, acerto, f0 = {}, [], {}
    for nome, ep in eps.items():
        conv = convidada(ep)
        cd, cc = centroide(ep["emb"][ep["persona"] == "davi"]), centroide(ep["emb"][ep["persona"] == conv])
        sep[nome] = {"convidada": conv, "cos_davi_convidada": float(cd @ cc)}
        for i, (v, p) in enumerate(zip(ep["emb"], ep["persona"])):
            outros = np.arange(len(ep["emb"])) != i
            c = {q: centroide(ep["emb"][outros & (ep["persona"] == q)]) for q in ("davi", conv)}
            acerto.append(max(c, key=lambda q: c[q] @ v) == p)
        for p in np.unique(ep["persona"]):
            f0.setdefault(p, []).extend(ep["f0"][(ep["persona"] == p) & (ep["f0"] > 0)].tolist())
    r["separacao"] = sep
    r["separacao_resumo"] = resumo([s["cos_davi_convidada"] for s in sep.values()])
    r["acerto_por_miolo"] = float(np.mean(acerto))
    r["f0_por_persona"] = {p: {"mediana": float(np.median(v)), "p10": float(np.percentile(v, 10)),
                               "p90": float(np.percentile(v, 90)), "miolos": len(v)} for p, v in f0.items()}

    # 2. Estabilidade nos episódios bons.
    internos, de_referencia = [], []
    for nome, ep in eps.items():
        for _, _, i, ref in pontuar_blocos(ep["persona"], ep["bloco"], ep["emb"], referencias(eps, nome)):
            internos.append(i)
            de_referencia.append(ref)
    r["bloco_interno"] = resumo(internos)
    r["bloco_referencia"] = resumo(de_referencia)

    # Impressão de voz entre episódios (mesma persona, mesma voz do Gemini).
    entre = {}
    for p in ("davi", "helena", "beatriz", "rafael", "jorge"):
        cs = [centroide(ep["emb"][ep["persona"] == p]) for ep in eps.values() if p in ep["persona"]]
        if len(cs) > 1:
            entre[p] = resumo([float(a @ b) for a, b in combinations(cs, 2)])
    r["mesma_persona_entre_episodios"] = entre

    # Proximidade entre as vozes (centróides globais), para escolher o defeito mais difícil.
    globais = {}
    for ep in eps.values():
        for p in np.unique(ep["persona"]):
            globais.setdefault(p, []).append(centroide(ep["emb"][ep["persona"] == p]))
    globais = {p: norm(np.mean(v, axis=0)) for p, v in globais.items()}
    r["proximidade_das_vozes"] = {f"{a}~{b}": float(globais[a] @ globais[b]) for a, b in combinations(sorted(globais), 2)}
    return r, globais


def limites(r):
    interno, ref, sep = r["bloco_interno"], r["bloco_referencia"], r["separacao_resumo"]
    return {
        # Abaixo do menor valor visto nos episódios bons, com folga de 3 desvios-padrão da média.
        "timbre_bloco_min": round(min(interno["min"] - 0.05, interno["media"] - 3 * interno["dp"]), 2),
        "timbre_referencia_min": round(min(ref["min"] - 0.05, ref["media"] - 3 * ref["dp"]), 2),
        "vozes_confundiveis_max": round(max(sep["max"] + 0.10, sep["media"] + 3 * sep["dp"]), 2),
    }


def defeitos(eps, globais, lim):
    banco = banco_de_vozes(eps)
    vozes = sorted(globais)
    resultado = {"timbre_trocado": {}, "vozes_confundiveis": {}}
    # Defeito 1: cada persona, cada bloco com miolos suficientes, trocado por cada outra voz.
    for substituta in vozes:
        detectados = total = 0

        for nome, ep in eps.items():
            refs = referencias(eps, nome)
            fontes = [e for (n, p), e in banco.items() if p == substituta and n != nome]
            if not fontes:
                continue
            fonte = np.concatenate(fontes)
            for p in np.unique(ep["persona"]):
                if p == substituta:
                    continue
                for b in np.unique(ep["bloco"][ep["persona"] == p]):
                    m = (ep["persona"] == p) & (ep["bloco"] == b)
                    if m.sum() < MIN_MIOLOS_NO_BLOCO or ((ep["persona"] == p) & ~m).sum() < MIN_MIOLOS_NO_BLOCO:
                        continue
                    emb = ep["emb"].copy()
                    emb[m] = fonte[RNG.choice(len(fonte), m.sum(), replace=False)]
                    [(_, _, interno, ref)] = [x for x in pontuar_blocos(ep["persona"], ep["bloco"], emb, refs, p)
                                              if x[1] == b]
                    detectados += interno < lim["timbre_bloco_min"] or ref < lim["timbre_referencia_min"]
                    total += 1
        resultado["timbre_trocado"][substituta] = {"casos": total, "detectados": detectados,
                                                   "taxa": detectados / total if total else None}
    # Defeito 2: a convidada trocada pelo Puck de outro episódio ou pela voz mais parecida com ele.
    mais_parecida = max((v for v in vozes if v != "davi"), key=lambda v: globais[v] @ globais["davi"])
    for substituta in ("davi", mais_parecida):
        valores = []
        for nome, ep in eps.items():
            conv = convidada(ep)
            if conv == substituta:
                continue
            fonte = np.concatenate([e for (n, p), e in banco.items() if p == substituta and n != nome])
            m = ep["persona"] == conv
            emb = fonte[RNG.choice(len(fonte), m.sum(), replace=len(fonte) < m.sum())]
            valores.append(float(centroide(ep["emb"][ep["persona"] == "davi"]) @ centroide(emb)))
        resultado["vozes_confundiveis"][f"convidada_trocada_por_{substituta}"] = {
            **resumo(valores), "detectados": int(sum(v > lim["vozes_confundiveis_max"] for v in valores)),
            "casos": len(valores)}
    return resultado


if __name__ == "__main__":
    pasta = Path(sys.argv[1])
    final = {}
    for modelo in sys.argv[2:]:
        eps = carregar(pasta, modelo)
        r, globais = analisar(eps)
        lim = limites(r)
        final[modelo] = {**r, "limites": lim, "defeitos": defeitos(eps, globais, lim)}
    (pasta / "analise.json").write_text(json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
    for modelo, r in final.items():
        print("=====", modelo)
        print("acerto por miolo:", round(r["acerto_por_miolo"], 4))
        print("separação davi×convidada:", {k: round(v, 3) for k, v in r["separacao_resumo"].items()})
        print("bloco interno:", {k: round(v, 3) for k, v in r["bloco_interno"].items()})
        print("bloco referência:", {k: round(v, 3) for k, v in r["bloco_referencia"].items()})
        print("mesma persona entre episódios:", {p: round(v["min"], 3) for p, v in r["mesma_persona_entre_episodios"].items()})
        print("limites:", r["limites"])
        print("defeito 1 (timbre trocado):", {v: f"{d['detectados']}/{d['casos']}" for v, d in r["defeitos"]["timbre_trocado"].items()})
        print("defeito 2 (confundíveis):", {k: f"{d['detectados']}/{d['casos']} (min {d['min']:.3f}, max {d['max']:.3f})"
                                             for k, d in r["defeitos"]["vozes_confundiveis"].items()})
        mais = sorted(r["proximidade_das_vozes"].items(), key=lambda kv: -kv[1])[:4]
        print("vozes mais próximas:", [(k, round(v, 3)) for k, v in mais])
