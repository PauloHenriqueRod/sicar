# Integração com PostgreSQL

Execute a partir de `back-sgp`, com um PostgreSQL descartável e dependências do projeto:

```text
python -m pytest integration_tests/ -q -rs
```

Configure `TEST_POSTGRES_URL` explicitamente para um banco exclusivo de teste, por exemplo `postgresql://usuario:senha@localhost:5432/sgp_rh_test`. O nome deve começar com `test_` ou terminar em `_test`, podendo ter um sufixo após `_test`. A URL não aceita parâmetros adicionais. Nunca use credenciais de produção.

Cada teste cria um schema `sgp_test_<UUID>`, configura esse schema como único `search_path` e remove somente o schema que acabou de criar. A aplicação e seu arquivo `.env` não são inicializados. Todas as operações verificadas usam conexões reais de PostgreSQL.

A suíte verifica migração aditiva idempotente, preservação de registros, índice único por usuário/requisição e conflito concorrente entre conexões distintas com rollback. Ela é separada de `tests/conftest.py`, que mantém os testes unitários e de API em SQLite.

Sem `TEST_POSTGRES_URL`, os casos são explicitamente pulados e **PostgreSQL permanece não validado localmente**. URL presente, configuração insegura ou conexão indisponível fazem a execução falhar. O workflow de backend fornece a URL de seu serviço PostgreSQL e executa esta suíte em uma etapa própria.

A suíte `test_salary_references_postgres.py` também confere migração aditiva/simulação, preservação do legado, Numeric e rejeição concorrente de vigências salariais sobrepostas.

Também existe regressão de leitura consistente de VB/RT durante edição confirmada em uma segunda conexão, incluindo nova consulta na mesma sessão. A execução PostgreSQL permanece para o CI; o teste equivalente SQLite usa banco temporário em WAL.

`test_official_sources_postgres.py` cobre a criação aditiva do cadastro de fontes/funções, Numeric com 12 casas e exclusão concorrente de vigências do mesmo componente de função. Usa o mesmo schema temporário e só executa com TEST_POSTGRES_URL explícita; a validação real permanece no CI quando não houver PostgreSQL local.
