"""Empilha os CSVs brutos do SICONFI em um arquivo por relatório/anexo.

Saída em dados/02_intermediario/siconfi_<relatorio>_<anexo>.parquet (ou .csv se
pyarrow não estiver instalado). Mantém todas as colunas originais da API e
acrescenta a sigla da UF a partir do nome do arquivo.

Atenção: os rótulos de conta ("conta", "cod_conta") mudam entre exercícios
conforme o Manual de Demonstrativos Fiscais. A harmonização das linhas fica
para a etapa de construção das variáveis (ver docs/dicionario_siconfi.md).
"""
from pathlib import Path

import pandas as pd

from _util import BRUTO, RAIZ, log

SAIDA = RAIZ / "dados" / "02_intermediario"


def gravar(df: pd.DataFrame, nome: str):
    SAIDA.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(SAIDA / f"{nome}.parquet", index=False)
        log.info("%s.parquet: %s linhas", nome, len(df))
    except ImportError:
        df.to_csv(SAIDA / f"{nome}.csv", index=False, encoding="utf-8")
        log.info("%s.csv: %s linhas", nome, len(df))


def empilhar(pasta: Path) -> pd.DataFrame:
    partes = []
    for arq in sorted(pasta.rglob("*.csv")):
        df = pd.read_csv(arq, low_memory=False)
        df["uf_arquivo"] = arq.stem.split("_")[-1]
        partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


if __name__ == "__main__":
    base = BRUTO / "siconfi"
    for rel in ("rreo", "rgf"):
        for pasta_anexo in sorted((base / rel).glob("*Anexo*")):
            df = empilhar(pasta_anexo)
            if not df.empty:
                gravar(df, f"siconfi_{rel}_{pasta_anexo.name.lower().replace('-', '_')}")
    df = empilhar(base / "dca")
    if not df.empty:
        gravar(df, "siconfi_dca")
