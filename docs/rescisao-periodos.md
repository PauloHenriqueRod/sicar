# Rescisão por contrato, datas e pagamentos

## Escopo e contratos

O novo contrato calcula o **saldo das parcelas calculadas** de salário final, férias, terço e 13º. Não representa líquido completo nem determina o direito. Modalidade suportada: professor substituto; motivos: término contratual ou rescisão antecipada quando a regra conferida pelo RH cobre a hipótese. `OUTRO` gera pendência.

- `POST /api/calcular`: mantém `tipo_calculo="rescisao"`; o novo corpo usa `dados_extraidos.matricula` e `dados_extraidos.rescisao`.
- `GET /api/calculos/contratos/rescisao`: JSON Schema autenticado.
- `POST /api/calculos/rescisao/previa`: recebe matrícula e plano, devolve sugestões e correções adotadas sem gravar histórico. Campos presentes precisam satisfazer seus contratos, inclusive fontes/documentos; confirmação final não é exigida para a prévia.
- Resultado: `tipo_rescisao="periodos_v1"`, `saldo_parcelas_calculadas`, parcelas, memória exata e rastreabilidade. `total_liquido_a_receber` permanece como alias de compatibilidade e não é repetido na apresentação.

O corpo agregado anterior continua aceito, sem conversão silenciosa em períodos. Históricos existentes não são recalculados. O leitor legado mantém sua estrutura; o worker envia `fontes_rescisao` separadamente de `dados_extraidos`. A interface inicia novos processos no contrato por períodos, sem converter quantidades agregadas em pagamentos confirmados. A idempotência compara decimais por valor. Não há migração nem nova tabela.

## Datas e quantidades

| Campo | Significado |
| --- | --- |
| `contrato_id` | Identidade do contrato conferida pelo RH. |
| `inicio_exercicio` | Início efetivo do contrato; no cadastro, usar o contexto CARGO/EMPREGO. |
| `data_termino` e `sentido_termino` | A_PARTIR_DE exclui a própria data; INCLUSIVO a inclui. |
| `ultimo_dia_trabalhado` | Último dia de trabalho efetivo, confirmado. |
| `ultimo_dia_considerado` | Limite financeiro confirmado das parcelas. |
| `justificativa_ultimo_dia` | Obrigatória quando o limite diverge da sugestão documental. |

Rescisão a partir de 31/08/2026 sugere considerar até 30/08. A partir de 01/09 mantém agosto como competência salarial. O último dia trabalhado não pode ser posterior ao considerado. A data excluída não pode ser reincluída sem corrigir o significado do término.

Férias contam aniversários mensais a partir do dia original de exercício; fração final inclusiva com pelo menos 15 dias gera mais um avo. Para início em 29/30/31, exigir política `LIMITAR_DIA_AO_MES` confirmada: menor entre dia original e último dia do mês, preservando a âncora original nos meses seguintes. Sem política o caso fica pendente.

A sugestão salarial conta a interseção contrato/competência final; o divisor é o calendário real. O 13º sugerido conta meses do ano final com pelo menos 15 dias considerados. `correcoes` admite dias salariais, avos adquiridos de férias e avos de 13º, sempre com inteiro e justificativa. A memória preserva sugestão, valor adotado e motivo. Confirmar a mesma quantidade sugerida mantém os dias de cada segmento, mesmo com bases distintas. Não há distribuição automática de quantidades efetivamente alteradas entre bases salariais distintas.

Não existe teto automático de 24 avos. A regra informa ausência de teto confirmada ou limite explícito. Exceder o limite gera pendência, sem truncamento. O contrato legado com mais de 24 avos também exige revisão no novo contrato. Limite técnico: 1200 meses/avos; não é um limite legal. A regra precisa estar confirmada, cobrir o período e incluir o motivo.

## Bases e precisão

`salarios` contém faixas inclusivas cobrindo o mês final sem lacunas/sobreposições. Cada base usa exclusivamente `valor_manual` com fonte/localizador ou referência salarial qualificada, mais titulação explícita (`N/A` quando não houver RT). As tabelas oficiais MGI/RT são reutilizadas pelo cadastro; não são anexos obrigatórios em cada cálculo.

Referências suportadas: carreira docente, vínculo TEMPORARIO/SUBSTITUTO/PROFESSOR_SUBSTITUTO, jornada e posição compatíveis. Mudanças de vigência dividem a faixa automaticamente; VB e RT permanecem separados na rastreabilidade. Referência ausente/ambígua não gera salário presumido. Bases de férias e 13º são separadas e exigidas somente nas parcelas dependentes.

Intervalos e conciliação reutilizam os serviços da issue #20. A aritmética acumula Fraction a partir de Decimal. HALF_UP é aplicado somente na apresentação monetária; frações exatas acompanham a memória. A soma dos valores apresentados pode diferir do saldo consolidado.

