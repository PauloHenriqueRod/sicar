# Abono de permanência por parcelas

## Escopo

A regra `CONTRIBUICAO_ELEGIVEL_CONFIRMADA` exige vigência, fonte e confirmação do direito pelo RH. As rubricas 98002 (PSS regular) e 98004 (PSS do 13º) sugerem descontos a conferir. O RH mapeia as rubricas de abono recebido. Um código pode atender às duas categorias em parcelas distintas.

## API e compatibilidade

`POST /api/calcular` mantém `tipo_calculo="abono"`. Novos processos usam `dados_extraidos.matricula` e `dados_extraidos.abono`. O JSON Schema autenticado está em `GET /api/calculos/contratos/abono`.

O contrato anual legado continua aceito, com os valores de `total_geral` e `consolidado_anual` preservados. A resposta identifica `tipo_abono="resumo_legado_v1"` e esclarece que representa uma soma informada, sem comprovar direito, parcelas ou pagamentos anteriores. Históricos existentes não são migrados nem recebem meses presumidos pela posição na lista. A interface abre novos processos no contrato estruturado.

O novo resultado tem `tipo_abono="parcelas_v1"`, `parcelas`, `lancamentos_considerados`, `duplicidades`, `consolidado_anual`, `totais` e `saldo_parcelas_calculadas`. `total_geral` permanece como alias do saldo, em texto monetário. Valores exatos acompanham o devido, recebido e saldo; o consolidado anual é derivado das parcelas de direito, sem deslocá-las para o ano do pagamento.

O histórico cifrado e a auditoria são gravados juntos. A idempotência compara decimais por valor e identificadores como texto. Um histórico anterior não comprova pagamento.

## Direito e cobertura

`periodo_direito` identifica primeiro e último dia incluídos dos efeitos confirmados. `data_documento` e `data_requerimento` são rastreabilidade e não substituem esses efeitos. Cada documento identifica matrícula quando conhecida e vínculo confirmado. Documento incompatível exige correção ou remoção, sem mistura automática por matrícula igual.

Cada competência regular do intervalo exige uma parcela identificada. Mês ausente não representa contribuição zero. Para cada exercício do intervalo, `cobertura_13` exige inclusão de parcela, não aplicabilidade confirmada com justificativa ou pendência. Não se gera um direito de 13º automaticamente.

Cada parcela informa:

| Campo | Significado |
| --- | --- |
| `id` | Alvo explícito dos lançamentos associados. |
| `categoria` | REGULAR ou DECIMO_TERCEIRO; independente da natureza da folha. |
| `competencia_direito` | AAAA-MM da parcela regular. |
| `exercicio_13` | Ano de referência do 13º, sem mês fictício. |
| `periodo_referencia` | Mês completo regular ou ano completo de 13º. |
| `rubrica_abono` e `natureza_folha_devida` | Identificação do abono devido; natureza normalizada em maiúsculas. |
| `contribuicao` | PENDENTE, IDENTIFICADA ou ZERO_CONFIRMADO. |
| `recebimento` | PENDENTE, IDENTIFICADO ou NAO_HOUVE_CONFIRMADO. |
| `fonte_conferencia` | Origem da conferência de cada parcela, inclusive zeros e ausência de pagamento. |

Competências/exercícios repetidos são rejeitados. Referência fora do período de direito fica pendente; não é descartada silenciosamente. No direito parcial, exigir `valor_elegivel` com valor, fonte, localização e justificativa; não ratear automaticamente a PSS pelos dias. O elegível não pode superar a contribuição efetivamente conciliada. A confirmação final não substitui a revisão das lacunas de cada parcela.

Limites técnicos: 600 competências regulares, até 650 parcelas, 51 exercícios de cobertura, 2000 lançamentos, 40 mapeamentos e dez documentos. O resultado respeita o limite comum de 1 MiB. Esses limites não são limites legais.

## Descontos e pagamentos

`lancamentos` distingue CONTRIBUICAO e ABONO. Cada registro identifica categoria, parcela, competência da folha de origem, rubrica, natureza R/D, natureza da folha, identificador de folha, sequência, operação, valor, fonte e confirmação individual. A categoria REGULAR/13º não é deduzida de NORMAL/SUPLEMENTAR.

Operações:

- LANCAMENTO: desconto previdenciário D ou crédito de abono R, conforme papel conferido.
- COMPLEMENTO: aponta para `complementa_id`, mantendo papel, categoria, rubrica, parcela e natureza do original.
- ESTORNO: aponta para `estorna_id`, incluindo complemento. Valor é magnitude não negativa; direção depende da operação explicitamente confirmada, preservando R/D observado. Estornos acumulados não podem exceder o valor do alvo.

Competências e folhas de um acerto podem diferir das originais; o vínculo é explícito e essas informações não são reescritas. A origem e o acerto devem afetar a mesma parcela, rubrica, papel e categoria. Referência inexistente, circular ou incompatível gera pendência.

A deduplicação considera competência, rubrica, naturezas, identificador de folha e sequência. Valor, operação, categoria, papel e parcela precisam concordar; relacionamentos com originais são comparados após resolver aliases de segundas vias. Mesmo valor não comprova duplicidade; folhas distintas podem ter valores iguais. Arquivo de origem não transforma uma cópia em novo pagamento. Um mesmo evento não pode ser usado integralmente em duas parcelas.

## Fórmula e memória

Contribuição conciliada = descontos originais + complementos − estornos/restituições vinculados. Abono recebido = créditos originais + complementos − estornos vinculados. Se a parcela é integral e não há elegível manual, devido = contribuição conciliada; nos demais casos, devido = elegível explicitamente conferido. Saldo = devido − recebido.

Contribuição ou recebimento conciliado negativo exige revisão; não há zeramento automático. Pagamento maior que o devido preserva saldo negativo. Zero de contribuição e ausência de pagamento são estados explícitos e distintos de desconhecimento.

`Fraction` a partir de valores decimais acumula as parcelas sem arredondamentos intermediários. HALF_UP é aplicado na apresentação. Exemplos: devido regular 1000 e recebido suplementar de 250 em competência posterior produzem saldo regular 750; contribuição elegível de 13º de 300 permanece separada, resultando em saldo total 1050. Duas parcelas exatas de 0,005 exibem 0,01 cada, mas o total exato apresentado é 0,01.

## Extração e interface

O leitor apresenta até 200 observações por documento, com linha e coluna quando disponíveis. Preserva sequências e sinais de 98002, 98004 e candidatos de abono. Ignora a coluna TOTAL e sinaliza excedentes, natureza desconhecida ou leitura incompleta. O RH pode associar fichas de vários anos ao mesmo vínculo ou preencher as parcelas manualmente.

Cada observação exige decisão: vincular a lançamento ou descartar com justificativa. Para utilizá-la, os dados revisados precisam concordar com o lançamento associado. Levar à revisão mantém o sinal no dado observado e copia a magnitude para o campo monetário, sem preencher papel, categoria, operação ou parcela automaticamente. Uma observação negativa não pode gerar lançamento original/complemento positivo silenciosamente: exige estorno vinculado ou `correcao_sinal_confirmada=true` com justificativa específica conferida pelo RH. Estornos explicitamente vinculados podem seguir a convenção de sinal da fonte, sem correção adicional. Editar o valor ou a identificação financeira da observação retira a confirmação da correção do sinal.

Reaplicar uma observação preserva o lançamento editado. Mudanças invalidam a confirmação final e o resultado. `tests/test_abono_parcelas.py` reúne exemplos de regular/13º, parcelas parciais, acertos, sinais, duplicidades e arredondamento.
