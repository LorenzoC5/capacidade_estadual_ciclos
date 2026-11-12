# RREO de 2000 a 2014: coleta nos portais estaduais

A API do Siconfi só tem o RREO dos estados a partir de 2015. Os relatórios de 2000 a 2014 existem, mas estão espalhados pelos portais de cada estado, quase sempre em PDF. Este guia descreve como transformá-los numa série contínua com a API.

## O fluxo

O trabalho tem três etapas, cada uma com uma rotina.

`40_rreo_baixar.py` lê a URL de cada estado em `dados/00_referencia/rreo_portais.csv`, percorre a página, segue os links que parecem levar a relatórios da LRF e baixa os arquivos que parecem ser RREO, identificando ano e bimestre pelo texto do link. Tudo o que encontrou fica em `_manifesto.csv`, na pasta do estado, inclusive o que não baixou e por quê.

`41_rreo_extrair.py` abre cada arquivo, localiza o Balanço Orçamentário e o demonstrativo da RCL e lê as linhas principais: receita corrente, receita tributária, transferências correntes, receita de capital, operações de crédito, despesa corrente, pessoal, juros, outras despesas correntes, despesa de capital, investimentos, inversões e amortização. Para escolher a coluna certa, usa a identidade contábil da própria linha (previsão atualizada igual a realizado mais saldo, na receita; dotação atualizada igual a liquidado mais saldo, na despesa). Assim a rotina não depende da posição exata das colunas, que muda entre estados e anos. Quando a identidade não fecha, usa a posição padrão e marca a linha.

`42_rreo_serie_continua.py` junta os PDFs (até 2014) com a API (de 2015 em diante), calcula o fluxo de cada bimestre e roda as checagens de qualidade.

## Ordem de trabalho recomendada

O catálogo já tem endereços para Mato Grosso, Espírito Santo, Goiás, Minas Gerais, Paraná, Pernambuco, Rio de Janeiro, Rio Grande do Sul e Santa Catarina. Os demais estão marcados como “preencher”.

A sugestão é começar por Mato Grosso, sozinho, e só depois ampliar:

1. rodar `python scripts/40_rreo_baixar.py --uf MT --listar` e conferir no manifesto se os links de 2000 a 2015 apareceram; se não, aumentar a profundidade ou trocar a URL de partida no catálogo;
2. baixar os arquivos (`--uf MT`, sem `--listar`) e abrir alguns no visualizador para ver se são texto ou imagem;
3. testar a extração em um arquivo de cada fase do leiaute (por exemplo 2002, 2006, 2010, 2014), com `--arquivo ... --mostrar`, e conferir os números com o PDF aberto;
4. extrair o estado inteiro e rodar a rotina 42.

Para cada estado novo, o passo 1 é o que mais muda. Os passos seguintes costumam funcionar sem ajuste, a não ser nos primeiros anos da LRF.

## Validação

Baixe também o RREO de 2015 de cada estado, em PDF. Como 2015 também existe na API, a rotina 42 compara as duas versões, variável por variável, e emite alerta para diferenças acima de 1%. Esse é o teste mais confiável de que a extração está certa para aquele estado e aquele leiaute.

A rotina também acusa acumulados que caem ao longo do ano, o que costuma indicar coluna errada ou relatório retificado, e anos com bimestres faltando. Para os valores anuais, vale ainda comparar o 6º bimestre com a série anual da Execução Orçamentária de Estados, do Tesouro, quando ela estiver na pasta.

## Problemas esperados

Os primeiros anos (2000 a 2004) seguem leiautes anteriores ao Manual de Demonstrativos Fiscais, e alguns estados só publicavam no diário oficial. Nesses casos, pode ser mais rápido digitar as poucas linhas de interesse do 6º bimestre do que adaptar a extração.

PDFs escaneados não têm texto. A rotina 41 marca esses arquivos como `sem_texto`. Para eles, rodar OCR antes (por exemplo, `ocrmypdf --language por arquivo.pdf arquivo.pdf`) e extrair de novo; números lidos por OCR precisam de conferência manual.

Alguns relatórios vêm em milhares de reais. A rotina detecta a unidade pelo cabeçalho, mas vale conferir os primeiros resultados de cada estado.

Os rótulos mudaram ao longo do tempo: “Receita Tributária” virou “Impostos, Taxas e Contribuições de Melhoria”, por exemplo. As expressões usadas para cada variável estão no topo de `41_rreo_extrair.py` e podem ser ampliadas.
