"""Coleta dos relatórios fiscais dos 27 estados na API do SICONFI (Tesouro Nacional).

O SICONFI é o sucessor do FINBRA para os dados declarados pelos entes.
API: https://apidatalake.tesouro.gov.br/ords/siconfi/tt/

Uso:
    python scripts/01_siconfi.py entes
    python scripts/01_siconfi.py rreo --anos 2015 2026
    python scripts/01_siconfi.py rgf  --anos 2015 2026
    python scripts/01_siconfi.py dca  --anos 2013 2025
    python scripts/01_siconfi.py msc  --anos 2018 2026     # pesado, opcional
    python scripts/01_siconfi.py tudo

Cada chamada grava um CSV por (relatório, anexo, ano, período, UF), o que permite
retomar a coleta se a conexão cair. A consolidação fica em 02_intermediario.
"""
from __future__ import annotations

import argparse
import datetime as dt

from _util import BRUTO, SICONFI, ja_existe, log, ords_todos, salvar, ufs

# Anexos usados no projeto. A lista completa está em docs/dicionario_siconfi.md.
RREO_ANEXOS = [
    "RREO-Anexo 01",  # Balanço orçamentário: receitas e despesas correntes/capital (poupança)
    "RREO-Anexo 02",  # Despesa por função/subfunção
    "RREO-Anexo 03",  # Receita Corrente Líquida (RCL), mês a mês
    "RREO-Anexo 04",  # Regime próprio de previdência
    "RREO-Anexo 06",  # Resultados primário e nominal
    "RREO-Anexo 07",  # Restos a pagar por poder
    "RREO-Anexo 09",  # Operações de crédito e despesas de capital (regra de ouro)
]
RGF_ANEXOS = [
    "RGF-Anexo 01",  # Despesa com pessoal (% RCL)
    "RGF-Anexo 02",  # Dívida Consolidada Líquida (DCL/RCL, limite do Senado)
    "RGF-Anexo 03",  # Garantias e contragarantias
    "RGF-Anexo 04",  # Operações de crédito
    "RGF-Anexo 05",  # Disponibilidade de caixa e restos a pagar (colchão de liquidez)
]
MSC_TIPOS = {
    "msc_patrimonial": [1, 2],      # ativo e passivo (caixa, aplicações, dívida)
    "msc_orcamentaria": [5, 6],     # execução orçamentária mensal
}


def coletar_entes():
    itens = ords_todos(SICONFI, "/entes", {})
    n = salvar(itens, BRUTO / "siconfi" / "entes" / "entes.csv")
    log.info("entes: %s linhas", n)


def coletar_rreo(ano_ini: int, ano_fim: int):
    for ano in range(ano_ini, ano_fim + 1):
        for periodo in range(1, 7):  # bimestres; o 6º acumula o ano
            for anexo in RREO_ANEXOS:
                for _, uf in ufs().iterrows():
                    destino = (BRUTO / "siconfi" / "rreo" / anexo.replace(" ", "_")
                               / f"{ano}" / f"rreo_{ano}_b{periodo}_{uf.sigla}.csv")
                    if ja_existe(destino):
                        continue
                    itens = ords_todos(SICONFI, "/rreo", {
                        "an_exercicio": ano, "nr_periodo": periodo,
                        "co_tipo_demonstrativo": "RREO", "no_anexo": anexo,
                        "co_esfera": "E", "id_ente": int(uf.cod_ibge),
                    })
                    n = salvar(itens, destino)
                    log.info("RREO %s %s b%s %s: %s linhas", anexo, ano, periodo, uf.sigla, n)


