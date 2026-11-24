# Adicionais ocupacionais e reflexos explícitos

## Escopo e fluxo

O resultado `tipo_adicionais="concessoes_v1"` usa a [apuração por períodos](apuracao-periodos.md) e compartilha a cobertura com a [progressão](progressao-eventos.md). O RH confere a concessão, a matrícula e a regra. Os anexos são opcionais.

A ficha financeira informa valores observados. `percentual_adicional_sugerido` representa somente a razão entre o adicional e o VB inequívocos na mesma competência. Essa sugestão aparece como anotação; não preenche percentual confirmado, não ativa rubrica nem cria concessão. O contrato legado de extração de progressão deixa o percentual ausente para revisão quando só há essa razão. Percentuais expressamente informados no texto continuam distinguíveis da razão calculada.

## Contrato

`POST /api/calcular`, com `tipo_calculo="insalubridade"`, aceita o novo objeto `dados_extraidos.adicionais`. O nome técnico do tipo é mantido por compatibilidade. O JSON Schema autenticado está em `GET /api/calculos/contratos/adicionais`; a progressão usa `GET /api/calculos/contratos/progressao`.

O plano contém `periodo`, `estado_inicial`, `eventos`, uma `rubrica` mensal em `rubricas`, `interrupcoes`, `reflexos`, `recebidos` e `conferido_pelo_rh=true`. A posição salarial qualificada continua obrigatória, inclusive para base manual, para identificação do contexto. O estado pode conter `adicional`:

| Campo | Significado |
| --- | --- |
| `identificador` | Identificação estável da concessão, igual nos fluxos de adicional e progressão. |
| `especie` | `INSALUBRIDADE`, `PERICULOSIDADE`, `IRRADIACAO`, `RAIOS_X` ou `OUTRO` com descrição. Não define automaticamente percentual/base. |
| `percentual`, `percentual_confirmado` | Percentual decimal e confirmação explícita, separados da sugestão extraída. |
| `inicio_vigencia`, `fim_vigencia` | Primeiro e último dia inclusivos da concessão; fim é opcional. Publicação não é convertida em início de efeitos. |
| `base` | Tipo `VB`, `VB_RT` ou `VALOR_CONFIRMADO`, mais `confirmada=true`. |
| `base.valor_manual` | Somente em `VALOR_CONFIRMADO`: valor decimal, fonte e localizador obrigatórios. |
| `regra` | Identificador, versão, fonte, vigência e `confirmada=true`. |

A fórmula mensal é `ADICIONAL_CONFIRMADO`. Em `VB_RT`, VB e RT são consultados e registrados separadamente, com jornada, posição, titulação e vigência compatíveis. RT não é incorporada em base `VB`; RT ausente não impede esse caso. Base `VB_RT` é incompatível com TAE. Base manual não se mistura com componentes de tabela. Não se informa VB/RT manualmente no estado inicial deste fluxo; uma base distinta exige a fonte própria em `VALOR_CONFIRMADO`.

A concessão é única por estado: o plano aceita apenas uma fórmula `ADICIONAL_CONFIRMADO`, inclusive na apuração genérica. Repeti-la sob outro código, natureza da folha ou natureza de rubrica é erro de contrato, não uma segunda parcela devida. Complementações legítimas permanecem discriminadas como recebimentos, sem repetir a fórmula do principal.

Eventos `ADICIONAL`, `POSICAO` e `RT` alteram respectivamente a concessão completa, a posição completa e a titulação. Na progressão, `ADICIONAL` também aceita a concessão completa, separada dos demais eventos. Cada evento declara regra histórica que cobre seus efeitos financeiros. Interrupções declaram regra que cobre todos os seus dias.

A regra da rubrica mensal cobre a janela apurada. A regra da concessão cobre os segmentos ativos. Mudanças de mês, tabela, evento e vigência dividem os segmentos sem repetir dias. Fora da vigência conhecida da concessão, o adicional é zero; sem início confirmado, a vigência é pendente. O calendário usa dias reais, inclusive fevereiro bissexto. O motor acumula frações exatas e aplica meio centavo para cima somente ao apresentar o resultado monetário.

## Reflexos e conciliação

`FERIAS_UM_TERCO` e `DECIMO_TERCEIRO` exigem avos inteiros explícitos de 1 a 12, competência, data-base, rubrica, naturezas e regra histórica. O componente do fluxo de adicionais é exclusivamente `ADICIONAL_CONFIRMADO`; na progressão podem coexistir componentes distintos. Não se deduz quantidade de férias ou 13º de nomes de meses, competência, número de segmentos ou existência de rubrica.

Quando há componente de adicional, também são obrigatórios:

- `origem`: o identificador da concessão usada na data-base;
- `periodo_referencia`: primeiro e último dia inclusivos do direito ao reflexo, conferidos pelo RH; pode anteceder a janela financeira;
- `pagamentos_anteriores`: lista explícita de IDs de `recebidos`, inclusive `[]` quando nenhum foi identificado e isso foi conferido.

