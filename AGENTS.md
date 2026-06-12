# AGENTS.md

## Objetivo deste arquivo

Este arquivo serve como guia obrigatório para qualquer IA/agente de código que trabalhe neste projeto.

O objetivo principal é **manter a estrutura, arquitetura e padrões do Finance App**, evitando que novas funcionalidades quebrem o projeto, dupliquem lógica ou misturem responsabilidades entre CLI, Streamlit, API, frontend e banco de dados.

Sempre que for alterar, criar ou refatorar código, siga este documento antes de tomar decisões.

---

# Visão geral do projeto

Este é um sistema de gestão financeira pessoal em Python, com múltiplas interfaces usando um núcleo compartilhado de lógica de negócio.

O projeto possui:

- CLI em Python
- Interface Streamlit
- API REST com FastAPI
- Frontend HTML/CSS/JS puro
- SQLite como banco atual
- IA de categorização
- Consultor financeiro inteligente
- Multi-contas
- Cartões de crédito
- Metas financeiras
- Alertas
- Relatórios

Todas as interfaces devem reutilizar a mesma camada de serviços, repositórios, modelos e banco de dados.

---

# Regra principal de arquitetura

A regra mais importante do projeto é:

> Interfaces não devem conter regra de negócio.  
> Services concentram regra de negócio.  
> Repositories concentram acesso ao banco de dados.  
> Models representam entidades.  
> Constants centralizam valores fixos.  
> Utils centralizam funções auxiliares reutilizáveis.

Nunca coloque SQL diretamente em CLI, Streamlit, FastAPI ou frontend.

Nunca duplique regra de negócio em várias interfaces.

---

# Estrutura oficial do projeto

Mantenha esta estrutura como base:

```txt
finance_app/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── config.py
│   │
│   ├── models/
│   │   ├── transaction.py
│   │   ├── account.py
│   │   ├── card.py
│   │   └── goal.py
│   │
│   ├── repositories/
│   │   ├── transaction_repository.py
│   │   ├── account_repository.py
│   │   ├── card_repository.py
│   │   └── goal_repository.py
│   │
│   ├── services/
│   │   ├── transaction_service.py
│   │   ├── report_service.py
│   │   ├── account_service.py
│   │   ├── card_service.py
│   │   ├── goal_service.py
│   │   ├── ai_service.py
│   │   ├── financial_advisor_service.py
│   │   ├── alert_service.py
│   │   └── export_service.py
│   │
│   ├── constants/
│   │   ├── categories.py
│   │   ├── payment_methods.py
│   │   ├── transaction_types.py
│   │   └── category_patterns.py
│   │
│   ├── interfaces/
│   │   ├── cli.py
│   │   ├── prompts.py
│   │   └── streamlit_app.py
│   │
│   ├── api/
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── routers/
│   │       ├── transactions.py
│   │       ├── accounts.py
│   │       ├── cards.py
│   │       ├── goals.py
│   │       ├── alerts.py
│   │       ├── reports.py
│   │       └── ai.py
│   │
│   └── utils/
│       ├── date_utils.py
│       ├── money_utils.py
│       ├── normalizers.py
│       └── logger.py
│
├── frontend/
│   ├── index.html
│   ├── pages/
│   ├── js/
│   └── css/
│
├── data/
├── logs/
├── run_streamlit.py
├── run_api.py
├── requirements.txt
├── README.md
├── STUDY_GUIDE.md
└── CHALLENGES.md
```

Ao adicionar novas funcionalidades, prefira encaixar dentro dessa estrutura em vez de criar pastas aleatórias.

---

# Responsabilidade de cada camada

## 1. Models

Local: `app/models/`

Use models para representar entidades do domínio.

Exemplos:

- Transaction
- Account
- Card
- Goal
- Invoice
- Installment

Models não devem conter SQL.

Models não devem depender de Streamlit, FastAPI, CLI ou frontend.

Models podem conter validações simples da própria entidade, mas regras mais complexas devem ficar em services.

---

## 2. Repositories

Local: `app/repositories/`

Repositories são o único lugar onde SQL deve existir.

Responsabilidades:

- Criar registros
- Buscar registros
- Atualizar registros
- Deletar registros
- Consultas específicas ao banco
- Conversão entre linhas do banco e models/dicionários

Não coloque regra de negócio financeira complexa aqui.

Exemplo correto:

```python
class TransactionRepository:
    def create(self, transaction):
        # SQL INSERT
        pass

    def list_by_month(self, month, year):
        # SQL SELECT
        pass
```

Exemplo errado:

```python
class TransactionRepository:
    def create_installments_and_calculate_invoice(self):
        # regra de negócio misturada com banco
        pass
```

Nesse caso, a regra deve ficar em um service.

---

## 3. Services

Local: `app/services/`

Services concentram a regra de negócio.

Responsabilidades:

- Validar operações
- Orquestrar repositories
- Calcular saldo
- Calcular faturas
- Gerar parcelas
- Gerar alertas
- Gerar relatórios
- Preparar dados para IA
- Aplicar regras financeiras

Exemplo:

```python
class TransactionService:
    def create_transaction(self, data):
        # valida origem
        # decide se é conta ou cartão
        # chama repository correto
        # gera parcelas se necessário
        pass
```

Toda interface deve chamar services, nunca repositories diretamente, salvo casos muito simples e já existentes no projeto.

---

## 4. Constants

Local: `app/constants/`

Use constants para valores fixos e reutilizáveis.

Exemplos:

- Categorias
- Formas de pagamento
- Tipos de transação
- Status de fatura
- Status de parcela
- Padrões de categorização por IA

Evite strings soltas repetidas pelo código.

Exemplo recomendado:

```python
PAYMENT_ORIGIN_ACCOUNT = "account"
PAYMENT_ORIGIN_CARD = "card"
```

---

## 5. Utils

Local: `app/utils/`

Use utils para funções auxiliares genéricas.

Exemplos:

- Formatação de dinheiro
- Normalização de texto
- Conversão de datas
- Logs
- Arredondamento financeiro

Utils não devem conhecer regra de negócio específica demais.

---

## 6. Interfaces

Local: `app/interfaces/`

As interfaces devem apenas:

- Coletar dados do usuário
- Mostrar dados na tela
- Chamar services
- Exibir mensagens de erro/sucesso

Não colocar regra financeira diretamente em:

- `cli.py`
- `prompts.py`
- `streamlit_app.py`

Se uma lógica for usada por mais de uma interface, ela obrigatoriamente deve ir para `services/`.

---

## 7. API FastAPI

Local: `app/api/`

A API deve:

- Receber requisições
- Validar entrada com schemas Pydantic
- Chamar services
- Retornar respostas padronizadas

Não colocar SQL na API.

Não colocar regra financeira diretamente nos routers.

Routers devem ser finos e objetivos.

Exemplo correto:

```python
@router.post("/transactions")
def create_transaction(payload: TransactionCreate):
    return transaction_service.create_transaction(payload.dict())
```

---

## 8. Frontend HTML/CSS/JS

Local: `frontend/`

O frontend deve consumir a API.

Responsabilidades:

- Renderizar telas
- Fazer chamadas HTTP usando `frontend/js/api.js`
- Manipular componentes visuais
- Validar campos básicos de formulário
- Mostrar feedback para o usuário

Não coloque regras financeiras importantes somente no JavaScript.

Toda regra importante precisa existir também no backend/core.

---

# Regras para novas funcionalidades

Ao criar uma nova funcionalidade, siga sempre esta ordem:

1. Entender o domínio e a regra
2. Criar/ajustar model, se necessário
3. Criar/ajustar repository, se precisar persistir dados
4. Criar/ajustar service com a regra de negócio
5. Expor na API, se necessário
6. Adaptar Streamlit, se necessário
7. Adaptar CLI, se necessário
8. Adaptar frontend HTML/CSS/JS, se necessário
9. Atualizar README, se a funcionalidade for relevante
10. Explicar o que foi alterado

---

# Padrão para gastos: conta vs cartão

Toda despesa deve ter uma origem clara:

- `account`: gasto direto da conta
- `card`: gasto no cartão de crédito

Uma despesa não pode ser conta e cartão ao mesmo tempo.