def coletar_rgf(ano_ini: int, ano_fim: int, poderes=("E",)):
    for ano in range(ano_ini, ano_fim + 1):
        for periodo in range(1, 4):  # estados publicam por quadrimestre
            for anexo in RGF_ANEXOS:
                for poder in poderes:
                    for _, uf in ufs().iterrows():
                        destino = (BRUTO / "siconfi" / "rgf" / anexo.replace(" ", "_") / f"{ano}"
                                   / f"rgf_{ano}_q{periodo}_{poder}_{uf.sigla}.csv")
                        if ja_existe(destino):
                            continue
                        itens = ords_todos(SICONFI, "/rgf", {
                            "an_exercicio": ano, "in_periodicidade": "Q", "nr_periodo": periodo,
                            "co_tipo_demonstrativo": "RGF", "no_anexo": anexo,
                            "co_esfera": "E", "co_poder": poder, "id_ente": int(uf.cod_ibge),
                        })
                        n = salvar(itens, destino)
                        log.info("RGF %s %s q%s %s %s: %s linhas", anexo, ano, periodo, poder, uf.sigla, n)


def coletar_dca(ano_ini: int, ano_fim: int):
    """Contas anuais (balanço patrimonial, receitas, despesas por natureza e função)."""
    for ano in range(ano_ini, ano_fim + 1):
        for _, uf in ufs().iterrows():
            destino = BRUTO / "siconfi" / "dca" / f"{ano}" / f"dca_{ano}_{uf.sigla}.csv"
            if ja_existe(destino):
                continue
            itens = ords_todos(SICONFI, "/dca", {"an_exercicio": ano, "id_ente": int(uf.cod_ibge)})
            n = salvar(itens, destino)
            log.info("DCA %s %s: %s linhas (todos os anexos)", ano, uf.sigla, n)


def coletar_msc(ano_ini: int, ano_fim: int):
    """Matriz de Saldos Contábeis mensal (a partir de 2018). Útil para caixa mensal."""
    hoje = dt.date.today()
    for ano in range(ano_ini, ano_fim + 1):
        for mes in range(1, 13):
            if (ano, mes) >= (hoje.year, hoje.month):
                break
            for endpoint, classes in MSC_TIPOS.items():
                for classe in classes:
                    for _, uf in ufs().iterrows():
                        destino = (BRUTO / "siconfi" / "msc" / endpoint / f"{ano}"
                                   / f"{endpoint}_{ano}_{mes:02d}_c{classe}_{uf.sigla}.csv")
                        if ja_existe(destino):
                            continue
                        itens = ords_todos(SICONFI, f"/{endpoint}", {
                            "id_ente": int(uf.cod_ibge), "an_referencia": ano, "me_referencia": mes,
                            "co_tipo_matriz": "MSCC", "classe_conta": classe, "id_tv": "ending_balance",
                        })
                        n = salvar(itens, destino)
                        log.info("MSC %s %s-%02d c%s %s: %s linhas", endpoint, ano, mes, classe, uf.sigla, n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("relatorio", choices=["entes", "rreo", "rgf", "dca", "msc", "tudo"])
    ap.add_argument("--anos", nargs=2, type=int, default=None)
    ap.add_argument("--todos-poderes", action="store_true",
                    help="RGF de Legislativo, Judiciário, MP e Defensoria além do Executivo")
    a = ap.parse_args()
    ano_atual = dt.date.today().year
    padrao = {"rreo": (2015, ano_atual), "rgf": (2015, ano_atual),
              "dca": (2013, ano_atual - 1), "msc": (2018, ano_atual)}
    poderes = ("E", "L", "J", "M", "D") if a.todos_poderes else ("E",)

    alvos = ["entes", "rreo", "rgf", "dca"] if a.relatorio == "tudo" else [a.relatorio]
    for alvo in alvos:
        ini, fim = a.anos or padrao.get(alvo, (None, None))
        if alvo == "entes":
            coletar_entes()
        elif alvo == "rreo":
            coletar_rreo(ini, fim)
        elif alvo == "rgf":
            coletar_rgf(ini, fim, poderes)
        elif alvo == "dca":
            coletar_dca(ini, fim)
        elif alvo == "msc":
            coletar_msc(ini, fim)
