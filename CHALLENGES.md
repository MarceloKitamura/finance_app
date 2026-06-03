# 🎯 Desafios práticos — Finance App

Desafios para você praticar de verdade, do mais fácil ao mais difícil.
Cada um diz **onde mexer** e **o que esperar**. Faça na ordem.

> Dica: antes de cada desafio, faça uma cópia do arquivo que vai mexer
> (ex: `cp streamlit_app.py streamlit_app_backup.py`). Se quebrar, é só voltar.

---

## 🟢 FÁCEIS (15-30 min cada)

### [ ] F1 — Mudar a cor do gráfico de despesas
**Arquivo:** `app/interfaces/streamlit_app.py`
**Onde:** no topo, ache `COLOR_EXPENSE = "#EF4444"`
**Faça:** troque por outra cor, ex: `"#F97316"` (laranja).
**Espere:** todos os gráficos de despesa mudam de cor de uma vez.
**Aprende:** o valor de centralizar a cor numa constante.

---

### [ ] F2 — Adicionar uma palavra-chave na IA
**Arquivo:** `app/constants/category_patterns.py`
**Onde:** na categoria "Transporte"
**Faça:** adicione `"99pay"` e `"indrive"` na lista.
**Teste:** no terminal:
```bash
python -c "from app.services.ai_service import AIService; from app.constants.transaction_types import TYPE_EXPENSE; print(AIService(use_llm=False).suggest_category('indrive corrida', TYPE_EXPENSE))"
```
**Espere:** `('Transporte', 0.85)`
**Aprende:** como a IA usa dados externos (os patterns).

---

### [ ] F3 — Mudar o ícone e título de uma página
**Arquivo:** `app/interfaces/streamlit_app.py`
**Onde:** na função `page_dashboard()`, a linha `st.title("📊 Dashboard")`
**Faça:** troque o emoji e o texto, ex: `st.title("💹 Meu Painel")`.
**Espere:** o título muda na tela.

---

### [ ] F4 — Mudar o tamanho do buraco do donut
**Arquivo:** `app/interfaces/streamlit_app.py`
**Onde:** função `donut_chart()`, parâmetro `hole=0.55`
**Faça:** teste `hole=0.7` (anel fino) e `hole=0` (pizza cheia).
**Espere:** o formato do gráfico muda.

---

### [ ] F5 — Adicionar uma dica nova no Consultor IA
**Arquivo:** `app/services/financial_advisor_service.py`
**Onde:** função `_rule_top_category_tip()`, dicionário `tips`
**Faça:** adicione uma dica para a categoria "Saúde", por exemplo:
```python
"Saúde": (
    "Gastos com saúde são importantes. Verifique se seu plano cobre "
    "exames de rotina para evitar despesas inesperadas."
),
```
**Espere:** quando "Saúde" for sua maior categoria, a dica aparece no Dashboard.
**Aprende:** como o consultor usa dados (dicas) separados da lógica.

---

## 🟡 MÉDIOS (1-2 horas cada)

### [ ] M1 — Adicionar um card "Ticket médio"
**Arquivo:** `app/interfaces/streamlit_app.py`
**Onde:** função `page_dashboard()`, depois dos 4 cards existentes
**Faça:** adicione uma 5ª métrica que mostra o gasto médio por transação.
```python
# Calcule usando o service (NÃO faça a conta na tela):
# ticket = total_despesas / numero_de_despesas
num_despesas = len([t for t in summary["transactions"] if t.type == TYPE_EXPENSE])
ticket = summary["total_expenses"] / num_despesas if num_despesas else 0
st.metric("🎫 Ticket médio", format_brl(ticket))
```
**Espere:** um card novo aparece com o gasto médio.
**Aprende:** como adicionar uma métrica derivada.

---

### [ ] M2 — Criar uma palavra-chave nova de receita
**Arquivos:** `app/constants/category_patterns.py`
**Faça:** na seção `INCOME_PATTERNS`, adicione padrões para "pix recebido", "venda".
**Teste:** cadastre uma receita com descrição "venda produto" e veja a IA sugerir.

---

### [ ] M3 — Adicionar um gráfico de pizza de Receitas vs Despesas
**Arquivo:** `app/interfaces/streamlit_app.py`
**Onde:** função `page_dashboard()`
**Faça:** use a função `donut_chart()` que já existe, passando um dicionário
`{"Receitas": total_incomes, "Despesas": total_expenses}`.
**Espere:** um donut comparando receita e despesa.
**Aprende:** reaproveitar funções que já existem.