## Regras obrigatórias

Se `payment_origin = "account"`:

- Deve ter `account_id`
- Não deve ter `card_id`
- Não deve gerar fatura
- Não deve gerar parcelas de cartão
- Deve afetar diretamente o saldo da conta

Se `payment_origin = "card"`:

- Deve ter `card_id`
- Não deve descontar imediatamente do saldo da conta
- Deve entrar na fatura do cartão
- Pode gerar parcelas
- Deve impactar saldo previsto/futuro, não saldo atual imediatamente

---

# Parcelamento no cartão

Compras parceladas devem ser tratadas como parcelas vinculadas a uma despesa principal.

Exemplo:

```txt
Compra: Celular
Valor total: 1200.00
Parcelas: 12
Cartão: Nubank
```

Resultado esperado:

```txt
Celular 1/12 - 100.00
Celular 2/12 - 100.00
Celular 3/12 - 100.00
...
Celular 12/12 - 100.00
```

## Regras obrigatórias

- Parcelamento só deve ser permitido para cartão.
- Compra no cartão com 1 parcela deve ser tratada como compra à vista no cartão.
- O valor total deve ser dividido pela quantidade de parcelas.
- Diferenças de centavos devem ser ajustadas na última parcela.
- Cada parcela deve estar ligada à fatura correta.
- Parcelas futuras devem entrar nos cálculos de previsão.
- A IA de conselho financeiro deve considerar parcelas futuras.

---

# Regras para faturas

Faturas de cartão devem considerar:

- Cartão usado
- Mês da fatura
- Ano da fatura
- Parcelas lançadas naquele mês
- Valor total da fatura
- Status da fatura

Status recomendados:

```txt
open
closed
paid
overdue
```

Se ainda não existir regra completa de fechamento e vencimento, implementar uma versão simples e deixar a estrutura preparada para evolução futura.

---

# Regras para saldo

O saldo da conta deve considerar:

```txt
saldo inicial
+ receitas
- despesas diretas da conta
- faturas pagas
```

Gastos no cartão não devem reduzir o saldo imediatamente.

Eles devem afetar:

- fatura atual
- faturas futuras
- previsão financeira
- alertas
- conselhos da IA

---

# IA de conselho financeiro

O `financial_advisor_service.py` deve ter acesso aos dados consolidados do usuário, incluindo:

- Receitas
- Despesas diretas da conta
- Gastos no cartão
- Faturas abertas
- Faturas futuras
- Parcelas futuras
- Metas
- Alertas
- Saldo atual
- Saldo previsto

Não crie lógica de IA separada em cada interface.

Toda análise deve passar pelo service correto.

---

# Padrões de banco de dados

O projeto usa SQLite atualmente.

Ao alterar banco de dados:

- Atualize `app/database.py`, se necessário
- Preserve dados existentes sempre que possível
- Evite alterações destrutivas
- Crie migrações simples ou funções de atualização se o projeto ainda não usar Alembic
- Garanta que o banco novo seja criado corretamente do zero
- Explique quais tabelas e campos foram alterados

Sugestões de tabelas futuras:

```txt
transactions
accounts
cards
goals
invoices
installments
```

Campos recomendados para parcelas:

```txt
installments
- id
- expense_id
- card_id
- installment_number
- total_installments
- amount
- invoice_month
- invoice_year
- due_date
- status
- created_at
```

---

# Padrões de nome

Use nomes claros e consistentes.

Preferir inglês técnico no código:

```txt
transaction
account
card
invoice
installment
payment_origin
amount
total_amount
purchase_date
due_date
status
```

Evite misturar nomes em português e inglês no código novo.

Na interface para o usuário, use português.

Exemplo:

Código:

```python
payment_origin = "card"
```

Interface:

```txt
Origem do pagamento: Cartão de crédito
```

---

# Validações obrigatórias

Toda entrada de dados financeiros deve validar:

- Valor maior que zero
- Data válida
- Categoria válida ou normalizada
- Tipo de transação válido
- Conta existente, se for gasto direto da conta
- Cartão existente, se for gasto no cartão
- Quantidade de parcelas maior ou igual a 1
- Origem do pagamento obrigatória
- Origem do pagamento não pode ser conta e cartão ao mesmo tempo

