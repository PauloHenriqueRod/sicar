# Apuração comum de períodos, eventos e parcelas

O núcleo `periodos_v1` calcula parcelas mensais, mudanças de estado e recebimentos. A [progressão](progressao-eventos.md) compara origem e destino em cada segmento. [Abono](abono-parcelas.md) e [rescisão](rescisao-periodos.md) têm regras próprias de cobertura e conciliação.

O RH confirma o período, as rubricas e as evidências. Na [revisão](fluxo-revisao-calculos.md), a interface indica o campo ou grupo com erro. Edições exigem nova confirmação e invalidam o resultado anterior.

## Datas e cobertura

| Campo | Significado |
| --- | --- |
| `periodo.inicio` | Primeiro dia incluído na apuração. |
| `periodo.ultimo_dia_considerado` | Último dia incluído, confirmado pelo RH; não é inferido de uma data de rescisão. |
| `data_documento` | Data documental de rastreabilidade; não desloca efeitos financeiros. |
| `data_implantacao` | Data em que a alteração foi implantada; não substitui o início dos efeitos. |
| `eventos[].efeitos_financeiros` | Primeiro dia em que as alterações declaradas naquele evento se aplicam. |

O estado inicial representa a situação no primeiro dia. Eventos devem ter efeitos dentro do intervalo. Datas documentais e de implantação podem ser posteriores, sem alterar a contagem. Datas de entrada usam `AAAA-MM-DD`, sem conversão de números/anos isolados em datas.

Internamente, os limites são ordinais em intervalos semiabertos `[início, último+1)`. A resposta apresenta datas inclusivas. A divisão inclui viradas de mês/ano, eventos, início/fim de referências confirmadas e interrupções. O calendário é o real: 28, 29, 30 ou 31 dias no divisor mensal. Cada dia aparece uma vez na linha do tempo; rubricas distintas podem naturalmente incidir sobre o mesmo segmento.

Interrupções sobrepostas formam uma exclusão única de dias, sem subtração duplicada. Elas devem ser recortadas ao intervalo pelo operador. Os segmentos interrompidos permanecem na trilha com `dias_computados=0`, permitindo conferir o intervalo integral.

## Estado, eventos e tabelas

O estado contém posição qualificada, jornada, titulação e percentuais explícitos de IQ, adicional e anuênio quando utilizados. Os campos de posição reutilizam o contrato descrito em [Referências salariais](referencias-salariais.md). Alterar posição ou jornada exige um novo objeto `posicao` completo.

Os eventos alteram somente os campos presentes em `alteracoes`. Duas alterações do mesmo campo na mesma data são rejeitadas; alterações de campos distintos na mesma data são aplicadas em conjunto, independentemente da ordem dos eventos. Cada evento identifica sua regra/ato com identificador, versão e fonte.

Ao mudar a posição, bases manuais anteriores são retiradas. Ao mudar a titulação, a RT manual anterior é retirada. É possível fornecer novas bases manuais explicitamente na mesma data. A ausência de `vb_manual`/`rt_manual` em uma alteração mantém a situação anterior; o valor **`null` explícito** remove a base manual e volta à consulta do cadastro. Essa distinção é preservada no histórico e na idempotência.

VB e RT confirmados são carregados em uma única consulta com todas as posições utilizadas. Cada segmento precisa estar integralmente coberto pela referência correta; lacunas ou RT incompatível geram pendência e impedem salvar um resultado parcial. VB/RT não são selecionados apenas por ano, e jornadas não compartilham chave. Bases manuais exigem valor, fonte e página/aba/linha, com prioridade explícita sobre a consulta; não tornam um registro do cadastro confirmado.

Fórmulas disponíveis por rubrica:

| Fórmula | Valor mensal antes da proporcionalidade |
| --- | --- |
| `VB` | VB do estado/tabela. |
| `RT` | RT docente da titulação explícita. |
| `VB_RT` | Soma do VB e da RT compatível. |
| `IQ_SOBRE_VB` | VB × percentual de IQ / 100; exige posição TAE. |
| `ADICIONAL_SOBRE_VB` | VB × percentual do adicional / 100, informado pelo RH. |
| `ANUENIO_SOBRE_VB` | VB × percentual de anuênio / 100, informado pelo RH. |
| `VALOR_MENSAL` | Valor mensal com fonte própria, conferido manualmente. |

