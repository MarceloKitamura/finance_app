# 📚 Guia de Estudo — Finance App

Este guia te leva do zero ao domínio do projeto, **uma etapa de cada vez**.
Não pule etapas. Cada uma tem: o que estudar, o que observar, e um mini-desafio.

A regra de ouro: **rode o código, mexa nele, quebre, conserte.** É assim que se aprende.

---

## Como usar este guia

- Cada "dia" leva ~30-60 min. Faça no seu ritmo (pode ser 1 por dia, 1 por semana).
- Antes de cada dia, abra o arquivo indicado e leia os comentários.
- No fim de cada dia, faça o mini-desafio. Se travar, está tudo bem — anote a dúvida.
- Marque o checkbox `[ ]` → `[x]` quando terminar.

---

## 🟢 SEMANA 1 — Rodar e explorar (sem código ainda)

> Objetivo: ter o projeto rodando e entender o que ele faz, antes de olhar código.

### [ ] Dia 1 — Fazer rodar
1. Instale: `pip install -r requirements.txt`
2. Rode a versão web: `streamlit run run_streamlit.py`
3. Clique em cada uma das 5 páginas no menu lateral.
4. Cadastre 5 transações de teste (1 receita + 4 despesas em categorias diferentes).
5. Volte ao Dashboard e veja os gráficos preencherem.

**Observe:** como os gráficos mudam quando você troca o mês na barra lateral.

**Mini-desafio:** cadastre uma despesa com a descrição "Netflix" e veja a IA sugerir a categoria sozinha. 🤖

---

### [ ] Dia 2 — Rodar a versão terminal (CLI)
1. Em outro terminal (mesma pasta): `python -m app.main`
2. Use o menu de números para cadastrar uma transação.
3. Volte ao Streamlit, recarregue (F5) → veja a transação do terminal aparecer.

**Observe:** as duas interfaces compartilham o mesmo banco. Esse é o ponto-chave do projeto.

**Mini-desafio:** descubra onde o banco está salvo (dica: pasta `data/`). Abra com o programa "DB Browser for SQLite" (gratuito) e veja a tabela `transactions`.

---

## 🟡 SEMANA 2 — Entender a estrutura (a base de tudo)

> Objetivo: entender POR QUE o projeto é dividido em pastas. Esse é o conceito mais importante.

### [ ] Dia 3 — O conceito de camadas
Leia, nesta ordem, só os comentários do topo de cada arquivo:
1. `app/models/transaction.py` — o que é uma transação
2. `app/repositories/transaction_repository.py` — quem fala com o banco
3. `app/services/transaction_service.py` — quem tem a regra de negócio
4. `app/interfaces/cli.py` — quem fala com o usuário

**Pergunta que você deve saber responder:** se eu trocar o SQLite por outro banco, quais arquivos mudam? (Resposta: só o repository.)

**Mini-desafio:** desenhe num papel as 4 camadas e uma seta mostrando "quem chama quem". Compare com o diagrama do README.

---

### [ ] Dia 4 — O fluxo de uma transação
Siga uma transação da tela até o banco:
1. Abra `app/interfaces/streamlit_app.py`, ache `page_add_transaction()`.
2. Veja a linha que chama `transaction_service.add_transaction(...)`.
3. Vá em `transaction_service.py`, ache `add_transaction()`.
4. Veja que ele chama `repository.create(...)`.
5. Vá no repository e veja o SQL `INSERT`.

**Observe:** a tela NÃO escreve SQL. Ela pede pro service, que pede pro repository.

**Mini-desafio:** encontre onde a validação acontece (dica: `transaction.validate()` no model). Por que ela não está na tela?

---

## 🟢 SEMANA 3 — Entender o Streamlit (a parte visual)

> Objetivo: entender como a interface web é construída.

### [ ] Dia 5 — Componentes básicos
Abra `app/interfaces/streamlit_app.py` na seção "5. PÁGINA: Dashboard".
Procure e entenda:
- `st.columns(4)` — divide a tela em 4 colunas
- `st.metric(...)` — cria os cards de número
- `st.plotly_chart(...)` — mostra um gráfico

**Mini-desafio:** mude o ícone do Dashboard de `📊` para `💹`. Salve e recarregue.

---

### [ ] Dia 6 — session_state (memória do app)
Leia a função `init_app()` (seção 3).

**Conceito-chave:** o Streamlit roda o arquivo INTEIRO toda vez que você clica em algo. O `session_state` é a memória que sobrevive entre esses "reruns".

**Pergunta:** o que aconteceria se criássemos `TransactionService()` direto na página, sem `session_state`? (Resposta: criaria um novo a cada clique — desperdício.)

**Mini-desafio:** na seção 4, ache a função `month_year_picker()`. Por que ela tem o parâmetro `key`? (Dica: o que acontece se dois seletores tiverem a mesma key?)

---

### [ ] Dia 7 — Gráficos com Plotly
Leia as funções `donut_chart()`, `bar_chart_horizontal()` e `income_vs_expense_chart()` (seção 4).

