"""Funções comuns aos scripts de coleta.

Requisições com novas tentativas, paginação das APIs ORDS do Tesouro
(SICONFI e SADIPEM), gravação em CSV e registro de log.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
BRUTO = RAIZ / "dados" / "01_bruto"
REF = RAIZ / "dados" / "00_referencia"

SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
SADIPEM = "https://apidatalake.tesouro.gov.br/ords/sadipem/tt"
TRANSF = "https://apiapex.tesouro.gov.br/aria/v1/transferencias_constitucionais/custom"

HEADERS = {"User-Agent": "pesquisa-academica-fea-usp/1.0", "Accept": "application/json"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(RAIZ / "coleta.log", encoding="utf-8")],
)
log = logging.getLogger("coleta")


def ufs() -> pd.DataFrame:
    """Tabela de referência das 27 UFs (código IBGE, sigla, região)."""
    return pd.read_csv(REF / "ufs.csv", dtype={"cod_ibge": int})


def get(url: str, params: dict | None = None, tentativas: int = 5, pausa: float = 2.0,
        timeout: int = 120, como_json: bool = True):
    """GET com novas tentativas e espera crescente. Retorna JSON, bytes ou None."""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    for i in range(1, tentativas + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json() if como_json else r.content
            if r.status_code in (400, 404):
                log.warning("HTTP %s em %s %s", r.status_code, url, params)
                return None
            log.warning("HTTP %s (tentativa %s/%s) %s", r.status_code, i, tentativas, url)
        except (requests.RequestException, json.JSONDecodeError) as e:
            log.warning("Erro (tentativa %s/%s) %s: %s", i, tentativas, url, e)
        time.sleep(pausa * i)
    log.error("Falhou após %s tentativas: %s %s", tentativas, url, params)
    return None


def ords_todos(base: str, endpoint: str, params: dict, limite: int = 5000) -> list[dict]:
    """Percorre todas as páginas de um endpoint ORDS seguindo `hasMore`."""
    itens, offset = [], 0
    while True:
        p = dict(params, offset=offset, limit=limite)
        corpo = get(f"{base}{endpoint}", p)
        if not corpo or not corpo.get("items"):
            break
        itens.extend(corpo["items"])
        if not corpo.get("hasMore"):
            break
        offset = corpo.get("offset", offset) + corpo.get("limit", limite)
        time.sleep(0.3)
    return itens


def salvar(registros, caminho: Path) -> int:
    """Grava lista de dicionários ou DataFrame em CSV (UTF-8). Retorna nº de linhas."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df = registros if isinstance(registros, pd.DataFrame) else pd.DataFrame(registros)
    if df.empty:
        return 0
    df.to_csv(caminho, index=False, encoding="utf-8")
    return len(df)


def ja_existe(caminho: Path) -> bool:
    """Permite retomar a coleta sem baixar de novo o que já está em disco."""
    return caminho.exists() and caminho.stat().st_size > 0
