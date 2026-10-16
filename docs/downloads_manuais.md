# Downloads manuais

Bases sem API aberta ou que exigem cadastro. Cada arquivo baixado vai para a subpasta indicada em `dados/01_bruto`, com o nome original preservado e a data do download anotada em `dados/01_bruto/<fonte>/LEIAME.txt`.

## CONFAZ: Boletim de Arrecadação dos Tributos Estaduais

Página: https://www.confaz.fazenda.gov.br/boletim-de-arrecadacao-dos-tributos-estaduais

Os dados abertos ficam no Portal Brasileiro de Dados Abertos, com link a partir do ícone na própria página do boletim. A série é mensal, por UF, e separa ICMS, IPVA, ITCMD e taxas; o ICMS vem detalhado por setor (atacado, varejo, energia, combustíveis, comunicação, transporte). A consulta cobre desde 1998. O portal federal passou a exigir chave de acesso para a API, então o caminho mais simples é baixar a planilha completa pela interface. Destino: `dados/01_bruto/confaz/`.

Para a pergunta (i), essa base permite separar a sensibilidade da receita própria ao ciclo da sensibilidade das transferências. Para a pergunta (ii), dá a queda mensal da arrecadação em cada crise, inclusive o choque da LC 194/2022 sobre combustíveis e energia.

## Séries estaduais anteriores a 2013

O SICONFI só cobre os estados a partir de 2013 (DCA) e 2015 (RREO e RGF pela API). Para a crise de 2008-09 e para o período logo após a LRF, há duas fontes no Tesouro, que a rotina `02_tesouro.py ckan` tenta localizar sozinha.

A primeira é a Execução Orçamentária de Estados, planilha com as contas dos estados de 1995 a 2013. A segunda é o FINBRA histórico, com as contas anuais de 1989 a 2012 em banco de dados Microsoft Access, publicado no Tesouro Transparente. Segundo a cartilha do FINBRA, entre 1998 e 2008 as despesas aparecem só na fase de empenho; a partir de 2009 vêm também liquidadas e pagas. Isso pesa na comparação com a série atual, que usa despesa liquidada.

Cartilha de extração: https://siconfi.tesouro.gov.br/siconfi/pages/public/arquivo/conteudo/Cartilha_do_Finbra_2023.pdf

Se a busca automática não trouxer os arquivos, baixar pela página do Tesouro Transparente (buscar “FINBRA” e “Execução Orçamentária de Estados”). Destino: `dados/01_bruto/tesouro_transparente/finbra_historico/` e `.../execucao_orcamentaria_estados/`.

## Base dos Dados: SICONFI compatibilizado

A Base dos Dados mantém o conjunto `br_me_siconfi` com tabelas por UF a partir de 2013 (`uf_receitas_orcamentarias`, `uf_despesas_orcamentarias`, `uf_despesas_funcao`). O dado de origem é o mesmo da DCA; o ganho é a tabela de compatibilização de contas entre exercícios, que resolve boa parte da troca de rótulos ao longo dos anos. O acesso é por BigQuery, com um projeto gratuito no Google Cloud.

```python
import basedosdados as bd   # pip install basedosdados

sql = """
SELECT ano, sigla_uf, estagio_bd, id_conta_bd, conta_bd, valor
FROM `basedosdados.br_me_siconfi.uf_receitas_orcamentarias`
"""
df = bd.read_sql(sql, billing_project_id="SEU_PROJETO_GCP")
df.to_csv("dados/01_bruto/base_dos_dados/uf_receitas_orcamentarias.csv", index=False)
```

Repetir trocando a tabela por `uf_despesas_orcamentarias` e `uf_despesas_funcao`. Destino: `dados/01_bruto/base_dos_dados/`.

## Boletim de Finanças dos Entes Subnacionais

Publicado pelo Tesouro todo ano desde 2016, com anexos em planilha. A rotina `02_tesouro.py ckan` busca os anexos; se não vierem, baixar pela página de publicações do Tesouro Transparente. Os números do boletim já passaram pelos ajustes do PAF, então servem de régua para conferir a apuração própria feita a partir do SICONFI.

## Contas Regionais 2024

O IBGE costuma divulgar as Contas Regionais em novembro, com cerca de dois anos de defasagem. A edição com dados de 2023 saiu em novembro de 2025; a de 2024 deve sair na próxima rodada. Quando sair, basta rodar `python scripts/03_ibge.py` de novo, depois de apagar os arquivos `sidra_t*.csv` das Contas Regionais.