## Rubrica 750 e recebimentos

`pagamentos_ferias` registra competência, rubrica 00750, naturezas, folha, sequência, operação, valor, origem/localizador, período aquisitivo, avos e base pertinente do terço.

- Original: de 1 a 12 avos quitados e período associado.
- Complemento: aponta para `pagamento_original_id` e informa zero novos avos.
- Estorno: aponta para `estorna_id` e explicita avos revertidos; o sinal/valor não determina avos automaticamente. Pode reverter pagamento ou complemento, inclusive por identificador de segunda via. Estorno de complemento informa zero avos e reduz o valor pago do grupo original, respeitando o limite monetário do complemento estornado.
- Cópias: conciliadas pela identidade financeira; divergências de período, avos ou base geram pendência.
- Originais com períodos sobrepostos precisam de revisão; não se contam duas concessões automaticamente.

Acertos devem apontar para o mesmo período e não podem declarar base conflitante com a do original. O RH confere a base pertinente no original, preservando sua fonte. Pagamentos devem pertencer às competências do contrato considerado; pagamentos posteriores ao mês final não são assimilados automaticamente.

Saldo de avos = adquirido menos quitado após estornos. Se positivo, principal = base × avos / 12 e terço = principal / 3. Se negativo, principal zero; alocar excedentes aos pagamentos mais recentes e calcular a devolução com a base pertinente. A ordem usa competências distintas, datas de pagamento informadas para todos os originais ativos ou `ordem_devolucao` explicitamente conferida (maior = mais recente). Empates geram pendência, sem ordenar arbitrariamente por ID ou início do período aquisitivo. Pagamento integralmente estornado pode ser reemitido para o mesmo período sem duplicar avos ativos. Base ausente ou devolução superior ao efetivamente pago após acertos gera pendência; nunca substituir automaticamente pela base atual.

`recebidos` contém os pagamentos das parcelas finais, separado do histórico 750. Salário/férias finais identificam a competência final; antecipações de 13º podem pertencer a competências anteriores do mesmo ano/contrato. Folhas NORMAL/SUPLEMENTAR permanecem distintas na memória por competência/rubrica/naturezas. A natureza da folha devida é normalizada como a recebida (sem espaços externos, em maiúsculas), evitando separar normal/NORMAL. Cópias e estornos usam a conciliação comum. A rubrica 750 não é deduzida novamente como pagamento final.

## Documentos e leitura

Podem ser associadas fontes de anos diferentes ao mesmo contrato. O RH confirma pessoa, vínculo e contrato em cada documento. Matrícula divergente ou contrato incompatível exige correção ou remoção.

| Fonte | Leitura e uso |
| --- | --- |
| Ficha financeira | Observações das rubricas 742, 750, 772, 82696 e 82407 por competência, natureza, sequência e coluna; TOTAL não é pagamento. |
| Cadastro | Candidato de exercício no contexto CARGO/EMPREGO; não usar exercício de outro contexto. |
| Término/contrato/aditivo | Campos explicitamente rotulados de data e contrato; significado e motivo são confirmados manualmente. |
| CACOFERIAS | Cabeçalhos INICIO/DIAS/PARCELA, linhas delimitadas ou colunas textuais reconhecidas, datas brasileiras/DDMMMYYYY. Programação não comprova gozo nem pagamento. |
| Tabelas oficiais MGI/RT | Cadastro confirmado de referências, separado do upload individual. |

O RH pode preencher os dados manualmente ou revisar candidatos do leitor. Ao aplicar um pagamento, confirme operação, folha, avos e período. Sinal negativo exige interpretação. A reextração conserva as edições. O leitor apresenta até 100 campos e 200 pagamentos por documento e sinaliza excedentes. Veja os [layouts e limites](extracao-documentos-rh.md).

## Exemplos independentes

16/01/2025 até 30/08/2026: 19 aniversários e fração final de 15 dias = 20 avos. Quitação pertinente de 12 deixa 8; quitação de 24 deixa −4, com principal zero. Se a base pertinente do último terço for R$ 5.400, devolução = 5.400 × 4 / 36 = R$ 600,00.

Salário de R$ 3.100, 15 dias em agosto, recebimento integral: devido salarial = 3.100 × 15 / 31 = R$ 1.500; saldo salarial = −R$ 1.600. As outras parcelas continuam discriminadas.

`tests/test_rescisao_periodos.py` cobre exemplos, aniversários/14–15 dias, mudanças salariais do cadastro, pagamentos, limites, pendências, documentos sintéticos, prévia, idempotência e PDF. Testes React cobrem revisão manual, precisão, prévia obsoleta, associação e agrupamento. SQLite não demonstra concorrência PostgreSQL; o cadastro reutiliza seus controles existentes. Nenhum teste utiliza arquivos reais do RH.
