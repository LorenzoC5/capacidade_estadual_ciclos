"""O corte se paga? Economia líquida de cortar R$ 1 de despesa estadual na crise.

Conta: cortar R$ 1 reduz o PIB estadual em m (multiplicador). Com receita tributária
própria igual a uma fração t do PIB e elasticidade e da receita ao PIB, a arrecadação
cai m * t * e. A economia líquida do corte é 1 - m * t * e, e o PIB perdido por real
efetivamente economizado é m / (1 - m * t * e).

Entradas (já geradas pela coleta):
  dados/01_bruto/siconfi/dca/...      receita tributária (natureza 1.1), bruta e deduções
  dados/01_bruto/ibge/sidra_t5938.csv PIB estadual a preços correntes
Saídas:
  dados/03_final/corte_carga_tributaria.csv    t por UF e ano
  dados/03_final/corte_se_paga.csv             tabela final por multiplicador
  dados/03_final/corte_se_paga.md              a mesma tabela em markdown
  dados/03_final/figuras/corte_se_paga.png

Uso:
  python scripts/30_corte_se_paga.py --anos 2019 2023 --elasticidade 1 1.5
"""
from __future__ import annotations

import argparse
import importlib

import pandas as pd

from _util import BRUTO, RAIZ, log

FINAL = RAIZ / "dados" / "03_final"
UF_FOCO = "MT"

# Multiplicadores das tabelas 1 e 2 do guia (fonte entre parênteses).
MULTIPLICADORES = [
    ("Gasto total, limite inferior IC 95% (Bezerra, Pereira e Scalco, 2026)", 0.17),
    ("Investimento, valor baixo (Arruda, Bastos e Rios e Silva, 2018)", 0.22),
    ("Gasto corrente, valor baixo (Arruda, Bastos e Rios e Silva, 2018)", 0.59),
    ("Construção em MT, valor adicionado tipo II (Silva e Guimarães, 2024)", 0.81),
    ("Gasto total, longo prazo (ANPEC, 2017)", 0.825),
    ("Gasto total sem 2020 (Bezerra, Pereira e Scalco, 2026)", 1.16),
    ("Administração pública em MT, tipo II (Silva e Guimarães, 2024)", 1.25),
    ("Investimento, valor alto (Arruda, Bastos e Rios e Silva, 2018)", 1.46),
    ("Educação pública em MT, tipo II (Silva e Guimarães, 2024)", 1.48),
    ("Gasto total, estimativa central (Bezerra, Pereira e Scalco, 2026)", 1.59),
    ("Gasto corrente, valor alto (Arruda, Bastos e Rios e Silva, 2018)", 1.64),
    ("Gasto total, limite superior IC 95% (Bezerra, Pereira e Scalco, 2026)", 3.47),
]


def receita_tributaria() -> pd.DataFrame:
    """Receita tributária líquida (natureza 1.1, bruta menos deduções) da DCA, nominal."""
    p1 = importlib.import_module("20_passo1_ajuste_crises")
    p1.NATUREZA = {"receita_tributaria": "1.1"}
    df = p1.painel_dca()
    if df.empty:
        raise SystemExit("Sem DCA em disco. Rodar: python scripts/01_siconfi.py dca")
    return df[["uf", "ano", "valor_nominal"]].rename(columns={"valor_nominal": "receita_tributaria"})


def pib_estadual() -> pd.DataFrame:
    arq = BRUTO / "ibge" / "sidra_t5938.csv"
    if not arq.exists():
        raise SystemExit("Sem PIB estadual. Rodar: python scripts/03_ibge.py")
    df = pd.read_csv(arq, dtype=str)
    var = df["Variável"].str.contains("Produto Interno Bruto a preços correntes", case=False, na=False)
    df = df[var & ~df["Variável"].str.contains("per capita|participação", case=False, na=False)]
    ufs = pd.read_csv(RAIZ / "dados" / "00_referencia" / "ufs.csv")
    df = df.merge(ufs[["nome", "sigla"]], left_on="Unidade da Federação", right_on="nome")
    fator = df["Unidade de Medida"].str.contains("Mil", case=False, na=False).map({True: 1000, False: 1})
    df["pib"] = pd.to_numeric(df["Valor"], errors="coerce") * fator
    return df.rename(columns={"sigla": "uf", "Ano": "ano"})[["uf", "ano", "pib"]].astype({"ano": int})


