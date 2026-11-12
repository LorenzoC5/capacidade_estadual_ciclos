"""Passo 1: quanto cada estado ajustou cada tipo de despesa em cada crise.

Entradas (geradas por 01_siconfi.py e 04_bcb.py):
  dados/01_bruto/siconfi/dca/<ano>/dca_<ano>_<UF>.csv          anual, 2013 em diante
  dados/01_bruto/siconfi/rreo/RREO-Anexo_01/<ano>/*.csv         bimestral, 2015 em diante
  dados/01_bruto/bcb/sgs_433.csv                                IPCA mensal
  dados/02_intermediario/historico_anual.csv   (opcional)       anos anteriores a 2013,
      no formato longo uf, ano, categoria, valor_nominal (ver docs/passo1_metodologia.md)

Saídas:
  dados/03_final/passo1_painel_anual.csv        UF x ano x categoria, valores reais
  dados/03_final/passo1_ajuste_por_crise.csv    UF x crise x ano da janela x categoria
  dados/03_final/passo1_resumo_crises.csv       mediana, quartis e MT por crise e categoria
  dados/03_final/passo1_bimestral_12m.csv       acumulado em 12 meses, bimestral, 2015+
  dados/03_final/figuras/passo1_<crise>.png

Uso:
  python scripts/20_passo1_ajuste_crises.py --diagnostico   # confere contas e colunas
  python scripts/20_passo1_ajuste_crises.py
"""
from __future__ import annotations

import argparse
import re
import unicodedata

import pandas as pd

from _util import BRUTO, RAIZ, log

FINAL = RAIZ / "dados" / "03_final"
INTER = RAIZ / "dados" / "02_intermediario"
UF_FOCO = "MT"

# ---------------------------------------------------------------- configuração
# Categorias pela natureza da receita e da despesa (códigos estáveis entre anos).
# O código é comparado depois de retirar os zeros finais: 3.1.00.00.00.00 vira "3.1".
NATUREZA = {
    "receita_corrente": "1",
    "despesa_corrente": "3",
    "pessoal": "3.1",
    "juros": "3.2",
    "custeio": "3.3",          # outras despesas correntes
    "despesa_capital": "4",
    "investimento": "4.4",
    "inversoes": "4.5",
    "amortizacao": "4.6",
}
DCA_COLUNA_DESPESA = r"liquidad"
DCA_COLUNA_RECEITA_BRUTA = r"brutas? realizadas?"
DCA_COLUNA_DEDUCAO = r"dedu"

# RREO, Anexo 1: rótulos de linha (sem acento, maiúsculos) e colunas acumuladas.
RREO_CONTAS = {
    "receita_corrente": r"^RECEITAS CORRENTES\b",
    "despesa_corrente": r"^DESPESAS CORRENTES\b",
    "pessoal": r"^PESSOAL E ENCARGOS SOCIAIS",
    "juros": r"^JUROS E ENCARGOS DA DIVIDA",
    "custeio": r"^OUTRAS DESPESAS CORRENTES",
    "despesa_capital": r"^DESPESAS DE CAPITAL\b",
    "investimento": r"^INVESTIMENTOS",
    "inversoes": r"^INVERSOES FINANCEIRAS",
    "amortizacao": r"^AMORTIZACAO DA DIVIDA",
}
RREO_COLUNA_RECEITA = r"ATE O BIMESTRE"
RREO_COLUNA_DESPESA = r"LIQUIDADAS ATE O BIMESTRE"
EXCLUIR = r"(?<!EXCETO )(?<!EXCETO-)INTRA"   # descarta intraorçamentárias, mantém "exceto intra"

# Crises: ano-base (antes do choque) e anos da janela. Fonte das datas: crises.csv.
CRISES = {
    "2003": (2002, [2003]),
    "2008-09": (2008, [2009]),
    "2015-16": (2014, [2015, 2016]),
    "2020": (2019, [2020]),
    "2022-23 (ICMS)": (2021, [2022, 2023]),
}
ANOS_TENDENCIA = 3   # anos antes do ano-base usados para a tendência


# ---------------------------------------------------------------- utilidades
def normalizar(txt) -> str:
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().upper()


def codigo_natureza(txt) -> str | None:
    """Extrai o código de natureza e retira os segmentos finais zerados."""
    m = re.search(r"(?<![\d.])(\d(?:\.\d{1,2}){2,})(?![\d.])", str(txt))
    if not m:
        return None
    partes = m.group(1).split(".")
    while len(partes) > 1 and set(partes[-1]) == {"0"}:
        partes.pop()
    return ".".join(partes)