Percentual ausente não é zero confirmado. IQ e RT permanecem distintos. Não há aquisição automática de anuênio, escolha automática de adicional, soma de opções de CD/FG/FCC ou determinação de uma base legal a partir da fórmula escolhida. Quando a base necessária difere das fórmulas oferecidas, o RH pode declarar o valor mensal com fonte ou utilizar a rotina específica.

Cada segmento mantém estado, eventos aplicados, interrupções, referências de regra e referências de tabela/manuais. Os parâmetros e valores da referência utilizada são preservados no snapshot, para que edições futuras do cadastro não recalculem o histórico.

## Parcela, competência e natureza da folha

Há uma fórmula devida por `(rubrica, natureza_folha, natureza_rubrica)` na apuração. Repetir essa chave é erro de contrato, evitando calcular duas vezes a mesma rubrica/dia. Códigos numéricos são normalizados, por exemplo `742` e `00742` usam `00742`.

`natureza_rubrica` distingue `R` (rendimento) e `D` (desconto). `natureza_folha` é um identificador explícito da classificação da folha, conforme a fonte, sem inferência pelo nome do documento. A consolidação apresenta **devido, recebido e saldo** para cada competência `AAAA-MM`, rubrica e ambas as naturezas. Os totais líquidos consideram rendimentos menos descontos; valores por rubrica mantêm sua natureza explícita. Folhas de naturezas distintas permanecem em linhas distintas.

Um recebimento exige `id`, competência, rubrica, naturezas, `identificador_folha`, `sequencia`, operação, valor e origem documental. A identidade financeira é a combinação de competência, rubrica, naturezas, folha e sequência; a página/PDF de origem não cria um pagamento novo.

- Mesmo ID ou mesma identidade financeira com os mesmos dados: duplicidade relatada e desconsiderada na soma.
- Mesmo ID/identidade com valor, operação ou alvo de estorno divergente: pendência; não sobrescreve nem escolhe silenciosamente um valor.
- Complementação: operação `COMPLEMENTO` com folha/sequência legitimamente distintas; é contada mesmo na mesma competência/rubrica.
- Estorno: operação `ESTORNO`, valor positivo e `estorna_id` do pagamento original. Reduz recebido. Exige mesma competência/rubrica/naturezas, referência a pagamento/complemento e soma de estornos não superior ao original. Duplicatas documentais do alvo são reconciliadas ao mesmo lançamento.

Os aliases dos pagamentos são resolvidos antes de comparar estornos, independentemente da ordem dos documentos. Cópias do mesmo estorno que apontam para aliases do mesmo pagamento são desconsideradas uma vez; alvos financeiramente distintos continuam gerando conflito. A lista de lançamentos considerados preserva a ordem recebida.

Recebimentos devem pertencer às competências da apuração. O motor não rateia automaticamente o recebido de uma ficha em mês parcial: o operador seleciona/confirma os pagamentos correspondentes ao escopo. `recebidos` é obrigatório, ainda que `[]`; a lista vazia, acompanhada da confirmação do RH, declara ausência de pagamentos identificados, em vez de omitir a verificação.

## Precisão e saída

Entradas monetárias aceitam números JSON ou textos decimais; na interface, ponto decimal e vírgula brasileira são normalizados sem conversão para `Number`. O contrato valida Decimal finito, não negativo, até 12 casas e os limites do cadastro. Booleanos não são valores financeiros.

A proporcionalidade é `valor_mensal × dias_computados / dias_reais_mes`. O núcleo converte Decimal diretamente em `Fraction`, preservando razões exatas e somando sem arredondamento intermediário. O arredondamento final de cada saída monetária aplica meio centavo para longe de zero, equivalente a `ROUND_HALF_UP`. Os subtotais exibidos são apresentações; não alimentam o total.

Exemplo independente: `0,01 × 14/28 + 0,01 × 15/30 = 0,01`. Cada parcela pode aparecer como `0,01`, mas somar esses valores apresentados produziria `0,02`, que não é o total devido. Numerador/denominador também são apresentados para rastrear a fração anterior ao arredondamento.

Valores monetários deste contrato e da progressão por eventos são **textos decimais com duas casas**, incluindo `total_geral_a_receber`, `devido`, `recebido` e `saldo`. Histórico, tela e PDF preservam esses centavos sem passagem por ponto flutuante binário. Os contratos legados mantêm sua representação pública. A política geral permanece `decimal_half_up_final_v3`; a trilha deste modo identifica `aritmetica_periodos=racional_exata`.

