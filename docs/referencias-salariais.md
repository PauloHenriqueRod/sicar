# Referências salariais por vigência

O cadastro identifica VB e RT por posição e vigência. A [apuração por períodos](apuracao-periodos.md) segmenta reajustes e a [progressão por eventos](progressao-eventos.md) verifica origem e destino em cada segmento.

## Identidade e seleção

A seleção exige **data explícita**, carreira (`TAE`, `MAGISTERIO_SUPERIOR`, `EBTT`), vínculo, jornada/regime e versão histórica da estrutura da carreira. Vínculo e versão são identificadores cadastrados e conferidos pelo RH, não classificações deduzidas pelo sistema. Jornada usa códigos como `20H`, `40H` e `DE`; DE não é aceito para TAE.

TAE usa classificação A–E, capacitação quando aplicável e padrão. Docente usa classe e nível. Os dois conjuntos não podem ser combinados. A versão histórica distingue mudanças de estrutura que reutilizam nomes/posições. Capacitação vazia significa que ela não integra aquela estrutura conferida; não deve representar um dado desconhecido. Textos são normalizados para igualdade exata (sem busca parcial), com chave SHA-256 da representação canônica.

Cada referência tem início, fim opcional, VB, lista de RT por titulação, fonte e estado. Os limites são inclusivos: uma referência encerrada em 31/03 não cobre 01/04. Fim vazio significa vigência aberta, não ausência de conferência. Uma mudança salarial exige encerrar o intervalo anterior antes de confirmar o seguinte. TAE não recebe RT neste cadastro; IQ continua sendo parâmetro do cálculo.

VB e RT pertencem à mesma referência, portanto compartilham carreira, vínculo, posição, jornada e vigência. Uma RT ausente não é obtida de outro período ou regime. Somente `CONFIRMADA` participa das consultas. `PENDENTE` e `INATIVA` não são salários substitutos. Fonte e identificação são obrigatórias; confirmar o cadastro é uma ação de admin/dev, após conferência documental manual.

Os valores ativos e as cópias convertidas usam `Numeric(30,12)`. O contrato aceita até 12 casas decimais, sem truncamento. A soma de VB e RT usa Decimal e não é arredondada antes do cálculo. Numeric exato é validado em PostgreSQL; SQLite é usado em testes locais e sua afinidade numérica não comprova a precisão do PostgreSQL para toda a faixa. O serviço confere a releitura do valor e rejeita a gravação se o banco perder precisão; na conversão legada, a cópia decimal fica vazia nesse caso. Não use SQLite como substituto de homologação financeira em PostgreSQL.

## Contrato HTTP

Rotas sob `/api/tabelas`, todas autenticadas e restritas a admin/dev:

| Método / rota | Contrato |
|---|---|
| GET `/referencias` | `pagina` (1...), `tamanho_pagina` (1–100), filtros `carreira`, `jornada`, `estado`, `data_referencia` |
| POST `/referencias` | Cria referência qualificada |
| PUT `/referencias/{id}` | Substitui os dados da referência e sua lista de RT; audita na mesma transação |
| GET `/pendencias-legadas` | Lista paginada de valores originais, conversão e motivo da pendência |
| PUT `/pendencias-legadas/{id}/vinculo` | `{ "referencia_id": 123 }`; exige referência confirmada e correspondência exata do valor/titulação |

Listas retornam `{itens, total, pagina, tamanho_pagina}`. Valores monetários do novo cadastro são **textos decimais**, preservados também pelo editor. Não convertê-los com `parseFloat` ao salvar. Campos de posição obrigatórios seguem o esquema OpenAPI `ReferenciaEntrada`; campos da outra carreira devem ser omitidos ou nulos.

Exemplo exclusivamente sintético de criação (não corresponde a uma tabela oficial):

```json
{
  "carreira": "MAGISTERIO_SUPERIOR", "vinculo": "EFETIVO",
  "jornada": "40H", "versao_carreira": "estrutura-sintetica-v1",
  "classe_docente": "Adjunto", "nivel_docente": 1,
  "inicio_vigencia": "2026-04-01", "fim_vigencia": null,
  "vencimento_basico": "3500.125", "retribuicoes": [{"titulacao":"Mestrado","valor":"1200.025"}],
  "fonte": "Fonte sintética conferida", "estado": "CONFIRMADA"
}
```

Duplicidades exatas de estrutura/intervalo são rejeitadas pelo banco mesmo para rascunhos. Intervalos confirmados sobrepostos são rejeitados pelo serviço e pelo banco: exclusão GiST no PostgreSQL e triggers no SQLite. RT duplicada pela titulação normalizada também é rejeitada. Conflitos retornam 409; entradas inválidas, 422. Alterar uma referência desfaz correspondências legadas previamente conferidas, exigindo nova verificação. Não altera snapshots de cálculos anteriores.

## Consulta pontual e compatibilidade dos cálculos

Os campos `referencia_antiga` e `referencia_nova` abaixo pertencem à progressão agregada legada. Nos novos processos, a progressão consulta as referências de cada segmento e permite correção individual justificada.

`POST /api/calcular` mantém o envelope existente. Em rescisão, `dados_extraidos.referencia_salarial` recebe os campos de posição acima e `data_referencia` (sem fonte, estado, VB ou RT). Em progressão, existem `referencia_antiga` e `referencia_nova`, independentes. O campo `titulacao` do cálculo escolhe a RT dentro de cada referência; `N/A` explícito significa sem RT. A titulação docente vazia gera pendência, sem assumir mestrado, doutorado ou RT zero. Para TAE, vazio ou `N/A` consulta apenas VB.