def tabela(t: float, elasticidades: list[float]) -> pd.DataFrame:
    linhas = []
    for nome, m in MULTIPLICADORES:
        linha = {"multiplicador": nome, "m": m}
        for e in elasticidades:
            econ = 1 - m * t * e
            linha[f"economia_liquida_e{e:g}"] = round(econ, 2)
            linha[f"pib_perdido_por_real_economizado_e{e:g}"] = round(m / econ, 2)
        linhas.append(linha)
    return pd.DataFrame(linhas)


def figura(t_foco: float, t_mediana: float, elasticidades: list[float]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    m = np.linspace(0, 3.6, 200)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for t, rotulo, cor in [(t_foco, UF_FOCO, "#c0392b"), (t_mediana, "mediana dos estados", "0.4")]:
        for e, estilo in zip(elasticidades, ["-", "--"]):
            ax.plot(m, 1 - m * t * e, estilo, color=cor, label=f"{rotulo}, elasticidade {e:g}")
    for _, valor in MULTIPLICADORES:
        ax.axvline(valor, color="0.85", lw=0.8, zorder=0)
    ax.axhline(0.5, color="0.6", lw=0.6, ls=":")
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Multiplicador do gasto estadual (m)")
    ax.set_ylabel("Economia líquida por R$ 1 cortado")
    ax.set_title("Quanto de cada real cortado o estado de fato economiza", fontsize=10)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    (FINAL / "figuras").mkdir(parents=True, exist_ok=True)
    fig.savefig(FINAL / "figuras" / "corte_se_paga.png", dpi=150)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", nargs=2, type=int, default=(2019, 2023))
    ap.add_argument("--elasticidade", nargs="+", type=float, default=[1.0, 1.5])
    a = ap.parse_args()

    base = receita_tributaria().merge(pib_estadual(), on=["uf", "ano"])
    base["t"] = base["receita_tributaria"] / base["pib"]
    FINAL.mkdir(parents=True, exist_ok=True)
    base.to_csv(FINAL / "corte_carga_tributaria.csv", index=False)

    janela = base[base["ano"].between(*a.anos)]
    t_uf = janela.groupby("uf")["t"].mean()
    t_foco, t_med = t_uf.get(UF_FOCO), t_uf.median()
    if t_foco is None:
        raise SystemExit(f"Sem dados de {UF_FOCO} no período {a.anos}")
    log.info("Receita tributária líquida / PIB, média %s-%s: %s = %.1f%%; mediana dos estados = %.1f%%",
             *a.anos, UF_FOCO, 100 * t_foco, 100 * t_med)

    tab = tabela(t_foco, a.elasticidade)
    tab.insert(0, "t_usado", round(t_foco, 4))
    tab.to_csv(FINAL / "corte_se_paga.csv", index=False)
    (FINAL / "corte_se_paga.md").write_text(
        f"Receita tributária líquida de {UF_FOCO} = {100 * t_foco:.1f}% do PIB "
        f"(média {a.anos[0]}-{a.anos[1]}); mediana dos estados = {100 * t_med:.1f}%.\n\n"
        + tab.drop(columns="t_usado").to_markdown(index=False), encoding="utf-8")
    figura(t_foco, t_med, a.elasticidade)
    pior = 1 - max(m for _, m in MULTIPLICADORES) * t_foco * max(a.elasticidade)
    log.info("Pior caso para %s: cada R$ 1 cortado ainda economiza R$ %.2f", UF_FOCO, pior)