O reflexo usa a base mensal na data-base escolhida pelo RH: `base × avos / 36` para o terço de férias e `base × avos / 12` para 13º. Na progressão, a base é a diferença entre destino e origem, não a remuneração integral. O período de referência discrimina o direito; ele não substitui os avos nem gera contagem automática.

Pagamentos devem corresponder à competência, rubrica e naturezas do reflexo. Cada pagamento é vinculado uma única vez; cópias identificadas pelo núcleo comum apontam para o lançamento canônico. Complementações e estornos explícitos são preservados. O resultado discrimina fonte, competência, folha, sequência, operação e valor dos pagamentos anteriores. A dedução ocorre uma única vez na conciliação comum; a lista do reflexo é rastreabilidade, não outra dedução. Pagamento de reflexo não vinculado gera pendência. Principal e reflexos usam rubricas/naturezas discriminadas; períodos sobrepostos de reflexos da mesma origem/tipo são rejeitados mesmo com datas-base diferentes.

## Separação entre os fluxos e revisões

`apurar_principal=false` na rubrica de adicional reserva esse componente somente como apoio aos reflexos. Não calcula o principal, e não aceita recebimentos do principal excluído. O motor exige a base/regra do apoio somente nos segmentos que contêm datas-base de reflexos. Uma concessão incompleta que não é utilizada não bloqueia um caso independente de VB/IQ/RT; não há salário ou base presumidos para contornar pendências.

A reserva é comum a adicionais, progressão e apuração por períodos. A chave reúne matrícula normalizada, identidade da concessão, espécie da parcela e intervalo. Principal reserva os dias ativos e reflexos reservam o período declarado. Sobreposição retorna `adicional_ja_apurado`, mesmo sob outra rubrica. Cabe ao RH reconhecer atos cadastrados com IDs diferentes.

Na progressão, a reserva inclui concessões da origem e do destino, inclusive em cessação ou troca de concessão. Um mesmo intervalo da mesma concessão conta uma vez.

O índice usa HMAC, sem matrícula/identificação do ato em texto claro, derivado da chave persistente de criptografia. PostgreSQL usa inserção tolerante a conflito e bloqueio de escopos em ordem determinística; SQLite serializa a escrita. Reserva, histórico cifrado e auditoria pertencem à mesma transação. A chave de idempotência permite repetir a mesma tentativa sem nova reserva. A rotação de `ENCRYPTION_KEY` exige também reconstrução controlada desses índices a partir dos históricos; não a altere isoladamente.

Para corrigir um cálculo, informe `dados_extraidos.substitui_historico_id` do registro ativo da mesma matrícula, observadas as permissões. A revisão substitui **toda** a cobertura em uma única transação. Inclua todas as parcelas que devem permanecer. Na edição do resultado, a interface vincula o histórico e exige nova confirmação. Entre fluxos, informe o ID explicitamente. Consulte a [memória de cálculo](memoria-calculos.md).

## Persistência, compatibilidade e recuperação

Na inicialização já existente com `Base.metadata.create_all`, são criadas aditivamente `escopos_adicionais`, `coberturas_adicionais` e `revisoes_calculos`. Não há alteração de coluna nem regravação de históricos. O teste em SQLite temporário cria essas tabelas duas vezes e verifica preservação do histórico anterior. Antes de atualizar um ambiente real, faça backup consistente do banco e da chave persistente, aplique primeiro em cópia e confira as três tabelas e a exportação das versões ativas. Para recuperação, interrompa as escritas e restaure conjuntamente banco e chave do mesmo backup; remover somente o índice perde a proteção contra duplicidade e não é procedimento de recuperação.

Históricos anteriores sem identificação comprovada da concessão não recebem cobertura retroativa presumida. Contratos agregados anteriores (`valores_mensais` e progressão legada) permanecem aceitos para compatibilidade estrutural; não oferecem o novo rastreamento de concessão entre fluxos e exigem conferência manual. No contrato `valores_mensais`, os valores são somados sem multiplicadores automáticos por rótulo de mês: textos como “OUTUBRO” ou “NOVEMBRO E 13º” não concedem reflexos. Esta é uma alteração deliberada do comportamento anterior; reflexos devem ser migrados para eventos explícitos. Históricos salvos não são recalculados. A interface inicia novos processos no contrato explícito. A proteção não equivale a detecção automática de pagamento ou de duplicidade de todo o acervo legado.

## Verificação

`tests/test_adicionais_explicitos.py` usa concessões, fichas e tabelas sintéticas com esperados independentes. Exemplos: VB 2.900 × 10% = 290,00; VB 2.900 + RT 580, sobre ambos a 10% = 348,00; mudança em fevereiro/2024 com dez dias de base VB e onze de VB+RT = 232,00; base manual 1.234,55 a 10% = 123,46. Há casos de pendências condicionais, avos ausentes, pagamentos anteriores, idempotência, cobertura entre fluxos e revisão.

Os testes React cobrem sugestão, conferência e revisão. `integration_tests/test_additional_coverage_postgres.py` verifica o bloqueio entre transações em PostgreSQL.
