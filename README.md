# SICAR — Sistema de Conferência e Apuração Remuneratória

O modo **Apuração por períodos e rubricas** permite declarar datas, eventos e recebimentos sem upload obrigatório, segmentando mudanças remuneratórias e conciliando devido, recebido e saldo. O [contrato e as regras de segmentação](docs/apuracao-periodos.md) detalham as fontes, a conferência manual do RH, a integração ao histórico/PDF e os limites.

A **Progressão docente ou TAE** usa o mesmo núcleo para separar progressão, IQ e RT por suas datas de efeito, com referências confirmadas de origem/destino e reflexos explícitos de férias/13º. Consulte o [contrato de progressão por eventos e exemplos independentes](docs/progressao-eventos.md).

Este repositório contém o **SICAR**, uma aplicação desenvolvida para a Superintendência de Gestão de Pessoas visando a automação, conferência e cálculos de folha de pagamento retroativos a partir de processos digitalizados (PDFs).

O sistema é responsável por mitigar erros operacionais, acelerar a ingestão de dados por meio da extração automática de dados de PDFs e garantir a rastreabilidade total das operações.

## 🚀 Tecnologias Utilizadas

### Front-end (`/front-sgp`)
* **React 18** com **TypeScript** e **Vite**
* **Tailwind CSS** para estilização (com suporte nativo a Dark Mode)
* **Lucide React** para iconografia
* **File-saver** para baixar relatórios do histórico

### Back-end (`/back-sgp`)
* **FastAPI** (Python 3)
* **PostgreSQL** com **SQLAlchemy** (ORM) para persistência de dados
* **pdfplumber** para extração avançada de textos e parsing de planilhas/processos em PDF
* **fpdf2** com fontes Unicode Noto Sans para geração dos relatórios oficiais de cálculo
* **bcrypt** & **PyJWT** para autenticação e segurança (JWT)

---

## ✨ Funcionalidades Principais

1. **Extração de PDFs por processo**
   * Uma apuração reúne os documentos de um servidor, com anexos opcionais por categoria.
   * Parsing inteligente que utiliza Regex e sanitização de dados para localizar valores, datas, nomes e matrículas.
2. **Motor de Cálculos de RH**
   * Suporte a 6 fluxos diferentes (Substituição, Insalubridade, Abono de Permanência, Rescisão, Progressão Docente e Exercício Anterior).
   * Conversão precisa e tratamentos matemáticos baseados nas fórmulas oficiais.
3. **Revisão "Human-in-the-loop"**
   * O analista de RH confere os dados extraídos e pode corrigir ou preencher os campos antes do cálculo.
4. **Exportação de Relatórios Oficiais**
   * Geração de relatórios analíticos em PDF prontos para assinatura.
   * O servidor gera o PDF a partir da memória salva no histórico.
5. **Auditoria e Segurança (LGPD)**
   * Controle de acesso baseado em Roles (`dev`, `admin`, `funcionario`).
   * Tabela de rastreabilidade (Logs) restrita a `devs` que registra quem calculou, quem extraiu e quais ações foram feitas no sistema.

---

## 🛠️ Como Executar o Projeto

### Pré-requisitos
- Node.js (v18+)
- Python (3.11+)
- PostgreSQL (rodando localmente ou em contêiner)

### 1. Configurando o Back-end
1. Navegue até a pasta do back-end:
   ```bash
   cd back-sgp
   ```
2. Crie um ambiente virtual e instale as dependências:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate | Linux/Mac: source .venv/bin/activate
   python -m pip install --upgrade pip==26.2.1 setuptools==84.1.0
   pip install -r requirements.txt
   ```
   Para atualizar um ambiente antigo, remova primeiro `fpdf` e reinstale `fpdf2`: ambos usam o módulo Python `fpdf` e não podem coexistir. Com o ambiente virtual ativo, execute `python -m pip uninstall -y fpdf`, seguido de `python -m pip install --force-reinstall -r requirements.txt`. Em ambientes novos, basta a instalação normal acima. As fontes e sua licença acompanham o código em `app/assets/fonts`.
3. Crie e configure o banco de dados PostgreSQL. Atualize a string de conexão no arquivo `.env` ou em `database.py`.
4. Inicie o servidor FastAPI:
   ```bash
   uvicorn app.main:app --reload
   ```
   *A API estará disponível em `http://localhost:8000` (e o Swagger interativo em `/docs`).*

### 2. Configurando o Front-end
1. Navegue até a pasta do front-end:
   ```bash
   cd front-sgp
   ```
2. Instale as dependências do Node:
   ```bash
   npm ci
   ```
3. Inicie o servidor de desenvolvimento:
   ```bash
   npm run dev
   ```
   *A interface estará disponível em `http://localhost:5173`.*

---

## Testes locais

As configurações de sessão, exportação auditada e publicação com HTTPS estão em [Segurança e implantação](docs/seguranca-producao.md).

No ambiente virtual ativado, instale as dependências de teste do backend:

```bash
pip install -r back-sgp/requirements-dev.txt
cd back-sgp
python -m pytest
```

Os testes usam SQLite em memória e geram PDFs em diretório temporário, sem usar o banco configurado no `.env`.

As dependências de desenvolvimento também incluem `pandas`, `openpyxl` e `xlrd` para os scripts de importação de planilhas `.xlsx` e `.xls`. No editor, selecione o Python do ambiente virtual do projeto (`.venv/Scripts/python.exe` no Windows). Os stubs de tipagem fornecidos pelo Pyrefly não substituem a instalação dessas bibliotecas nesse ambiente.

Os requisitos Python fixam versões diretas e usam `back-sgp/constraints.txt` para as transitivas. O ambiente de desenvolvimento requer Python 3.11 ou superior; NumPy usa versões específicas para Python 3.11 e para 3.12+. Ao atualizar pacotes, revise as restrições, execute os testes e a auditoria. O CI usa pip-audit em ambiente separado e bloqueia alertas conhecidos sem ignorá-los.

Na raiz do projeto, execute `npm run check:front` para validar lint, build TypeScript/Vite e testes de componentes.

O frontend utiliza npm e mantém `front-sgp/package-lock.json` como referência das versões. Use `npm ci` em instalações limpas e `npm audit` para verificar vulnerabilidades conhecidas.

## 📄 Especificações Matemáticas
Se você for um desenvolvedor e precisar entender a regra de negócio por trás de cada fluxo matemático, leia o documento [`back-sgp/read.md`](./back-sgp/read.md) que contém a documentação das fórmulas obtidas por engenharia reversa das planilhas legadas.
