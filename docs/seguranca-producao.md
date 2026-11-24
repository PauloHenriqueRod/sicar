# Segurança e implantação

## Dependências e auditoria

O [override de `minimatch`](../front-sgp/package.json) corrige uma dependência de desenvolvimento do ESLint. Ao atualizar o lint, reavalie a compatibilidade da versão principal e confira, com Node 22, `npm ci`, `npm audit --audit-level=low`, lint, testes e build. [Alerta de origem](https://github.com/advisories/GHSA-g3hv-75wg-m249).

No backend, reproduza a [preparação e auditoria do CI](../.github/workflows/testes-backend.yml). O job atualiza as ferramentas de instalação antes dos requisitos e roda o auditor em ambiente separado, apontando para os pacotes instalados na aplicação. Isso inclui dependências que já vieram com a versão de Python usada no runner.

## Comportamento

- Cada conta possui um identificador aleatório permanente. Recriar o mesmo nome de usuário não recupera acesso com um token antigo.
- Cada login abre uma sessão no banco. A API verifica conta ativa, versão da credencial, revogação, prazo absoluto e inatividade em todas as requisições autenticadas.
- O prazo padrão é de 24 horas, com encerramento após 45 minutos sem requisições autenticadas. Atividade no servidor renova apenas o prazo de inatividade. Movimentos do mouse, isoladamente, não renovam a sessão no servidor.
- Sair encerra a sessão atual. Alterar ou redefinir a senha encerra todas as sessões anteriores; a troca feita pelo próprio usuário cria uma nova sessão.
- Ao sair, a interface retira os dados da tela imediatamente, mas só confirma o encerramento após uma resposta bem-sucedida da API. Falhas de rede, limite de tráfego ou timeout exibem nova tentativa; o bloqueio permanece após recarregar a página enquanto não houver confirmação.
- Falhas de login retornam a mesma resposta para conta inexistente, inativa, bloqueada ou senha incorreta. Todas passam pela verificação de senha com bcrypt.
- Alterações de usuários, senhas, tabelas salariais e cálculos são confirmadas junto com a auditoria. Se o registro falhar, a alteração é desfeita e a API responde com erro.
- A exportação recebe somente `historico_id`. Tipo, entradas revisadas e resultado vêm do registro criptografado salvo pelo servidor. Usuários comuns acessam seus próprios registros; administradores e desenvolvedores mantêm acesso global.

O PDF reproduz o cálculo armazenado. A autenticação do documento de origem e a confirmação do direito cabem ao RH.

## Atualização de uma instalação existente

1. Faça backup do banco e preserve a chave de criptografia em armazenamento protegido.
2. Interrompa os processos da aplicação antes de atualizar. A migração aditiva executada na inicialização não deve concorrer com outros processos de migração.
3. Compile o frontend e inicie uma instância do backend. A inicialização adiciona os identificadores das contas existentes e cria a tabela de sessões. Reexecutar a migração preserva os identificadores já atribuídos.
4. Todos os usuários precisarão entrar novamente. Tokens do formato antigo são rejeitados.
5. O histórico anterior permanece consultável. Registros legados que guardam apenas o resultado não contêm as entradas necessárias à exportação vinculada; nesses casos, inicie um novo cálculo com dados revisados. Snapshots completos, inclusive versões substituídas, são exportados a partir dos valores salvos e identificados pela sua versão, conforme [memória de cálculo](memoria-calculos.md).

Não altere `ENCRYPTION_KEY` sem um procedimento de migração dos dados criptografados.

### Atualização da geração de relatórios

O gerador utiliza `fpdf2` e fontes Unicode Noto Sans incluídas em `app/assets/fonts`, com licença OFL. Em ambientes que ainda tenham `fpdf` instalado, pare a aplicação e, no ambiente virtual ativo e dentro de `back-sgp`, execute:

```text
python -m pip uninstall -y fpdf
python -m pip install --force-reinstall -r requirements.txt
python -m pip check
```

Os dois pacotes compartilham o módulo `fpdf`; a reinstalação restaura seus arquivos mesmo se ambos já tiverem coexistido. Inclua as fontes no pacote de implantação. Travessões, aspas tipográficas e nomes em português e Latin estendido são preservados. A cobertura da fonte não inclui todos os sistemas de escrita: caracteres sem glifo retornam HTTP 422 com seus códigos Unicode, sem gerar um relatório que omita dados.

### Atualização das tabelas e dos metadados do histórico

A inicialização normaliza classe e titulação (caixa, acentos e espaços) e cria índices únicos. Duplicidades de classe/nível/ano ou classe/nível/titulação/ano, inclusive após normalização, interrompem a migração para revisão manual. Confira os [procedimentos de migração e recuperação do cadastro salarial](referencias-salariais.md).

Em uma cópia autorizada do banco, ensaie a migração de matrícula, classe, titulação e resultados legados para o histórico criptografado. Ela valida a chave e processa registros em lotes. Em produção, execute com uma única instância. Para reverter, restaure a versão correspondente do banco e da chave. Falha de leitura deve retornar erro. Quantidade, proprietário, tipo e data dos registros continuam visíveis no banco.

A auditoria de extração autenticada registra ator, IP, quantidade e situação. O log de falhas omite nomes, conteúdo de documentos, parâmetros SQL e detalhes da exceção. Rejeições anteriores ao endpoint ficam fora desses eventos. A troca da própria senha admite cinco tentativas por minuto por IP. O login serializa a contagem de falhas por conta no PostgreSQL.

## Publicação do frontend com proteção

O frontend de produção deve compartilhar a mesma origem HTTPS da API. O backend pode servir os arquivos compilados, aplicando CSP e os demais cabeçalhos também ao HTML.

1. Em `front-sgp`, execute `npm ci` e `npm run build`. Deixe `VITE_API_URL` ausente ou vazia no build de produção. Ela passa a usar a origem atual; o endereço localhost fica restrito ao desenvolvimento.
2. No ambiente do backend, configure:

   ```dotenv
   ENVIRONMENT=production
   SERVE_FRONTEND=true
   ALLOWED_ORIGINS=https://rh.exemplo.edu.br
   ALLOWED_HOSTS=rh.exemplo.edu.br
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   SESSION_IDLE_TIMEOUT_MINUTES=45
   ```

   Substitua o domínio de exemplo. Configure também `DATABASE_URL`, `SECRET_KEY`, `ENCRYPTION_KEY` e a senha inicial por variáveis protegidas. Não publique arquivos de ambiente ou bancos no repositório.

3. Termine o HTTPS em um proxy confiável e encaminhe tanto a interface quanto `/api` ao backend. Restrinja o acesso direto à porta do backend.
4. Para um proxy na mesma máquina, um exemplo de inicialização, dentro de `back-sgp`, é:

   ```text
   ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
   ```

   Se o proxy estiver em outro endereço, configure explicitamente seu IP confiável e a interface de escuta apropriada. Não use `*` como lista de proxies confiáveis. O proxy deve sobrescrever os cabeçalhos encaminhados pelo cliente; o aplicativo usa o esquema validado pelo servidor ASGI.

5. Confira no navegador que o HTML recebe `Content-Security-Policy`, `Strict-Transport-Security` e `Cache-Control: no-store`, e que o cookie de login tem `Secure`, `HttpOnly` e `SameSite=Strict`.

Não use o servidor de desenvolvimento do Vite como hospedagem pública. Se optar por hospedar o frontend separadamente, será necessário configurar esses cabeçalhos no servidor que entrega o HTML e revisar as origens de conexão da CSP.

A CSP não permite scripts externos nem scripts inline. Estilos inline permanecem permitidos por compatibilidade com os componentes existentes. Essa política complementa as proteções da aplicação, mas não substitui a prevenção de XSS.

## Proteções de requisições e documentos

Hosts devem ser explícitos: `ALLOWED_HOSTS` usa nomes de domínio, separados por vírgula, sem esquema ou porta. Na ausência dessa variável, produção usa os hosts de `ALLOWED_ORIGINS`; desenvolvimento aceita localhost, 127.0.0.1 e testserver. Para acesso pela rede local, configure o host adicional. O host é validado antes do redirecionamento HTTPS.

Pedidos que alteram dados são rejeitados quando o cabeçalho `Origin` informa uma origem não autorizada. Pedidos com `Sec-Fetch-Site: cross-site` sem origem também são rejeitados. Clientes sem esses cabeçalhos continuam sujeitos à autenticação e às permissões. Essas verificações complementam os cookies `SameSite=Strict`.

O corpo da requisição é limitado antes do parser: 1 MiB nos demais endpoints e 51 MiB no upload, inclusive quando o tamanho não foi declarado ou foi declarado incorretamente. Permanecem os limites de dez arquivos por lote e 5 MiB por arquivo. Configure limites de corpo, conexões e tempo também no proxy.

Cada processo do backend permite duas leituras de PDF simultâneas, executadas em processos descartáveis com limite de 15 segundos, 512 MiB de memória, cem páginas e um milhão de caracteres extraídos. A conversão em texto e a interpretação estruturada compartilham esses limites; a API recebe os dados prontos sem executar as expressões de extração no seu event loop. O leitor não recebe chaves e senhas nas variáveis de ambiente. Se o sistema operacional não conseguir aplicar o limite de memória, a leitura falha com 503. Isso não equivale a uma sandbox de permissões: o processo mantém as permissões de arquivos e rede do usuário do serviço. Use uma conta de serviço com privilégios mínimos e mantenha o parser atualizado.

O limitador global mantém até 8.192 endereços ativos, com até 200 pedidos por minuto por endereço. Novos endereços são rejeitados quando a capacidade está cheia até que entradas expirem. Esses limites e os do SlowAPI são locais a cada processo; uma instalação com vários workers ou instâncias precisa de um limite compartilhado no proxy ou em armazenamento apropriado. Usuários atrás do mesmo IP compartilham a cota.

A inicialização de produção rejeita `TESTING=true`, chave JWT com menos de 32 bytes, origens sem HTTPS e `DATABASE_URL` ausente ou que não indique PostgreSQL. `ENVIRONMENT` aceita apenas `development`, `testing` e `production`. O tamanho mínimo da chave não mede sua aleatoriedade: gere uma chave forte fora do repositório. A criação inicial do administrador aplica a mesma política de senha dos cadastros; não altera senhas de administradores já existentes.

As exportações também são executadas em processos descartáveis, com até duas gerações simultâneas por processo da API, 15 segundos, 512 MiB, cem páginas e 5 MiB de saída. O conteúdo enviado ao gerador é limitado a 256 KiB, profundidade oito, dez mil nós, 4.096 caracteres por campo e cem mil caracteres no total. Falhas removem arquivos parciais. O processo recebe somente as variáveis de ambiente permitidas para execução, sem chaves de aplicação. Essas restrições não substituem o isolamento de permissões da conta de serviço.

Uma atualização aditiva cria `historico_calculo.idempotency_key` e um índice único por usuário e chave. Execute a atualização com uma única instância, conforme as demais migrações de inicialização. Repetir uma solicitação de cálculo com a mesma chave e dados retorna o resultado já salvo; reutilizar a chave com outros dados retorna conflito. Clientes antigos sem chave não têm essa garantia. O histórico, a chave e a auditoria do cálculo são confirmados na mesma transação.

A interface limpa dados e operações pendentes ao observar saída ou troca de identidade em outra aba, e confirma a identidade atual no servidor. Eventos entre abas contêm apenas identificadores aleatórios de evento e estado de sessão, nunca valores ou documentos de RH.

## Escopo da validação

Os testes usam dados sintéticos e banco temporário. A configuração real de DNS, certificados, proxy, backups, permissões do banco e monitoramento depende da implantação. Esta alteração não representa uma auditoria das vulnerabilidades atuais de todas as dependências.
