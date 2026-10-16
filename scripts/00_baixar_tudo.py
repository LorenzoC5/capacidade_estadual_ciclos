"""Roda toda a coleta em sequência. Tempo estimado: algumas horas (o RREO é o mais longo).

Uso:
    python scripts/00_baixar_tudo.py            # tudo, exceto MSC
    python scripts/00_baixar_tudo.py --com-msc  # inclui a MSC mensal (bem mais pesada)

A coleta é retomável: arquivos já baixados são pulados.
"""
import argparse
import subprocess
import sys
from pathlib import Path

PASTA = Path(__file__).parent
ETAPAS = [
    ["01_siconfi.py", "tudo"],
    ["02_tesouro.py", "tudo"],
    ["03_ibge.py"],
    ["04_bcb.py"],
    ["05_ipeadata.py"],
    ["10_consolidar_siconfi.py"],
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--com-msc", action="store_true")
    a = ap.parse_args()
    if a.com_msc:
        ETAPAS.insert(1, ["01_siconfi.py", "msc"])
    for etapa in ETAPAS:
        print(f"\n=== {' '.join(etapa)} ===", flush=True)
        r = subprocess.run([sys.executable, str(PASTA / etapa[0]), *etapa[1:]])
        if r.returncode != 0:
            print(f"Etapa {etapa[0]} terminou com erro; seguindo para a próxima. Ver coleta.log")
