/* =========================================================
   Finance App — CAMADA DE API (api.js)
   ---------------------------------------------------------
   Único lugar que sabe FALAR com a FastAPI. As páginas chamam
   estas funções e recebem dados já em JSON — nunca usam fetch()
   diretamente. Isso isola a app de mudanças na API.

   Endpoints disponíveis na API (conferidos no backend):
     GET    /meta                       -> listas p/ os <select>
     GET    /transactions[?filtros]     -> lista
     GET    /transactions/{id}          -> uma
     POST   /transactions               -> cria
     DELETE /transactions/{id}          -> remove
     GET    /reports/monthly?year=&month= -> resumo do mês

   OBS 1: a API tem PUT /transactions/{id} (update no lugar). Por isso
   `updateTransaction` edita mantendo o mesmo id e a metadata de parcela
   (ideal para ajustar os centavos da última parcela).

   OBS 2: a API ainda NÃO expõe os conselhos da IA (Groq). A função
   `generateConselho` tenta um endpoint opcional e, se não existir,
   gera um conselho local baseado em regras (fallback). Assim a tela
   funciona hoje e fica pronta pra IA depois.
   ========================================================= */

const Api = (() => {
  // URL pública da SUA API no Render. Depois de criar o serviço lá, troque
  // o valor abaixo pela URL que o Render te der (algo como
  // "https://finance-app-api.onrender.com"). Sem barra "/" no final.
  const PROD_API = "https://COLOQUE-SUA-API-AQUI.onrender.com";

  // Decide automaticamente qual API usar:
  // - rodando local (localhost / 127.0.0.1 / arquivo aberto direto) -> API local
  // - publicado (Vercel) -> usa a PROD_API acima
  // Assim o mesmo código funciona nos dois lugares sem você editar toda hora.
  const _isLocal = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const BASE = _isLocal ? "http://127.0.0.1:8000" : PROD_API;

  /**
   * Núcleo das requisições. Faz o fetch, trata erros HTTP e
   * devolve o JSON. Lança Error com a mensagem `detail` da API.
   */
  async function request(path, options = {}) {
    let res;
    try {
      res = await fetch(BASE + path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
    } catch (_) {
      // Falha de rede / API fora do ar.
      throw new Error(
        `Não consegui falar com a API (${BASE}). Ela está rodando? ` +
        `Rode "python run_api.py" na raiz do projeto.`
      );
    }
    if (!res.ok) {
      let detail = `Erro ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    // DELETE devolve {detail: "..."}; demais devolvem JSON normal.
    return res.json();
  }

  // ---------- Metadados ----------

  /** Listas fixas (tipos, formas de pagamento, pessoas, categorias). */
  function getMeta() {
    return request("/meta");
  }

  // ---------- Transações ----------

  /**
   * Lista transações. `filtros` é um objeto opcional:
   * { year, month, category, spent_by, type }.
   * ATENÇÃO: no backend os filtros são mutuamente exclusivos
   * (mês > categoria > pessoa, e tipo por último). Para combinar
   * vários filtros ao mesmo tempo, a página de Lançamentos busca
   * tudo (sem filtros) e filtra no cliente.
   */
  function fetchTransactions(filtros = {}) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) {
      if (v !== undefined && v !== null && v !== "") params.set(k, v);
    }
    const qs = params.toString();
    return request("/transactions" + (qs ? `?${qs}` : ""));
  }

  /** Busca uma transação pelo id. */
  function getTransaction(id) {
    return request(`/transactions/${id}`);
  }

  /** Cria uma transação. `data` segue o schema TransactionCreate. */
  function createTransaction(data) {
    return request("/transactions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  /** Remove uma transação pelo id. */
  function deleteTransaction(id) {
    return request(`/transactions/${id}`, { method: "DELETE" });
  }

  /**
   * Atualiza uma transação no lugar (PUT /transactions/{id}). Mantém o MESMO
   * id e a metadata de parcela — por isso dá para ajustar só o valor de uma
   * parcela (ex.: os centavos da última) sem desfazer a compra parcelada.
   * `data` pode trazer só os campos a mudar; o backend preserva o resto.
   */
  function updateTransaction(id, data, applyToGroup = false) {
    // applyToGroup: propaga campos compartilhados (quem gastou, categoria,
    // pagamento, conta, cartão) para todas as parcelas da mesma compra.
    const qs = applyToGroup ? "?apply_to_group=true" : "";
    return request(`/transactions/${id}${qs}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // ---------- IA de categorização ----------

  /**
   * Pede ao backend uma sugestão de categoria para a descrição.
   * Retorna { category, confidence } — category pode ser null (sem palpite).
   * Em qualquer erro devolve {category:null, confidence:0} para não
   * atrapalhar o cadastro.
   */
  async function suggestCategory(description, type) {
    try {
      const qs = new URLSearchParams({ description, type }).toString();
      return await request(`/ai/suggest-category?${qs}`);
    } catch (_) {
      return { category: null, confidence: 0 };
    }
  }

  // ---------- Contas / saldos ----------

  /** Lista as contas COM o saldo atual já calculado pelo backend. */
  function getAccounts() {
    return request("/accounts");
  }

  /** Cria uma conta. `data` = { name, kind, initial_balance, color, icon }. */
  function createAccount(data) {
    return request("/accounts", { method: "POST", body: JSON.stringify(data) });
  }

  /** Atualiza uma conta pelo id (mesmo corpo do create). */
  function updateAccount(id, data) {
    return request(`/accounts/${id}`, { method: "PUT", body: JSON.stringify(data) });
  }

  /** Remove uma conta pelo id (a API bloqueia se houver transações). */
  function deleteAccount(id) {
    return request(`/accounts/${id}`, { method: "DELETE" });
  }

  // ---------- Cartões de crédito ----------

  /** Lista cartões com fatura/uso do mês informado. */
  function getCards(year, month) {
    const now = new Date();
    const y = year || now.getFullYear();
    const m = month || now.getMonth() + 1;
    return request(`/cards?year=${y}&month=${m}`);
  }

  /** Cria um cartão. `data` = { name, brand, limit_total, closing_day, due_day, color, status }. */
  function createCard(data) {
    return request("/cards", { method: "POST", body: JSON.stringify(data) });
  }

  /** Atualiza um cartão pelo id. */
  function updateCard(id, data) {
    return request(`/cards/${id}`, { method: "PUT", body: JSON.stringify(data) });
  }

  /** Remove um cartão pelo id. */
  function deleteCard(id) {
    return request(`/cards/${id}`, { method: "DELETE" });
  }

  /**
   * Fatura detalhada do mês + as próximas faturas (com parcelas futuras).
   * Retorna { card_id, card_name, limit_total, statements: [...] }.
   */
  function getCardStatements(id, year, month, monthsAhead = 6) {
    const now = new Date();
    const y = year || now.getFullYear();
    const m = month || now.getMonth() + 1;
    return request(`/cards/${id}/statements?year=${y}&month=${m}&months_ahead=${monthsAhead}`);
  }

  // ---------- Metas financeiras ----------

  /** Lista metas com progresso do mês informado. */
  function getGoals(year, month) {
    const now = new Date();
    const y = year || now.getFullYear();
    const m = month || now.getMonth() + 1;
    return request(`/goals?year=${y}&month=${m}`);
  }

  function createGoal(data) {
    return request("/goals", { method: "POST", body: JSON.stringify(data) });
  }
  function updateGoal(id, data) {
    return request(`/goals/${id}`, { method: "PUT", body: JSON.stringify(data) });
  }
  function deleteGoal(id) {
    return request(`/goals/${id}`, { method: "DELETE" });
  }

  // ---------- Alertas ----------

  /** Lista os alertas do mês informado (derivados do estado atual). */
  function getAlerts(year, month) {
    const now = new Date();
    const y = year || now.getFullYear();
    const m = month || now.getMonth() + 1;
    return request(`/alerts?year=${y}&month=${m}`);
  }

  // ---------- Gastos recorrentes ----------

  /** Lista os templates de gasto recorrente (com próxima cobrança). */
  function getRecurring() {
    return request("/recurring-expenses");
  }
  function createRecurring(data) {
    return request("/recurring-expenses", { method: "POST", body: JSON.stringify(data) });
  }
  function updateRecurring(id, data) {
    return request(`/recurring-expenses/${id}`, { method: "PUT", body: JSON.stringify(data) });
  }
  function deleteRecurring(id) {
    return request(`/recurring-expenses/${id}`, { method: "DELETE" });
  }

  /**
   * Autopreenchimento: dado o texto digitado na descrição, devolve
   * sugestões (templates + último gasto similar). Em erro devolve []
   * para não atrapalhar o cadastro.
   */
  async function suggestRecurring(description) {
    try {
      const qs = new URLSearchParams({ description }).toString();
      return await request(`/recurring-expenses/suggest?${qs}`);
    } catch (_) {
      return [];
    }
  }

  /** Padrões recorrentes detectados automaticamente no histórico. */
  async function getDetectedRecurring(monthsBack = 6) {
    try {
      return await request(`/recurring-expenses/detected?months_back=${monthsBack}`);
    } catch (_) {
      return [];
    }
  }

  // ---------- Agenda de vencimentos ----------

  /** Lista vencimentos. Com `upcomingDays`, só os próximos N dias (pendentes). */
  function getVencimentos(upcomingDays) {
    const qs = upcomingDays ? `?upcoming_days=${upcomingDays}` : "";
    return request(`/vencimentos${qs}`);
  }
  function createVencimento(data) {
    return request("/vencimentos", { method: "POST", body: JSON.stringify(data) });
  }
  function updateVencimento(id, data) {
    return request(`/vencimentos/${id}`, { method: "PUT", body: JSON.stringify(data) });
  }
  function deleteVencimento(id) {
    return request(`/vencimentos/${id}`, { method: "DELETE" });
  }
  /** Marca um vencimento como pago (mensal gera a próxima ocorrência). */
  function payVencimento(id) {
    return request(`/vencimentos/${id}/pay`, { method: "POST" });
  }
  /** Projeção de fluxo de caixa do mês (saldo dia a dia). */
  function getCashFlow(year, month) {
    const now = new Date();
    const y = year || now.getFullYear();
    const m = month || now.getMonth() + 1;
    return request(`/vencimentos/cash-flow?year=${y}&month=${m}`);
  }

  // ---------- Importação de extrato ----------

  /**
   * Pré-visualiza um extrato. `payload` = { format:"csv"|"ofx", content, mapping? }.
   * Sem mapping (CSV), devolve só os cabeçalhos para o usuário mapear as colunas.
   */
  function previewImport(payload) {
    return request("/import/preview", { method: "POST", body: JSON.stringify(payload) });
  }

  /** Grava as transações revisadas. `items` segue ImportConfirmItemIn. */
  function confirmImport(items) {
    return request("/import/transactions", {
      method: "POST",
      body: JSON.stringify({ items }),
    });
  }

  // ---------- Relatórios ----------

  /** Resumo de um mês: totais, saldo, agrupamentos e transações. */
  function getMonthlyReport(year, month) {
    return request(`/reports/monthly?year=${year}&month=${month}`);
  }

  /**
   * IA Gestora: score de saúde (0-100) + previsão + insights do mês.
   * É um POST (recalcula/usa cache no backend). Em erro, devolve null para
   * a página tratar.
   */
  async function getHealthScore(year, month) {
    try {
      return await request(`/reports/health-score?year=${year}&month=${month}`, {
        method: "POST",
      });
    } catch (e) {
      throw e; // a página de gestor mostra a mensagem.
    }
  }

  /**
   * Busca os resumos dos últimos `n` meses (incluindo o atual),
   * do mais antigo para o mais recente. Útil para o gráfico de
   * evolução mensal e a comparação mês a mês.
   * Faz as chamadas em paralelo (Promise.all).
   */
  async function getMonthlyRange(year, month, n = 6) {
    const pedidos = [];
    for (let i = n - 1; i >= 0; i--) {
      // Recua i meses a partir de (year, month).
      const d = new Date(year, month - 1 - i, 1);
      pedidos.push(getMonthlyReport(d.getFullYear(), d.getMonth() + 1));
    }
    return Promise.all(pedidos);
  }

  // ---------- Salário (bruto / líquido / divisão) ----------

  /** Lê a configuração de salário + líquido estimado + divisão 15/30. */
  function getSalary() {
    return request("/salary");
  }

  /** Salva a configuração de salário. `data` segue SalaryConfigIn. */
  function saveSalary(data) {
    return request("/salary", { method: "PUT", body: JSON.stringify(data) });
  }

  // ---------- Previsão financeira do mês ----------

  /**
   * Previsão determinística do saldo de fim de mês (salário + recorrentes +
   * contas + saldo atual). Em erro devolve null para o dashboard tratar.
   */
  async function getForecast(year, month, includeSalary = true) {
    const now = new Date();
    const y = year || now.getFullYear();
    const m = month || now.getMonth() + 1;
    // include_salary=false = "modo sem salário": projeta o saldo sem contar com
    // o pagamento ainda não recebido.
    const salarioParam = includeSalary ? "" : "&include_salary=false";
    try {
      return await request(`/forecast?year=${y}&month=${m}${salarioParam}`);
    } catch (_) {
      return null;
    }
  }

  // ---------- Conselhos (IA gestora / fallback) ----------

  /**
   * Busca os insights do mês no backend (GET /advice). O backend roda as
   * regras determinísticas (offline) e, se houver GROQ_API_KEY, acrescenta
   * um conselho personalizado da IA (Groq).
   *
   * Retorna { year, month, llm_used, insights: [...] } ou `null` se o
   * endpoint não existir/falhar — aí o chamador cai no fallback local.
   */
  async function getAdvice(year, month) {
    try {
      return await request(`/advice?year=${year}&month=${month}`);
    } catch (_) {
      return null; // sem endpoint/erro -> fallback local (regras no front)
    }
  }

  /**
   * Estado das integrações de IA (GET /ai/status): se Groq/OpenAI têm chave.
   * Usado para mostrar um aviso de "configure sua chave" quando a IA roda só
   * com as regras offline. Em erro devolve null (a página simplesmente omite).
   */
  async function getAIStatus() {
    try {
      return await request("/ai/status");
    } catch (_) {
      return null;
    }
  }

  return {
    BASE, request, getMeta,
    fetchTransactions, getTransaction, createTransaction,
    deleteTransaction, updateTransaction,
    getAccounts, createAccount, updateAccount, deleteAccount,
    getCards, createCard, updateCard, deleteCard, getCardStatements,
    getGoals, createGoal, updateGoal, deleteGoal,
    getAlerts,
    suggestCategory,
    getRecurring, createRecurring, updateRecurring, deleteRecurring,
    suggestRecurring, getDetectedRecurring,
    getVencimentos, createVencimento, updateVencimento, deleteVencimento,
    payVencimento, getCashFlow,
    previewImport, confirmImport,
    getHealthScore,
    getSalary, saveSalary, getForecast,
    getMonthlyReport, getMonthlyRange, getAdvice, getAIStatus,
  };
})();