**Observe:** cada função recebe dados (um dicionário) e devolve uma "figura". A página só chama `st.plotly_chart(figura)`.

**Mini-desafio:** na função `donut_chart`, mude o `hole=0.55` para `hole=0.3`. Veja como o buraco do donut fica menor. Depois teste `hole=0` (vira pizza).

---

## 🔵 SEMANA 4 — Entender a IA (a parte mais legal)

> Objetivo: entender como a categorização automática funciona.

### [ ] Dia 8 — Como a IA "pensa"
Abra `app/services/ai_service.py` e leia o comentário do topo (o mapa das 2 camadas).

Depois teste a IA isolada no terminal:
```bash
python -c "from app.services.ai_service import AIService; from app.constants.transaction_types import TYPE_EXPENSE; print(AIService(use_llm=False).suggest_category('uber para o trabalho', TYPE_EXPENSE))"
```

**Observe:** ela retorna uma tupla `(categoria, confiança)`.

**Mini-desafio:** teste com 3 descrições suas e veja o que a IA sugere.

---

### [ ] Dia 9 — As palavras-chave
Abra `app/constants/category_patterns.py`.

**Observe:** é só um dicionário de `categoria → lista de palavras`. A "inteligência" é procurar essas palavras na descrição.

**Mini-desafio (importante!):** adicione a palavra `"99pay"` na categoria "Transporte". Salve. Teste no terminal com a descrição "99pay corrida". Deve sugerir Transporte.

---

### [ ] Dia 10 — A lógica de busca
Em `ai_service.py`, leia a função `_match_by_pattern()`.

**Conceito:** ela conta quantas palavras-chave de cada categoria aparecem na descrição. A categoria com mais "acertos" vence.

**Pergunta:** por que usamos `\b` no regex? (Dica: para "gas" não casar dentro de "gasto". Leia o comentário.)

**Mini-desafio:** entenda a fórmula da confiança: `0.85 + (score-1)*0.06`. Por que 2 palavras dão mais confiança que 1?

---

### [ ] Dia 10b — O Consultor IA (análise financeira)
Abra `app/services/financial_advisor_service.py` e leia o comentário do topo.

**Conceito-chave:** o consultor é uma **lista de regras**. Cada regra é um método
`_rule_xxx` que olha os dados e devolve um conselho (ou `None` se não tiver nada
a dizer). O método `generate_insights()` roda todas e junta os resultados.

Teste no terminal:
```bash
python -c "
from app.services.financial_advisor_service import FinancialAdvisorService
from app.services.transaction_service import TransactionService
ts = TransactionService()
ts.add_transaction('2026-05-10','Mercado',2000,'despesa','Mercado','Pix')
ts.add_transaction('2026-05-05','Salario',3000,'receita','Salario','Pix')
for i in FinancialAdvisorService().generate_insights(2026, 5):
    print(f'[{i.severity}] {i.title}: {i.message}')
"
```

**Observe:** cada regra é independente. Uma com bug não derruba as outras
(há um try/except em volta de cada uma).

**Mini-desafio:** leia a regra `_rule_subscriptions_weight`. Ela faz duas coisas
diferentes dependendo do peso das assinaturas. Entenda quando ela vira "alerta de
economia" e quando vira só "resumo".

---

## 🔴 SEMANA 5 — Modificar por conta própria

> Objetivo: ganhar autonomia. Agora você muda o projeto sozinho.

### [ ] Dia 11 — Seu primeiro recurso novo
Vá no arquivo `CHALLENGES.md` e faça os desafios marcados como **Fácil**.

### [ ] Dia 12 — Um desafio médio
Escolha UM desafio **Médio** do `CHALLENGES.md`.

### [ ] Dia 13 — Revisão geral
Releia o `transaction_service.py` inteiro. Agora deve fazer muito mais sentido do que na Semana 2.

---

## ✅ Checklist de domínio (você "fechou" o projeto quando consegue...)

- [ ] Explicar para alguém o que é "camada de service"
- [ ] Adicionar uma palavra-chave nova na IA sem ajuda
- [ ] Adicionar um card de métrica novo no Dashboard
- [ ] Explicar por que a interface não escreve SQL
- [ ] Mudar a cor de um gráfico
- [ ] Rodar tanto a CLI quanto o Streamlit
- [ ] Entender o que `session_state` faz

Quando todos estiverem marcados, você está pronto para a **Fase 3 (FastAPI + frontend)**.

---

## 📌 Dicas de estudo

1. **Não decore, entenda.** Pergunte sempre "por que isso existe?".
2. **Quebre de propósito.** Mude um valor, veja o erro, entenda a mensagem.
3. **Use o log.** O arquivo `logs/app.log` mostra o que o programa fez.
4. **Uma coisa de cada vez.** Não tente entender tudo num dia.
5. **Anote dúvidas.** Quando algo não fizer sentido, escreva. Pergunte depois.