def ler_csvs(pasta, padrao="*.csv") -> pd.DataFrame:
    partes = []
    for arq in sorted(pasta.rglob(padrao)):
        df = pd.read_csv(arq, low_memory=False)
        df["uf_arquivo"] = arq.stem.split("_")[-1]
        df["arquivo"] = arq.name
        partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def sem_duplicatas(df, chaves, origem):
    dup = df.duplicated(chaves, keep=False)
    if dup.any():
        log.warning("%s: %s linhas duplicadas para %s; mantendo a primeira. "
                    "Rodar --diagnostico e ajustar os filtros.", origem, int(dup.sum()), chaves)
    return df.drop_duplicates(chaves, keep="first")


# ---------------------------------------------------------------- deflator
def ipca() -> pd.DataFrame:
    df = pd.read_csv(BRUTO / "bcb" / "sgs_433.csv")
    df["data"] = pd.to_datetime(df["data"], dayfirst=True)
    df["valor"] = pd.to_numeric(df["valor"].astype(str).str.replace(",", "."), errors="coerce")
    df = df.sort_values("data")
    df["indice"] = (1 + df["valor"] / 100).cumprod()
    df["ano"], df["mes"] = df["data"].dt.year, df["data"].dt.month
    ultimo_completo = df.groupby("ano")["mes"].max().loc[lambda s: s == 12].index.max()
    base = df.loc[df["ano"] == ultimo_completo, "indice"].mean()
    df["fator"] = base / df["indice"]   # multiplica valor nominal -> R$ do ano-base
    log.info("Valores reais a preços médios de %s (IPCA)", ultimo_completo)
    return df


# ---------------------------------------------------------------- anual (DCA)
def painel_dca() -> pd.DataFrame:
    bruto = ler_csvs(BRUTO / "siconfi" / "dca")
    if bruto.empty:
        log.warning("Sem DCA em disco; rodar 01_siconfi.py dca")
        return pd.DataFrame()
    bruto = bruto[~bruto[["anexo", "rotulo", "conta"]].astype(str)
                  .apply(lambda c: c.map(normalizar)).apply(lambda c: c.str.contains(EXCLUIR)).any(axis=1)]
    bruto["codigo"] = bruto["conta"].map(codigo_natureza).fillna(bruto["cod_conta"].map(codigo_natureza))
    bruto["coluna_n"] = bruto["coluna"].map(normalizar)
    alvo = {v: k for k, v in NATUREZA.items()}
    bruto = bruto[bruto["codigo"].isin(alvo)]
    bruto["categoria"] = bruto["codigo"].map(alvo)
    bruto["valor"] = pd.to_numeric(bruto["valor"], errors="coerce")

    desp = bruto[~bruto["categoria"].str.startswith("receita")
                 & bruto["coluna_n"].str.contains(DCA_COLUNA_DESPESA.upper())]
    rec = bruto[bruto["categoria"].str.startswith("receita")]
    rec_bruta = rec[rec["coluna_n"].str.contains(DCA_COLUNA_RECEITA_BRUTA.upper(), regex=True)]
    rec_ded = rec[rec["coluna_n"].str.contains(DCA_COLUNA_DEDUCAO.upper())]

    chaves = ["uf_arquivo", "exercicio", "categoria"]
    desp = sem_duplicatas(desp, chaves, "DCA despesa")
    rec_bruta = sem_duplicatas(rec_bruta, chaves, "DCA receita")
    ded = rec_ded.groupby(chaves, as_index=False)["valor"].sum().rename(columns={"valor": "deducoes"})
    rec = rec_bruta.merge(ded, on=chaves, how="left").fillna({"deducoes": 0})
    rec["valor"] = rec["valor"] - rec["deducoes"]   # receita líquida de deduções (FUNDEB etc.)

    df = pd.concat([desp[chaves + ["valor"]], rec[chaves + ["valor"]]])
    return df.rename(columns={"uf_arquivo": "uf", "exercicio": "ano", "valor": "valor_nominal"})


def painel_anual() -> pd.DataFrame:
    df = painel_dca()
    hist = INTER / "historico_anual.csv"
    if hist.exists():
        h = pd.read_csv(hist)
        h = h[h["ano"] < (df["ano"].min() if not df.empty else 9999)]
        df = pd.concat([h[["uf", "ano", "categoria", "valor_nominal"]], df])
        log.info("Histórico anterior a 2013 incluído: %s linhas", len(h))
    else:
        log.info("Sem %s: crises de 2003 e 2008-09 ficam de fora por ora", hist.name)
    defl = ipca().groupby("ano")["fator"].mean()
    df["valor_real"] = df["valor_nominal"] * df["ano"].map(defl)
    largo = df.pivot_table(index=["uf", "ano"], columns="categoria", values="valor_real").reset_index()
    if {"receita_corrente", "despesa_corrente"} <= set(largo.columns):
        largo["poupanca_corrente"] = largo["receita_corrente"] - largo["despesa_corrente"]
    if {"juros", "amortizacao"} <= set(largo.columns):
        largo["servico_divida"] = largo["juros"] + largo["amortizacao"]
    longo = largo.melt(id_vars=["uf", "ano"], var_name="categoria", value_name="valor_real").dropna()
    return longo