---

# Erros e mensagens

Erros devem ser claros e amigáveis.

Exemplo ruim:

```txt
ValueError
```

Exemplo bom:

```txt
Não foi possível salvar a despesa: escolha se o gasto foi feito na conta ou no cartão.
```

Services podem lançar exceções específicas ou retornar respostas padronizadas, desde que o padrão atual do projeto seja respeitado.

---

# Frontend e UX

Ao mexer na interface:

## Se o usuário escolher Conta

Mostrar:

- Conta/carteira
- Valor
- Categoria
- Descrição
- Data

Esconder:

- Cartão
- Parcelas
- Fatura

## Se o usuário escolher Cartão

Mostrar:

- Cartão
- Valor total
- Quantidade de parcelas
- Valor da parcela
- Categoria
- Descrição
- Data da compra
- Prévia das faturas afetadas

Esconder:

- Conta direta, salvo se for necessário para pagamento de fatura

---

# Dashboard

O dashboard deve diferenciar:

- Saldo atual
- Saldo previsto
- Receitas
- Despesas diretas da conta
- Gastos no cartão
- Fatura atual
- Faturas futuras
- Parcelas futuras
- Metas
- Alertas

Não misturar gasto direto da conta com gasto no cartão no mesmo cálculo sem deixar isso claro.

---

# Relatórios

Relatórios devem permitir separar ou comparar:

- Despesas por categoria
- Despesas por conta
- Despesas por cartão
- Faturas por mês
- Parcelas futuras
- Evolução mensal
- Saldo previsto

---

# Boas práticas de código

Sempre que alterar o projeto:

- Mantenha funções pequenas
- Evite duplicação
- Use nomes claros
- Não crie arquivos gigantes sem necessidade
- Não misture responsabilidades
- Não quebre imports existentes
- Preserve compatibilidade com CLI, Streamlit, API e frontend quando possível
- Faça alterações incrementais
- Explique impactos

---

# Testes e verificação manual

Se existir estrutura de testes, criar ou atualizar testes.

Se não existir, ao final de cada alteração, informar como testar manualmente.

Checklist mínimo:

```txt
1. Criar despesa direta da conta
2. Verificar se desconta do saldo
3. Criar despesa no cartão à vista
4. Verificar se entra na fatura
5. Criar despesa parcelada no cartão
6. Verificar se parcelas aparecem nas faturas futuras
7. Verificar dashboard
8. Verificar relatórios
9. Verificar conselho financeiro/IA
10. Verificar API, se aplicável
```

---

# Comandos úteis

## Criar ambiente virtual

```bash
python -m venv .venv
```

## Ativar ambiente virtual no Windows

```bash
.\.venv\Scripts\activate
```

## Instalar dependências

```bash
pip install -r requirements.txt
```

## Rodar CLI

```bash
python -m app.main
```

## Rodar Streamlit

```bash
streamlit run run_streamlit.py
```

## Rodar API

```bash
python run_api.py
```

## Rodar frontend simples

```bash
python -m http.server --directory frontend 8080
```

---

# Antes de finalizar qualquer tarefa

Sempre entregar um resumo com:

```txt
Arquivos alterados
Novos arquivos criados
Tabelas/campos alterados
Regras implementadas
Como testar
Possíveis pontos de atenção
```

---

# O que não fazer

Não faça:

- SQL dentro da interface
- Regra financeira dentro do frontend
- Duplicação de lógica entre Streamlit e FastAPI
- Alterações destrutivas no banco sem aviso
- Mudanças grandes sem explicar
- Criar estrutura paralela sem necessidade
- Ignorar o core compartilhado
- Misturar conta e cartão no mesmo gasto
- Parcelamento sem vínculo com fatura
- IA financeira sem considerar parcelas futuras

---

# Princípio final

Este projeto é um app financeiro pessoal em evolução.

Toda mudança deve deixar o sistema:

- Mais organizado
- Mais fácil de manter
- Mais fácil de estudar
- Mais seguro nos cálculos
- Mais preparado para crescer

Priorize clareza, consistência e aprendizado.
