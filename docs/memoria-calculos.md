# Memória de cálculo e versões

Consulta e exportação utilizam entradas e resultado salvos. A conferência do direito e das fontes cabe ao RH.

## Snapshot preservado

O envelope existente `versao=2` conserva `dados_extraidos` (entradas finais), `dados_utilizados` (identificação e dados efetivamente usados), `resultado_calculo` e `rastreabilidade`. Entradas decimais exatas, versão do motor, calendário e política de arredondamento ficam na rastreabilidade. Os fluxos estruturados também conservam regras, tabelas, segmentos e conciliação de devido, recebido e saldo. Sugestões, documentos de origem, aplicações e correções seguem no contrato de revisão quando fornecidos.

A aplicação preserva o registro cifrado original. O recálculo cria um registro vinculado. Backups, chave e controle administrativo do banco continuam necessários.

## Consulta e recálculo

`GET /api/historico/{id}` exige sessão e o mesmo escopo de acesso da listagem/exportação: usuários comuns consultam seus registros; administradores e desenvolvedores têm o acesso global existente. Ausência e falta de permissão retornam a mesma resposta 404. A resposta usa `Cache-Control: no-store` e contém o snapshot original, `anterior_id`, `substituido_por`, `pode_recalcular` e `entradas_recalculo`. Estas últimas preferem a cópia decimal exata da rastreabilidade, com fallback para entradas salvas em snapshots anteriores sem essa cópia.

Em **Histórico → Ver memória**, o operador consulta fontes, entradas, resultado e versão. **Preparar recálculo** cria um rascunho com `substitui_historico_id` e exige nova conferência. Outro recálculo não substitui um rascunho pendente.

O recálculo vincula o último histórico acessível do servidor. Cada registro admite um sucessor. Abono, rescisão e exercícios anteriores exigem também o mesmo tipo. Nos fluxos de adicionais, a operação inclui as reservas de cobertura. Novo histórico, vínculo e auditoria são gravados na mesma transação.

Registros antigos com apenas o resultado continuam consultáveis, com versão desconhecida quando ausente. Recálculo e exportação vinculada exigem entradas completas.

## Equivalência e exportação

`POST /api/exportar-pdf` recebe apenas o ID do histórico. O PDF traz o resultado salvo, o identificador e a versão do motor. Um snapshot completo substituído pode ser exportado identificado como **VERSÃO HISTÓRICA SUBSTITUÍDA PELO #…**. Na substituição, o relatório reorganiza os componentes para exibição.

A política `decimal_half_up_final_v3` soma com a precisão interna e arredonda somente na finalização monetária. A nota de arredondamento salva é mostrada junto ao resultado e à memória, e segue na exportação. Exemplo sintético: duas rubricas de `0.005` são exibidas individualmente como `0.01`, mas o total exato `0.010` é finalizado em `0.01`, sem ajustar arbitrariamente nenhuma rubrica para forçar a soma visual.

Nomes, documentos e valores não são incluídos nas mensagens de auditoria, erros ou issues. A auditoria de gravação/exportação registra o identificador do histórico; o conteúdo pessoal permanece no snapshot criptografado e na consulta autorizada. Não há armazenamento dessas evidências no navegador.

## Verificação

`test_memoria_historico.py` verifica integridade do registro anterior, vínculos, permissões, decimais e equivalência entre resultado, consulta e exportação. `Historico.test.tsx` cobre a consulta e a preparação do recálculo.