O RH pode informar `salario_mensal` em rescisão ou `salario_antigo`/`salario_novo` em progressão. Um salário explicitamente revisado tem precedência e é rastreado como `origem: revisao`. Campo vazio é omitido pela interface e provoca consulta; não vira zero. Zero explicitamente informado continua sendo zero. Todos os dados da revisão permanecem editáveis.

Os campos legados classe/nível/ano são mantidos como metadados e calendário, **não selecionam uma tabela**. Não existe mais procura pelo último ano disponível. Sem contexto completo ou referência confirmada, a resposta é 400 com `detail[].type = referencia_salarial_pendente`, sem criação de histórico. Não há salário presumido. A mensagem distingue falta de contexto, referência ausente e RT incompatível.

Nos cálculos com consulta pontual, o RH separa períodos quando houver reajuste. Cada consulta carrega posição, VB e todas as RTs em um único SELECT, inclusive na listagem paginada. Origem e destino são consultas independentes. Titulação, classe ou nível ausentes exigem revisão.

O snapshot v2 preserva a seleção efetiva em `dados_utilizados` e as entradas revisadas em `dados_extraidos` e `rastreabilidade.entradas_decimais`. Histórico e PDF usam a posição efetiva, ou a informada para salário manual. A mesma chave retorna o resultado salvo após mudanças cadastrais. Snapshots anteriores mantêm sua apresentação original.

## Migração e relatório local

A migração cria quatro tabelas novas, sem apagar ou reescrever as anuais: `estrutura_remuneratoria`, `referencia_salarial`, `retribuicao_referencia`, `pendencia_salarial_legada`. As tabelas antigas continuam Float como origem legada; não participam mais da resolução salarial. Cada linha antiga é copiada como pendência, mantendo classe, nível, ano, titulação, valor original textual e conversão Numeric quando exata. Não é atribuído 1º de janeiro nem inferida jornada, vínculo ou posição histórica. Valores que não caibam sem alteração permanecem sem conversão e com motivo explícito.

O processo é repetível. Alterações posteriores via CRUD legado sincronizam a pendência e removem o vínculo anterior, sem promover valores a referências confirmadas. O vínculo manual registra correspondência e não ativa o legado. A aplicação também executa a migração aditiva na inicialização; **prepare e confira uma cópia antes de implantar esta versão**.

Com a aplicação parada, crie backup usando as ferramentas do banco, restaure em um banco temporário e execute de `back-sgp`:

```text
python -m scripts.migrar_referencias_salariais --database-url <URL-do-banco-temporario> --report <caminho-local-novo.json>
python -m scripts.migrar_referencias_salariais --database-url <URL-do-banco-temporario> --report <outro-caminho-local-novo.json> --apply
```

Sem `--apply`, a transação, incluindo DDL, é desfeita. O relatório apresenta contagens, origem, valor original, valor convertido, conversão sem alteração, estado e motivo por registro. O arquivo deve ser novo; não é sobrescrito. Guarde relatórios e backups fora do repositório. URLs podem conter credenciais: utilize o mecanismo protegido do ambiente e não as inclua em logs ou documentos versionados. Confira totais, originais e linhas sem conversão antes de repetir a aplicação no banco alvo. Falhas no banco desfazem a transação; uma falha na gravação final do relatório exige repetir a operação idempotente para gerar novo relatório e conferir o estado.

### Recuperação

1. Pare a aplicação e preserve o relatório e o backup anterior.
2. Se a migração falhou, confira se a transação foi desfeita e execute novamente em cópia temporária.
3. Se for necessário reverter o código, mantenha as tabelas novas; o legado foi preservado. Suspenda cálculos baseados nas tabelas anuais no código anterior, pois ele não oferece a garantia de vigência desta versão. Não apague as referências confirmadas nem históricos novos para fazer rollback.
4. Se for necessária restauração do banco, restaure o backup em banco separado, confira contagens/valores e aponte a aplicação somente após conferência. Preserve uma cópia do estado posterior para não perder cálculos produzidos após a atualização.

A preservação das linhas originais, a simulação e a repetição são testadas em banco temporário. A restauração operacional de backups depende do ambiente e deve ser ensaiada pelo responsável pela implantação.

## Verificações

- `pytest tests/test_salary_references.py`: datas, carreiras, jornadas, vínculos, estrutura histórica, RT, pendências, contratos, permissões, triggers e migração SQLite descartável.
- `pytest tests/test_salary_reference_regressions.py`: edição concorrente de VB/RT com e sem cache, titulação ausente ou explícita, posição efetiva no histórico/PDF, idempotência e precedência dos salários manuais.
- Regressões de arredondamento e histórico: `test_final_rounding.py`, `test_rounding_policy.py`, `test_calculation_contracts.py`.
- `pytest integration_tests/`: com `TEST_POSTGRES_URL` de banco exclusivo de teste, valida DDL, migração/simulação, Numeric com 12 casas e bloqueio real de escrita concorrente pela exclusão. Sem a variável, informa skip; não comprova PostgreSQL.
- Vitest: cadastro/edição decimal, seleção por data, erro de conflito, campos por carreira, pendência e serialização da revisão.

Para carregar ou revisar tabelas e consultar lacunas e origens de VB, RT, IQ e CD/FG/FCC, consulte a [importação de fontes oficiais](importacao-fontes-oficiais.md). As tabelas pertencem ao cadastro.