---

### [ ] M4 — Filtro por intervalo de valor
**Arquivo:** `app/interfaces/streamlit_app.py`
**Onde:** função `page_list_all()`, na sidebar de filtros
**Faça:** adicione dois `st.number_input` (valor mínimo e máximo) e filtre a lista.
**Espere:** só transações dentro do intervalo aparecem.

---

### [ ] M5 — Criar uma regra nova no Consultor IA
**Arquivo:** `app/services/financial_advisor_service.py`
**Faça:** crie uma regra que avisa quando o gasto com "Alimentação" + "Mercado"
juntos passam de 40% das despesas (sinal de que comida está pesando muito).
**Passos:**
1. Escreva um método `_rule_food_weight(self, ctx)` seguindo o padrão das outras regras.
2. Adicione `self._rule_food_weight` na lista `rules` dentro de `generate_insights()`.
3. Teste cadastrando muitos gastos de comida.
**Aprende:** como o sistema de regras é extensível — esse é o conceito central
do consultor. Cada regra é independente.

---

## 🔴 DIFÍCEIS (2-4 horas cada)

### [ ] D1 — Ativar a IA com ChatGPT de verdade
**Pré-requisito:** uma API key da OpenAI (tem custo, mas baixo).
**Faça:**
1. Instale: `pip install openai`
2. Configure a chave: `export OPENAI_API_KEY="sua-chave"` (Linux/Mac)
3. Rode o Streamlit. Na barra lateral deve aparecer "🤖 IA: patterns + LLM ativo".
4. Cadastre uma despesa com descrição esquisita que os patterns NÃO pegam,
   ex: "estabelecimento 4837 sao paulo". A IA via LLM deve tentar adivinhar.
**Arquivo de referência:** `app/services/ai_service.py`, função `_classify_with_llm()`
**Aprende:** como integrar uma IA externa de verdade com fallback seguro.

---

### [ ] D2 — Adicionar a função "Excluir transação"
**Arquivos:** `repository` → `service` → `streamlit_app.py` (as 3 camadas!)
**Faça:**
1. No `transaction_repository.py`, adicione `def delete(self, transaction_id: int)`.
2. No `transaction_service.py`, adicione `def delete_transaction(self, id)`.
3. No Streamlit, na página de Transações, adicione um botão de excluir.
**Aprende:** como um recurso novo atravessa TODAS as camadas. Este é o desafio
mais importante para entender a arquitetura.

---

### [ ] D3 — Página de "Metas de gastos"
**Faça:** crie uma nova página onde o usuário define um limite por categoria
(ex: "máximo R$ 500 em Alimentação") e o app mostra uma barra de progresso
(`st.progress`) de quanto já foi gasto.
**Dica:** você precisará de uma forma de salvar as metas (pode ser um novo
arquivo `metas.json` ou uma nova tabela no banco).
**Aprende:** modelar um recurso novo do zero.

---

### [ ] D4 — Gráfico de gastos por dia do mês
**Arquivo:** `app/interfaces/streamlit_app.py` + talvez um método novo no `report_service.py`
**Faça:** crie um gráfico de linha mostrando quanto foi gasto em cada dia do mês.
**Dica:** agrupe as transações por `t.date` e some os valores.
**Lembre:** a lógica de agrupar deve ir no `report_service`, não na tela!

---

## 🏆 Desafio final (projeto completo)

### [ ] BOSS — Integre tudo
Combine: D2 (excluir) + M1 (ticket médio) + D3 (metas) num app coeso.
Se você conseguir fazer isso sem quebrar a CLI nem misturar regra de negócio
na interface, você **dominou** a arquitetura. Hora da Fase 3 (FastAPI)! 🚀

---

## ✋ Regras importantes ao fazer os desafios

1. **Nunca coloque SQL no streamlit_app.py.** Sempre passe pelo service/repository.
2. **Nunca calcule saldo/total na tela.** Sempre use o `report_service`.
3. **Teste a CLI depois de cada mudança.** Rode `python -m app.main` para garantir
   que não quebrou a Fase 1.
4. **Leia a mensagem de erro.** 90% dos erros dizem exatamente o que está errado.