# ---------------------------------------------------------------- medidas por crise
def ajuste_por_crise(painel: pd.DataFrame) -> pd.DataFrame:
    p = painel.set_index(["uf", "categoria", "ano"])["valor_real"]
    rc = painel[painel.categoria == "receita_corrente"].set_index(["uf", "ano"])["valor_real"]
    linhas = []
    for crise, (base, janela) in CRISES.items():
        for (uf, cat), serie in p.groupby(level=[0, 1]):
            s = serie.droplevel([0, 1])
            if base not in s.index:
                continue
            v0 = s[base]
            anteriores = [a for a in range(base - ANOS_TENDENCIA, base) if a in s.index]
            g = None
            if anteriores and s[min(anteriores)] > 0 and v0 > 0:
                k = base - min(anteriores)
                g = (v0 / s[min(anteriores)]) ** (1 / k) - 1
            for ano in janela:
                if ano not in s.index:
                    continue
                v = s[ano]
                tendencia = v0 * (1 + g) ** (ano - base) if g is not None else None
                linhas.append({
                    "crise": crise, "uf": uf, "categoria": cat, "ano_base": base, "ano": ano,
                    "valor_base": v0, "valor": v,
                    "var_real_pct": 100 * (v / v0 - 1) if v0 else None,
                    "desvio_tendencia_pct": 100 * (v / tendencia - 1) if tendencia else None,
                    "anos_tendencia": base - min(anteriores) if anteriores else 0,
                    "delta_pp_receita_base": 100 * (v - v0) / rc.get((uf, base), float("nan")),
                })
    return pd.DataFrame(linhas)


def resumo(aj: pd.DataFrame) -> pd.DataFrame:
    if aj.empty:
        return pd.DataFrame()
    media_janela = aj.groupby(["crise", "uf", "categoria"], as_index=False)[
        ["var_real_pct", "desvio_tendencia_pct", "delta_pp_receita_base"]].mean()
    g = media_janela.groupby(["crise", "categoria"])["var_real_pct"]
    out = pd.DataFrame({
        "n_estados": g.count(), "p25": g.quantile(0.25), "mediana": g.median(), "p75": g.quantile(0.75),
    }).reset_index()
    foco = media_janela[media_janela.uf == UF_FOCO][["crise", "categoria", "var_real_pct"]]
    return out.merge(foco.rename(columns={"var_real_pct": UF_FOCO}), how="left")


# ---------------------------------------------------------------- bimestral (RREO)
def painel_bimestral() -> pd.DataFrame:
    bruto = ler_csvs(BRUTO / "siconfi" / "rreo" / "RREO-Anexo_01")
    if bruto.empty:
        log.warning("Sem RREO Anexo 1 em disco; rodar 01_siconfi.py rreo")
        return pd.DataFrame()
    bruto["conta_n"] = bruto["conta"].map(normalizar)
    bruto["coluna_n"] = bruto["coluna"].map(normalizar)
    bruto = bruto[~(bruto["conta_n"].str.contains(EXCLUIR) | bruto["cod_conta"].astype(str).map(normalizar).str.contains(EXCLUIR))]
    bruto["periodo"] = bruto["arquivo"].str.extract(r"_b(\d)_").astype(int)
    linhas = []
    for cat, rx in RREO_CONTAS.items():
        col = RREO_COLUNA_RECEITA if cat.startswith("receita") else RREO_COLUNA_DESPESA
        sel = bruto[bruto["conta_n"].str.contains(rx) & bruto["coluna_n"].str.contains(col)]
        if cat.startswith("receita"):
            sel = sel[~sel["coluna_n"].str.contains("LIQUIDADAS|EMPENHADAS|PAGAS")]
        sel = sem_duplicatas(sel, ["uf_arquivo", "exercicio", "periodo"], f"RREO {cat}")
        sel = sel.assign(categoria=cat, valor=pd.to_numeric(sel["valor"], errors="coerce"))
        linhas.append(sel[["uf_arquivo", "exercicio", "periodo", "categoria", "valor"]])
    df = pd.concat(linhas).rename(columns={"uf_arquivo": "uf", "exercicio": "ano", "valor": "acumulado"})
    df = df.sort_values(["uf", "categoria", "ano", "periodo"])
    # fluxo do bimestre = acumulado no ano menos o acumulado do bimestre anterior
    df["fluxo"] = df.groupby(["uf", "categoria", "ano"])["acumulado"].diff().fillna(df["acumulado"])
    defl = ipca()
    defl["periodo"] = (defl["mes"] + 1) // 2
    fator = defl.groupby(["ano", "periodo"])["fator"].mean()
    df["fluxo_real"] = df["fluxo"] * df.set_index(["ano", "periodo"]).index.map(fator)
    df["acum_12m_real"] = (df.groupby(["uf", "categoria"])["fluxo_real"]
                           .transform(lambda s: s.rolling(6, min_periods=6).sum()))
    return df


