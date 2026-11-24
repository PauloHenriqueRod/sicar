# Anexos opcionais e revisão dos cálculos

Cada cálculo corresponde a um servidor e vínculo. O RH seleciona a modalidade, confere os valores finais e confirma o direito antes de calcular.

| Etapa | Comportamento |
| --- | --- |
| Seleção | Cada modalidade apresenta seções específicas, como ficha financeira e ata de progressão. Cada seção aceita vários PDFs. Novas seleções se somam às anteriores. Trocar de modalidade limpa os anexos. As tabelas salariais pertencem ao cadastro. |
| Extração | Sem anexos, o formulário abre diretamente. Com anexos, uma requisição produz uma revisão, com situação e erros por arquivo. A categoria identifica a seção de envio. O conteúdo determina o leitor. Uma falha individual preserva os demais arquivos. Falha global permite continuar manualmente. |
| Associação | O operador confere pessoa, vínculo e papel de cada bloco. Na substituição, documentos do titular são apoio ao cálculo do substituto. A primeira ficha de progressão pode sugerir nome e matrícula em campos vazios quando a identificação é inequívoca. A associação continua sujeita à confirmação. |
| Conferência | Mostre os valores financeiros por competência, com pendências visíveis e fontes expansíveis. Todos os valores são editáveis. Campo desconhecido fica vazio e zero confirmado é preservado. Para substituir um valor em conflito, mostre o atual e a sugestão e registre a justificativa. |
| Cálculo | A API valida os dados finais enviados por `serializeReviewData`. Correções individuais de VB ou RT preservam a referência e o valor sugerido sem alterar o cadastro salarial. O motor usa o valor conferido. |

## Edições e rastreabilidade

O rascunho permanece em memória durante a navegação. Reextrações acrescentam evidências e preservam edições, inclusive campos apagados. Uma versão diferente do leitor produz nova proposta. A troca de sessão limpa os dados. O estado por arquivo indica espera, conclusão ou falha da resposta em lote.

`aplicacoes` associa campo e documento ao valor final. Em uma substituição, `valor_anterior` e `historico_aplicacoes` preservam a decisão precedente no histórico criptografado. A API exige justificativa e limita a trilha a 1.000 aplicações anteriores e 300 caracteres por valor. Para idempotência de registros antigos, histórico ausente equivale à lista vazia. Histórico preenchido participa da comparação.

Consulte os [leitores de documentos](extracao-documentos-rh.md), os [atos e portarias suportados](extracao-atos-portarias.md), as [regras de progressão](progressao-eventos.md) e a [memória do cálculo](memoria-calculos.md).

## Verificação

Os testes `App.extraction.test.tsx`, `App.workflow.test.tsx` e `ExtractionReview.test.tsx` cobrem anexos opcionais, associação, preservação das edições e falhas. No backend, `test_revised_value_reaches_engine_without_changing_document_or_global_table` em [test_extracao_documentos.py](../back-sgp/tests/test_extracao_documentos.py) verifica o valor revisado que chega ao motor.
