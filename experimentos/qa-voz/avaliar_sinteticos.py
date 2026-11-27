"""Aplica as regras do QA de voz aos episódios bons e aos sintéticos e diz o que cada um dispara.

Regras (limites calculados nos episódios bons, em analisar.py):
- timbre no bloco: centróide da persona no bloco contra o resto do episódio < timbre_bloco_min,
  ou contra a impressão de voz de referência < timbre_referencia_min;
- persona inteira trocada: centróide da persona no episódio contra a referência < persona_referencia_min;
- vozes confundíveis: centróide do Davi contra o da convidada > vozes_confundiveis_max.

    avaliar_sinteticos.py medidas_bons pasta_sinteticos modelo
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from analisar import analisar, carregar, centroide, convidada, limites, pontuar_blocos, referencias  # noqa: E402


def persona_contra_referencia(eps):
    """Episódio inteiro de cada persona contra a referência dos outros episódios (só quem tem outros)."""
    valores = []
    for nome, ep in eps.items():
        refs = referencias(eps, nome)
        for p in np.unique(ep["persona"]):
            if p in refs:
                valores.append(float(centroide(ep["emb"][ep["persona"] == p]) @ refs[p]))
    return valores


def regras(ep, refs, lim):
    disparos = []
    for p, b, interno, ref in pontuar_blocos(ep["persona"], ep["bloco"], ep["emb"], refs):
        if interno < lim["timbre_bloco_min"]:
            disparos.append(f"timbre: {p} no bloco {b} contra o episódio {interno:.2f}")
        if ref < lim["timbre_referencia_min"]:
            disparos.append(f"timbre: {p} no bloco {b} contra a referência {ref:.2f}")
    for p in np.unique(ep["persona"]):
        if p in refs:
            v = float(centroide(ep["emb"][ep["persona"] == p]) @ refs[p])
            if v < lim["persona_referencia_min"]:
                disparos.append(f"voz trocada: {p} contra a referência {v:.2f}")
    conv = convidada(ep)
    cos = float(centroide(ep["emb"][ep["persona"] == "davi"]) @ centroide(ep["emb"][ep["persona"] == conv]))
    if cos > lim["vozes_confundiveis_max"]:
        disparos.append(f"vozes confundíveis: davi x {conv} {cos:.2f}")
    return disparos, cos


if __name__ == "__main__":
    bons_dir, sint_dir, modelo = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    bons = carregar(bons_dir, modelo)
    r, _ = analisar(bons)
    lim = limites(r)
    pr = np.array(persona_contra_referencia(bons))
    lim["persona_referencia_min"] = round(min(pr.min() - 0.05, pr.mean() - 3 * pr.std()), 2)
    print("limites:", lim)
    print("persona inteira contra referência nos bons:", {"min": round(pr.min(), 3), "media": round(pr.mean(), 3)})
    falsos = 0
    for nome, ep in bons.items():
        disparos, cos = regras(ep, referencias(bons, nome), lim)
        falsos += bool(disparos)
        if disparos:
            print("  FALSO POSITIVO", nome, disparos)
    print(f"episódios bons com disparo: {falsos}/{len(bons)}")
    saida = {"limites": lim, "falsos_positivos": falsos, "bons": len(bons), "sinteticos": {}}
    for pasta in sorted(p for p in sint_dir.iterdir() if p.is_dir()):
        defeito = json.loads((pasta / "defeito.json").read_text(encoding="utf-8"))
        [ep] = carregar(pasta, modelo).values()
        # A referência não pode incluir o episódio base, que está sendo testado.
        disparos, cos = regras(ep, referencias(bons, defeito["base"]), lim)
        saida["sinteticos"][pasta.name] = {"disparos": disparos, "cos_davi_convidada": cos}
        print(("DETECTADO " if disparos else "NÃO DETECTADO ") + pasta.name, disparos)
    (sint_dir / f"resultado-{modelo}.json").write_text(json.dumps(saida, indent=1, ensure_ascii=False), encoding="utf-8")