## API e contrato

Reutiliza `POST /api/calcular`, autenticado, com `tipo_calculo="apuracao_periodos"`, `dados_extraidos.apuracao` e chave UUID de idempotência opcional. `GET /api/calculos/contratos/apuracao-periodos`, também autenticado, fornece o JSON Schema gerado pelo modelo vigente.

Os índices de classe, nível e titulação do histórico usam o **estado inicial declarado** da apuração. Para docentes, classe/nível docente; para TAE, classe de exibição `Técnico Administrativo` e padrão TAE no índice de nível, mantendo classificação e capacitação distintas no snapshot. As mudanças posteriores permanecem nos segmentos. Campos superiores legados não substituem esses índices; registros históricos existentes não são regravados.

Exemplo mínimo inteiramente sintético:

```json
{
  "tipo_calculo": "apuracao_periodos",
  "dados_extraidos": {
    "matricula": "DEMO-1",
    "apuracao": {
      "periodo": {"inicio": "2024-02-01", "ultimo_dia_considerado": "2024-02-29"},
      "estado_inicial": {
        "posicao": {
          "carreira": "TAE", "vinculo": "EFETIVO", "jornada": "40H",
          "versao_carreira": "SINTETICA", "classificacao_tae": "E", "padrao_tae": 1
        },
        "titulacao": "N/A",
        "vb_manual": {"valor": "2900", "fonte": "Tabela sintética conferida", "localizador": "Aba 1, linha 2"}
      },
      "rubricas": [{
        "rubrica": "1", "natureza_folha": "NORMAL", "natureza_rubrica": "R", "formula": "VB",
        "regra": {"identificador": "REGRA-SINTETICA", "versao": "1", "fonte": "Regra sintética conferida"}
      }],
      "recebidos": [],
      "conferido_pelo_rh": true
    }
  }
}
```

Resultado esperado: `total_geral_a_receber="2900.00"`, uma competência e 29 dias computados. `conferido_pelo_rh` aceita somente o booleano `true`. Regras e fontes são declarações conferidas do operador; o sistema não confirma sua autenticidade.

Erros de contrato retornam 400 com localização. Pendências operacionais incluem `referencia_salarial_pendente`, `rt_pendente`, `percentual_pendente`, `lancamento_conflitante`, `estorno_sem_origem`, `estorno_incompativel`, `estorno_excedente` e limites de recursos. O histórico não é salvo quando a apuração fica pendente. Repetir a mesma chave com dados alterados retorna 409, inclusive ao trocar campo ausente por remoção manual explícita.

Na idempotência, os campos Decimal são comparados por valor: `300`, `300.0` e `"300.00"` reutilizam o mesmo histórico e resultado. Isso também vale para percentuais e valores de eventos, rubricas e recebimentos. Matrículas, sequências, versões de regras e demais textos continuam com comparação exata; diferenças monetárias reais são rejeitadas mesmo quando o arredondamento final produziria o mesmo valor apresentado.

## Limites e verificações

Os fluxos de [exercícios anteriores](exercicios-parcelas.md) e [substituição](substituicao-periodos.md) reutilizam o calendário com contratos específicos. `ADICIONAL_CONFIRMADO` compartilha a reserva de cobertura com [adicionais e progressão](adicionais-explicitos.md).

Até 600 competências, 100 eventos, 100 interrupções, 20 rubricas e 2000 recebimentos; no máximo 2000 referências candidatas, 2000 parcelas devidas e 1 MiB de resultado. O limite de corpo da API continua 1 MiB. Relatórios mantêm os limites anteriores de dados, páginas e tempo; uma apuração extensa pode precisar ser dividida para exportação, sem elevar limites globais.

`tests/test_apuracao_periodos.py` cobre calendário, eventos simultâneos, referências, conciliação, arredondamento e API/PDF. A integração com PostgreSQL é verificada separadamente no CI.

Fontes técnicas consultadas em 27/10/2026: documentação oficial de [Fraction](https://docs.python.org/3.13/library/fractions.html), [calendário](https://docs.python.org/3.13/library/calendar.html) e [datas/ordinais](https://docs.python.org/3.13/library/datetime.html#datetime.date.toordinal). Elas fundamentam os mecanismos de representação e calendário, não a concessão de benefícios. Metadados bibliográficos também foram registrados no catálogo local excluído do Git.