# ---------------------------------------------------------------- figuras
def figuras(aj: pd.DataFrame):
    if aj.empty:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pasta = FINAL / "figuras"
    pasta.mkdir(parents=True, exist_ok=True)
    cats = ["receita_corrente", "pessoal", "custeio", "investimento", "servico_divida", "poupanca_corrente"]
    m = aj.groupby(["crise", "uf", "categoria"], as_index=False)["var_real_pct"].mean()
    for crise, d in m.groupby("crise"):
        d = d[d.categoria.isin(cats) & (d.categoria != "poupanca_corrente")]
        if d.empty:
            continue
        ordem = [c for c in cats if c in d.categoria.unique()]
        fig, ax = plt.subplots(figsize=(8, 0.6 * len(ordem) + 1.5))
        for i, c in enumerate(ordem):
            x = d[d.categoria == c]
            ax.scatter(x["var_real_pct"], [i] * len(x), color="0.7", s=18, zorder=2)
            ax.plot([x["var_real_pct"].median()] * 2, [i - 0.3, i + 0.3], color="black", lw=2, zorder=3)
            mt = x[x.uf == UF_FOCO]
            ax.scatter(mt["var_real_pct"], [i] * len(mt), color="#c0392b", s=50, zorder=4)
        ax.axvline(0, color="0.4", lw=0.8)
        rotulos = {"receita_corrente": "Receita corrente", "pessoal": "Pessoal", "custeio": "Custeio",
                   "investimento": "Investimento", "servico_divida": "Serviço da dívida"}
        ax.set_yticks(range(len(ordem)), [rotulos.get(c, c) for c in ordem])
        ax.invert_yaxis()
        ax.set_xlabel("Variação real em relação ao ano-base (%)")
        ax.set_title(f"Crise {crise}: estados (cinza), mediana (traço), {UF_FOCO} (vermelho)", fontsize=10)
        fig.tight_layout()
        fig.savefig(pasta / f"passo1_{re.sub(r'[^0-9a-z]+', '_', crise.lower())}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------- diagnóstico
def diagnostico():
    for nome, pasta in [("DCA", BRUTO / "siconfi" / "dca"),
                        ("RREO Anexo 1", BRUTO / "siconfi" / "rreo" / "RREO-Anexo_01")]:
        arqs = sorted(pasta.rglob(f"*_{UF_FOCO}.csv"))
        if not arqs:
            print(f"\n{nome}: nenhum arquivo de {UF_FOCO}")
            continue
        df = pd.read_csv(arqs[-1], low_memory=False)
        print(f"\n===== {nome}: {arqs[-1].name} =====")
        print("Colunas:", list(df.columns))
        for c in ["anexo", "rotulo", "coluna"]:
            if c in df:
                print(f"\nValores de '{c}':", *sorted(df[c].dropna().unique()), sep="\n  ")
        print("\nPrimeiras contas (cod_conta | conta):")
        print(df[["cod_conta", "conta"]].drop_duplicates().head(60).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnostico", action="store_true")
    a = ap.parse_args()
    if a.diagnostico:
        diagnostico()
        raise SystemExit
    FINAL.mkdir(parents=True, exist_ok=True)
    painel = painel_anual()
    if painel.empty:
        raise SystemExit("Painel anual vazio. Rodar --diagnostico e conferir contas e colunas.")
    painel.to_csv(FINAL / "passo1_painel_anual.csv", index=False)
    aj = ajuste_por_crise(painel)
    aj.to_csv(FINAL / "passo1_ajuste_por_crise.csv", index=False)
    resumo(aj).to_csv(FINAL / "passo1_resumo_crises.csv", index=False)
    figuras(aj)
    bim = painel_bimestral()
    if not bim.empty:
        bim.to_csv(FINAL / "passo1_bimestral_12m.csv", index=False)
    log.info("Passo 1 concluído: %s linhas de ajuste em %s crises",
             len(aj), aj["crise"].nunique() if len(aj) else 0)
