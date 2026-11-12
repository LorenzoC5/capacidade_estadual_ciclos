# Passo 1: o ajuste fiscal efetivo dos estados nas crises

## Pergunta

Quando a receita caiu em cada crise, o que cada estado cortou, em quanto e em comparação com os outros estados? O resultado alimenta o passo 2, em que os cortes são multiplicados pelos multiplicadores de cada tipo de despesa, e o passo 3, que simula o colchão de liquidez. Mato Grosso é o caso em destaque, e os demais estados servem de régua.

## Dados

A série anual vem da DCA, que existe para os estados desde 2013, com receita e despesa organizadas pela natureza. A vantagem da natureza é que o código é estável entre anos: pessoal é sempre 3.1, custeio 3.3, investimento 4.4, e assim por diante. Isso evita depender dos rótulos dos anexos do RREO, que mudam a cada edição do Manual de Demonstrativos Fiscais. A despesa é tomada na fase liquidada. A receita corrente é líquida das deduções, como a parcela do FUNDEB, para ficar comparável ao conceito usado na CAPAG.

A série bimestral vem do RREO, Anexo 1, a partir de 2015. Ela serve para olhar a dinâmica dentro do ano, sobretudo em 2020, quando a queda e a recuperação couberam em poucos meses. O RREO informa valores acumulados no ano. O programa calcula o fluxo de cada bimestre pela diferença entre bimestres e soma os seis bimestres mais recentes, o que dá um acumulado em 12 meses livre de sazonalidade (13º salário, concentração do investimento no fim do ano).

Todos os valores são deflacionados pelo IPCA e expressos a preços médios do último ano completo.

As crises de 2003 e 2008-09 dependem de dados anteriores a 2013. O programa aceita um arquivo `dados/02_intermediario/historico_anual.csv`, no mesmo formato longo do painel (colunas `uf`, `ano`, `categoria`, `valor_nominal`), montado a partir da Execução Orçamentária de Estados ou do FINBRA histórico. Enquanto esse arquivo não existir, o programa roda só para 2015-16, 2020 e 2022-23.

## Medidas

Para cada crise, define-se um ano-base, o último antes do choque (2002, 2008, 2014, 2019 e 2021), e uma janela com os anos da crise. Para cada estado, categoria e ano da janela, o programa calcula três medidas.

A primeira é a variação real em relação ao ano-base, em porcentagem. É a medida mais simples de explicar a um gestor.

A segunda é o desvio em relação à tendência. A tendência é o crescimento real médio dos três anos anteriores ao ano-base, projetado para frente. Ela importa porque uma despesa que vinha crescendo 5% ao ano e ficou parada também foi ajustada. Como a DCA começa em 2013, a tendência para a crise de 2015-16 usa só um ano (2013 a 2014), e a coluna `anos_tendencia` registra isso. Com o histórico anterior a 2013, a tendência passa a usar os três anos completos.

A terceira é a variação da categoria em pontos percentuais da receita corrente do ano-base. É a medida que permite somar as partes: mostra quanto da queda de receita foi absorvido por corte de pessoal, de custeio, de investimento, ou por queda da poupança corrente. Para a poupança corrente, que pode ficar perto de zero ou negativa, esta é a única medida que faz sentido; a variação percentual dela deve ser ignorada.

Além das categorias de despesa, o painel traz a poupança corrente (receita corrente menos despesa corrente) e o serviço da dívida (juros mais amortização), que o orientador sugeriu acompanhar nas crises.

## Saídas

O arquivo `passo1_ajuste_por_crise.csv` tem uma linha por estado, crise, ano da janela e categoria, com as três medidas. O `passo1_resumo_crises.csv` resume cada crise e categoria com a mediana e os quartis dos estados e o valor de Mato Grosso, usando a média dos anos da janela. As figuras em `dados/03_final/figuras/` mostram, para cada crise, a variação de cada categoria em todos os estados, com a mediana e Mato Grosso em destaque. O `passo1_bimestral_12m.csv` traz o acumulado em 12 meses por bimestre, para os gráficos de 2020.

## Como rodar

Depois da coleta (`01_siconfi.py dca`, `01_siconfi.py rreo` e `04_bcb.py`), rodar primeiro o diagnóstico:

```bash
python scripts/20_passo1_ajuste_crises.py --diagnostico
```

Ele mostra as colunas, os rótulos e as primeiras contas da DCA e do RREO de Mato Grosso, para conferir se os filtros do programa batem com o que a API de fato devolve. O programa foi escrito a partir da documentação e testado com dados simulados no formato da API, não com a API real. Os pontos a conferir estão todos no topo do arquivo: os códigos de natureza, os nomes das colunas de despesa liquidada, de receita bruta e de deduções, e o filtro que descarta as linhas intraorçamentárias para não contar duas vezes a mesma despesa. Se aparecer o aviso de linhas duplicadas no registro, é sinal de que algum desses filtros precisa de ajuste.

Depois do diagnóstico:

```bash
python scripts/20_passo1_ajuste_crises.py
```

## Limites

A comparação com o ano-base atribui à crise tudo o que mudou na janela, inclusive decisões que não tinham relação com ela, como reajustes salariais já contratados ou o fim de um ciclo de obras. A comparação com os outros estados ajuda a separar o que foi reação ao choque do que foi particularidade de cada um. Em 2020, a despesa e a receita foram infladas por transferências federais da LC 173/2020 e por gastos de saúde; o RREO bimestral e as transferências do Tesouro ajudam a separar esse efeito. Em 2022-23, a queda de ICMS veio de mudança de alíquota, não de recessão, e a compensação da LC 201/2023 entra em parte como receita, o que deve ser lembrado na leitura.
