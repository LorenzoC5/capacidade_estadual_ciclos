# Downloads manuais

Bases sem API aberta ou que exigem cadastro. Cada arquivo baixado vai para a subpasta indicada em `dados/01_bruto`, com o nome original preservado e a data do download anotada em `dados/01_bruto/<fonte>/LEIAME.txt`.

## RREO e RGF estaduais de 2000 a 2014

A consulta de RREO no SICONFI, e portanto a API, começa em 2015 para os estados. Os relatórios anteriores foram publicados por cada estado no próprio portal, em geral em PDF, na seção de transparência ou de “Relatórios da LRF” da secretaria de Fazenda ou de Economia. O Distrito Federal, por exemplo, mantém todos os demonstrativos do RREO de 2000 em diante.

Antes de baixar 27 estados por 15 anos, vale decidir com o grupo se a frequência anual basta para as crises de 2003 e de 2008-09. Se bastar, as séries anuais da Execução Orçamentária de Estados e do FINBRA histórico (seção seguinte) cobrem poupança corrente, pessoal, investimento e serviço da dívida sem precisar extrair dados de PDF. Se for preciso o bimestre, a recomendação é começar pelos estados de comparação mais relevantes para Mato Grosso e extrair só as linhas usadas no projeto. Destino: `dados/01_bruto/rreo_rgf_portais/<UF>/`.

Para a dívida consolidada antes de 2015, o orientador indicou os dados do PAF e da STN além do RGF. Vale perguntar a ele qual série do PAF tem em mente e onde ela está publicada.

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

O IBGE costuma divulgar as Contas Regionais em novembro, com cerca de dois anos de defasagem. A edição com dados de 2023 saiu em novembro de 2025; a de 2024 deve sair na próxima rodada.

As Contas Regionais não aparecem como pesquisa na API de agregados do SIDRA (a única tabela por UF lá é a 5938, da pesquisa “Produto Interno Bruto dos Municípios”, só com valores correntes). Por isso `03_ibge.py` busca a edição mais recente no FTP do IBGE (`ftp.ibge.gov.br/Contas_Regionais/<edição>/xls/`), guarda os zips `Especiais_2002_<edição>_xls.zip` e `Conta_da_Producao_2002_<edição>_xls.zip` em `dados/01_bruto/ibge/contas_regionais/<edição>/` e grava `contas_regionais_especiais.csv` e `contas_regionais_conta_producao.csv`. As planilhas do IBGE vêm com os acentos corrompidos e, nas contas das grandes regiões, com o rótulo “Região Norte” repetido por engano; o script identifica território e atividade pelo título do arquivo e pela posição da aba. Ler as planilhas `.xls` exige o pacote `xlrd`, que está no `requirements.txt`.

Quando a edição nova sair, basta apagar os dois CSVs `contas_regionais_*.csv` (e `sidra_t5938.csv`, se quiser atualizar também a tabela do SIDRA) e rodar `python scripts/03_ibge.py` de novo. Os zips da edição anterior ficam guardados na própria pasta.
