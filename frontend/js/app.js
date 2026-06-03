/* =========================================================
   Finance App — ORQUESTRADOR (app.js)
   ---------------------------------------------------------
   Ponto de entrada de TODAS as páginas. Um único arquivo serve
   o app inteiro: ele lê `document.body.dataset.page` e roda a
   inicialização correta (dashboard, lançamentos, etc.).

   Papel do app.js: ligar eventos e COORDENAR Api (dados) + UI
   (tela). Ele não formata nem faz fetch direto — delega.

   Ordem dos <script> no HTML: utils.js, api.js, ui.js, app.js,
   além do Chart.js (CDN) antes do ui.js para os gráficos.
   ========================================================= */

(() => {
  const { $, $$, hojeISO, nomeMes, MONTHS, formatarMoeda, formatarData,
          agrupaSoma, validarTransacao, variacaoPct, debounce } = Utils;

  // Cache das listas de /meta (carregado uma vez por página).
  let META = null;

  // ---------- Helpers compartilhados ----------

  /**
   * Monta o seletor de período (ano/mês) que algumas páginas colocam
   * na topbar. Preenche os meses, define o mês atual e liga eventos.
   * `onChange` roda quando o usuário troca período ou clica em Atualizar.
   * Retorna () => ({ year, month }).
   */
  function setupPeriod(onChange) {
    const monthSel = $("#month");
    if (monthSel && !monthSel.options.length) {
      MONTHS.forEach((nome, i) => {
        const opt = document.createElement("option");
        opt.value = i + 1;
        opt.textContent = nome;
        monthSel.appendChild(opt);
      });
    }
    const now = new Date();
    if ($("#year"))  $("#year").value = now.getFullYear();
    if (monthSel)    monthSel.value = now.getMonth() + 1;

    $("#year")?.addEventListener("change", onChange);
    monthSel?.addEventListener("change", onChange);
    $("#reload")?.addEventListener("click", onChange);

    return () => ({
      year: Number($("#year")?.value) || now.getFullYear(),
      month: Number($("#month")?.value) || now.getMonth() + 1,
    });
  }

  /** Carrega /meta uma vez. Em falha, mostra status e relança. */
  async function ensureMeta() {
    if (META) return META;
    try {
      META = await Api.getMeta();
      UI.clearStatus();
    } catch (e) {
      UI.showStatus(e.message);
      throw e;
    }
    return META;
  }

  // =========================================================
  // PÁGINA: DASHBOARD
  // =========================================================
  async function initDashboard() {
    UI.mountLayout({
      page: "dashboard",
      title: "📊 Dashboard",
      topbarExtra: periodHTML(),
    });

    const getPeriod = setupPeriod(load);
    $("#btn-nova")?.addEventListener("click", () => {
      location.href = "pages/lancamentos.html";
    });

    async function load() {
      const { year, month } = getPeriod();
      let summary;
      try {
        summary = await Api.getMonthlyReport(year, month);
      } catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();

      UI.renderKPIs(summary);

      // Alertas pendentes (não lidos) do mês selecionado. Seção some se vazia.
      try {
        const alerts = await Api.getAlerts(year, month);
        const sec = $("#alerts-section");
        const naoLidos = UI.unreadAlerts(alerts);
        if (naoLidos.length) {
          if (sec) sec.hidden = false;
          UI.renderAlerts(alerts, $("#dash-alerts"), {
            onChange: () => { if ($("#dash-alerts").children.length === 0 && sec) sec.hidden = true; },
          });
        } else if (sec) {
          sec.hidden = true;
        }
      } catch (e) {
        console.warn("Falha ao carregar alertas:", e.message);
      }

      // Saldos por conta (independe do período: saldo é acumulado).
      try {
        const accounts = await Api.getAccounts();
        UI.renderAccountCards(accounts, $("#accounts-cards"));
      } catch (e) {
        // Não derruba o dashboard se /accounts falhar; só loga.
        console.warn("Falha ao carregar saldos:", e.message);
      }

      // Cartões: fatura/uso do mês selecionado. A seção só aparece se houver
      // cartões cadastrados.
      try {
        const cards = await Api.getCards(year, month);
        const sec = $("#cards-section");
        if (cards && cards.length) {
          if (sec) sec.hidden = false;
          UI.renderCardCards(cards, $("#dash-cards"));
        } else if (sec) {
          sec.hidden = true;
        }
      } catch (e) {
        console.warn("Falha ao carregar cartões:", e.message);
      }

      // Metas em progresso (do mês selecionado). Seção some se não houver.
      try {
        const goals = await Api.getGoals(year, month);
        const sec = $("#goals-section");
        if (goals && goals.length) {
          if (sec) sec.hidden = false;
          UI.renderGoalCards(goals, $("#dash-goals"));
        } else if (sec) {
          sec.hidden = true;
        }
      } catch (e) {
        console.warn("Falha ao carregar metas:", e.message);
      }

      // Últimas transações (as 8 mais recentes do mês).
      const recentes = [...summary.transactions]
        .sort((a, b) => (a.date < b.date ? 1 : -1))
        .slice(0, 8);
      UI.renderTransactionsTable(recentes, {
        tbody: $("#tbody"),
        emptyEl: $("#empty"),
        withActions: false,
      });

      // Gráficos.
      UI.renderPie("chart-category", summary.expenses_by_category);
      UI.renderBar("chart-person", summary.expenses_by_person, "#3B82F6");

      // Conselho rápido (regras locais).
      const { dicas } = UI.conselhoLocal(summary);
      const top = dicas[0];
      $("#quick-advice").textContent = top
        ? top.texto
        : "Sem dados suficientes para um conselho neste mês.";
    }

    await load();
  }

  // =========================================================
  // PÁGINA: LANÇAMENTOS
  // =========================================================
  async function initLancamentos() {
    UI.mountLayout({ page: "lancamentos", title: "💸 Lançamentos" });

    try { await ensureMeta(); } catch { return; }

    // ---- Estado da listagem (filtros/ordenação/paginação no cliente) ----
    let todas = [];          // todas as transações vindas da API
    let editandoId = null;   // id em edição (null = criando)
    let categoriaManual = false; // usuário escolheu a categoria na mão?
    let ordem = { campo: "date", asc: false };
    let pagina = 1;
    const PAGE_SIZE = 12;

    // ---- Formulário ----
    UI.fillSelect($("#payment_method"), META.payment_methods);
    UI.fillSelect($("#spent_by"), META.people);
    UI.fillSelect($("#account"), META.accounts || []);
    UI.fillSelect($("#card"), META.cards || [], { keepFirst: true });
    $("#date").value = hojeISO();
    aplicarCategorias();

    $$('input[name="type"]').forEach((r) =>
      r.addEventListener("change", () => {
        aplicarCategorias();
        // Tipo mudou: as categorias mudam, então liberamos a sugestão de novo.
        categoriaManual = false;
        sugerirCategoria();
      }));
    $("#category").addEventListener("change", () => {
      $("#custom-category-wrap").hidden = $("#category").value !== "Outros";
      // Mexeu na categoria: respeita a escolha e some o selo da IA.
      categoriaManual = true;
      $("#cat-ai-badge").hidden = true;
    });
    // Ao digitar a descrição, pede sugestão de categoria (com debounce
    // para não chamar a API a cada tecla).
    $("#description").addEventListener("input", debounce(sugerirCategoria, 450));

    /**
     * Pede a sugestão de categoria à IA e PREENCHE o campo automaticamente,
     * a menos que o usuário já tenha escolhido manualmente. O selo "🤖 IA"
     * aparece para deixar claro que foi sugestão (e que dá pra trocar).
     */
    async function sugerirCategoria() {
      const desc = $("#description").value.trim();
      const badge = $("#cat-ai-badge");
      if (categoriaManual || desc.length < 3) { badge.hidden = true; return; }

      const type = document.querySelector('input[name="type"]:checked').value;
      const { category, confidence } = await Api.suggestCategory(desc, type);

      // Enquanto a chamada voltava, o usuário pode ter mexido na categoria.
      if (categoriaManual) return;

      const select = $("#category");
      const existe = category && [...select.options].some((o) => o.value === category);
      if (existe && confidence >= 0.5) {
        select.value = category;
        $("#custom-category-wrap").hidden = true;
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }
    $("#spent_by").addEventListener("change", () => {
      $("#custom-person-wrap").hidden = $("#spent_by").value !== "Outro";
    });
    $("#form").addEventListener("submit", onSubmit);
    $("#btn-cancel-edit").addEventListener("click", resetForm);

    function aplicarCategorias() {
      const type = document.querySelector('input[name="type"]:checked').value;
      const cats = type === "receita" ? META.income_categories : META.expense_categories;
      UI.fillSelect($("#category"), cats);
      $("#custom-category-wrap").hidden = $("#category").value !== "Outros";
    }

    function resetForm() {
      $("#form").reset();
      editandoId = null;
      categoriaManual = false;
      $("#cat-ai-badge").hidden = true;
      $("#date").value = hojeISO();
      $("#form-title").textContent = "➕ Nova transação";
      $("#btn-save").textContent = "💾 Salvar";
      $("#btn-cancel-edit").hidden = true;
      $("#custom-category-wrap").hidden = true;
      $("#custom-person-wrap").hidden = true;
      aplicarCategorias();
    }

    async function onSubmit(ev) {
      ev.preventDefault();
      const msg = $("#form-msg");
      const type = document.querySelector('input[name="type"]:checked').value;

      let category = $("#category").value;
      if (category === "Outros") category = $("#custom-category").value.trim();
      let spentBy = $("#spent_by").value;
      if (spentBy === "Outro") spentBy = $("#custom-person").value.trim();

      const payload = {
        date: $("#date").value,
        description: $("#description").value.trim(),
        amount: parseFloat($("#amount").value),
        type,
        category,
        payment_method: $("#payment_method").value,
        spent_by: spentBy || "Eu",
        account: $("#account").value || "Carteira",
        card: $("#card").value || "",
      };

      const { ok, erros } = validarTransacao(payload);
      if (!ok) {
        msg.textContent = "⚠ " + erros.join(" ");
        msg.className = "form-msg err";
        return;
      }

      $("#btn-save").disabled = true;
      try {
        if (editandoId === null) {
          const criada = await Api.createTransaction(payload);
          UI.showMessage("ok", `Transação criada (ID ${criada.id}).`);
        } else {
          await Api.updateTransaction(editandoId, payload);
          UI.showMessage("ok", "Transação atualizada.");
        }
        msg.textContent = "";
        resetForm();
        await carregar();
      } catch (e) {
        msg.textContent = "⚠ " + e.message;
        msg.className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#btn-save").disabled = false;
      }
    }

    function editar(tx) {
      editandoId = tx.id;
      // Editando: a categoria já existe, então não deixamos a IA sobrescrever.
      categoriaManual = true;
      $("#cat-ai-badge").hidden = true;
      // Marca o tipo e recarrega categorias antes de selecionar.
      document.querySelector(`input[name="type"][value="${tx.type}"]`).checked = true;
      aplicarCategorias();
      $("#description").value = tx.description;
      $("#amount").value = tx.amount;
      $("#date").value = tx.date.slice(0, 10);

      // Categoria pode não estar na lista (foi "Outros"): trata.
      if ([...$("#category").options].some((o) => o.value === tx.category)) {
        $("#category").value = tx.category;
        $("#custom-category-wrap").hidden = true;
      } else {
        $("#category").value = "Outros";
        $("#custom-category-wrap").hidden = false;
        $("#custom-category").value = tx.category;
      }
      $("#payment_method").value = tx.payment_method;
      // Conta da transação (se ainda existir na lista).
      if (tx.account && [...$("#account").options].some((o) => o.value === tx.account)) {
        $("#account").value = tx.account;
      }
      // Cartão da transação (vazio = nenhum).
      $("#card").value = (tx.card && [...$("#card").options].some((o) => o.value === tx.card)) ? tx.card : "";
      if ([...$("#spent_by").options].some((o) => o.value === tx.spent_by)) {
        $("#spent_by").value = tx.spent_by;
        $("#custom-person-wrap").hidden = true;
      } else {
        $("#spent_by").value = "Outro";
        $("#custom-person-wrap").hidden = false;
        $("#custom-person").value = tx.spent_by;
      }

      $("#form-title").textContent = `✏️ Editar transação #${tx.id}`;
      $("#btn-save").textContent = "💾 Salvar alterações";
      $("#btn-cancel-edit").hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
      UI.showMessage("info", "Editar = criar nova versão e remover a antiga (a API não tem update).");
    }

    async function excluir(id) {
      if (!confirm(`Excluir a transação ${id}?`)) return;
      try {
        await Api.deleteTransaction(id);
        UI.showMessage("ok", "Transação removida.");
        if (editandoId === id) resetForm();
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    // ---- Listagem + filtros ----
    UI.fillSelect($("#f-category"),
      [...new Set([...META.expense_categories, ...META.income_categories])],
      { keepFirst: true });
    UI.fillSelect($("#f-person"), META.people, { keepFirst: true });
    UI.fillSelect($("#f-payment"), META.payment_methods, { keepFirst: true });
    UI.fillSelect($("#f-account"), META.accounts || [], { keepFirst: true });

    ["f-type", "f-person", "f-category", "f-payment", "f-account"].forEach((id) =>
      $("#" + id).addEventListener("change", () => { pagina = 1; render(); }));
    $("#f-search").addEventListener("input", debounce(() => { pagina = 1; render(); }, 250));
    $("#f-clear").addEventListener("click", () => {
      ["f-type", "f-person", "f-category", "f-payment", "f-account", "f-search"].forEach((id) => ($("#" + id).value = ""));
      pagina = 1; render();
    });

    // Ordenação ao clicar nos cabeçalhos marcados com data-sort.
    $$("#table thead th.sortable").forEach((th) =>
      th.addEventListener("click", () => {
        const campo = th.dataset.sort;
        ordem = { campo, asc: ordem.campo === campo ? !ordem.asc : true };
        render();
      }));

    $("#prev-page").addEventListener("click", () => { if (pagina > 1) { pagina--; render(); } });
    $("#next-page").addEventListener("click", () => { pagina++; render(); });

    function filtrar() {
      const fType = $("#f-type").value;
      const fPerson = $("#f-person").value;
      const fCat = $("#f-category").value;
      const fPay = $("#f-payment").value;
      const fAccount = $("#f-account").value;
      const fBusca = $("#f-search").value.trim().toLowerCase();

      return todas.filter((t) =>
        (!fType || t.type === fType) &&
        (!fPerson || t.spent_by === fPerson) &&
        (!fCat || t.category === fCat) &&
        (!fPay || t.payment_method === fPay) &&
        (!fAccount || t.account === fAccount) &&
        (!fBusca || t.description.toLowerCase().includes(fBusca)));
    }

    function ordenar(lista) {
      const { campo, asc } = ordem;
      const dir = asc ? 1 : -1;
      return [...lista].sort((a, b) => {
        let va = a[campo], vb = b[campo];
        if (campo === "amount") { va = Number(va); vb = Number(vb); }
        else { va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }
        return va < vb ? -dir : va > vb ? dir : 0;
      });
    }

    function render() {
      const filtradas = ordenar(filtrar());
      const totalPag = Math.max(1, Math.ceil(filtradas.length / PAGE_SIZE));
      pagina = Math.min(pagina, totalPag);
      const inicio = (pagina - 1) * PAGE_SIZE;
      const visiveis = filtradas.slice(inicio, inicio + PAGE_SIZE);

      UI.renderTransactionsTable(visiveis, {
        tbody: $("#tbody"),
        emptyEl: $("#empty"),
        onDelete: excluir,
        onEdit: editar,
      });

      $("#page-info").textContent = `${filtradas.length} resultado(s) • página ${pagina}/${totalPag}`;
      $("#prev-page").disabled = pagina <= 1;
      $("#next-page").disabled = pagina >= totalPag;

      // Indicador de ordenação no cabeçalho.
      $$("#table thead th.sortable").forEach((th) => {
        const base = th.textContent.replace(/[ ▲▼]+$/, "");
        th.textContent = th.dataset.sort === ordem.campo ? `${base} ${ordem.asc ? "▲" : "▼"}` : base;
      });
    }

    async function carregar() {
      try {
        todas = await Api.fetchTransactions(); // tudo; filtra no cliente
        UI.clearStatus();
      } catch (e) { UI.showStatus(e.message); return; }
      render();
    }

    await carregar();
  }

  // =========================================================
  // PÁGINA: RELATÓRIOS
  // =========================================================
  async function initRelatorios() {
    UI.mountLayout({
      page: "relatorios",
      title: "📈 Relatórios",
      topbarExtra: periodHTML(),
    });

    const getPeriod = setupPeriod(load);
    // Seletor de quantos meses comparar/evoluir (2/3/6).
    $("#compare-months")?.addEventListener("change", load);

    async function load() {
      const { year, month } = getPeriod();
      const nMeses = Number($("#compare-months")?.value) || 6;
      let serie;
      try {
        // Últimos N meses (o último é o selecionado) para evolução + comparação.
        serie = await Api.getMonthlyRange(year, month, nMeses);
        UI.clearStatus();
      } catch (e) { UI.showStatus(e.message); return; }

      const atual = serie[serie.length - 1];
      const anterior = serie.length > 1 ? serie[serie.length - 2] : null;

      // ---- Resumo do período ----
      $("#sum-incomes").textContent = formatarMoeda(atual.total_incomes);
      $("#sum-expenses").textContent = formatarMoeda(atual.total_expenses);
      $("#sum-balance").textContent = formatarMoeda(atual.balance);

      // ---- Tabela de comparação (receitas, despesas, saldo) ----
      renderCompareTable(atual, anterior);

      // ---- Gráficos ----
      UI.renderPie("rep-category", atual.expenses_by_category);
      UI.renderBar("rep-person", atual.expenses_by_person, "#8B5CF6");

      // Forma de pagamento: a API não agrupa por isso, então calculamos
      // a partir das transações de despesa do mês.
      const despesas = atual.transactions.filter((t) => t.type === "despesa");
      UI.renderBar("rep-payment", agrupaSoma(despesas, "payment_method", "amount"), "#F59E0B");

      // Evolução mensal (receitas x despesas).
      const labels = serie.map((s) => nomeMes(s.month));
      UI.renderLine("rep-evolution", labels, [
        { label: "Receitas", data: serie.map((s) => s.total_incomes), color: "#10B981" },
        { label: "Despesas", data: serie.map((s) => s.total_expenses), color: "#EF4444" },
      ]);

      // Comparação por categoria (atual vs anterior, lado a lado).
      renderCatCompare(atual, anterior);

      // Tabela por categoria.
      renderCategoriaTabela(atual.expenses_by_category, atual.total_expenses);
    }

    /** Linha da tabela de comparação com seta e cor conforme a variação. */
    function compareRow(label, atualVal, antVal, lowerIsBetter) {
      const tem = antVal !== null && antVal !== undefined;
      const delta = tem ? variacaoPct(atualVal, antVal) : 0;
      // Para despesas, subir é ruim (vermelho). Para receitas/saldo, subir é bom.
      const bom = lowerIsBetter ? delta <= 0 : delta >= 0;
      const cls = !tem ? "" : (delta === 0 ? "" : bom ? "down" : "up");
      const seta = !tem ? "—" : `${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(1)}%`;
      return `<tr>
        <td>${label}</td>
        <td class="num">${tem ? formatarMoeda(antVal) : "—"}</td>
        <td class="num">${formatarMoeda(atualVal)}</td>
        <td class="num"><span class="delta ${cls}">${seta}</span></td>
      </tr>`;
    }

    function renderCompareTable(atual, anterior) {
      // Atualiza os cabeçalhos com os nomes dos meses.
      $("#compare-th-curr").textContent = `${nomeMes(atual.month)}/${atual.year}`;
      $("#compare-th-prev").textContent = anterior ? `${nomeMes(anterior.month)}/${anterior.year}` : "—";
      $("#compare-tbody").innerHTML =
        compareRow("Receitas", atual.total_incomes, anterior?.total_incomes ?? null, false) +
        compareRow("Despesas", atual.total_expenses, anterior?.total_expenses ?? null, true) +
        compareRow("Saldo", atual.balance, anterior?.balance ?? null, false);
    }

    function renderCatCompare(atual, anterior) {
      const catsAtual = atual.expenses_by_category || {};
      const catsAnt = (anterior && anterior.expenses_by_category) || {};
      // Top 7 categorias pela soma dos dois meses.
      const todas = {};
      for (const [k, v] of Object.entries(catsAtual)) todas[k] = (todas[k] || 0) + v;
      for (const [k, v] of Object.entries(catsAnt)) todas[k] = (todas[k] || 0) + v;
      const labels = Object.entries(todas).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([k]) => k);
      UI.renderGroupedBars("rep-cat-compare", labels, [
        { label: anterior ? nomeMes(anterior.month) : "Anterior", data: labels.map((l) => catsAnt[l] || 0), color: "#64748B" },
        { label: nomeMes(atual.month), data: labels.map((l) => catsAtual[l] || 0), color: "#3B82F6" },
      ]);
    }

    function renderCategoriaTabela(porCategoria, total) {
      const tbody = $("#cat-tbody");
      tbody.innerHTML = "";
      const entries = Object.entries(porCategoria).sort((a, b) => b[1] - a[1]);
      $("#cat-empty").hidden = entries.length > 0;
      for (const [cat, val] of entries) {
        const pct = total > 0 ? (val / total) * 100 : 0;
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${cat}</td><td class="num">${formatarMoeda(val)}</td><td class="num">${pct.toFixed(1)}%</td>`;
        tbody.appendChild(tr);
      }
    }

    await load();
  }

  // =========================================================
  // PÁGINA: CONFIGURAÇÕES
  // =========================================================
  async function initConfiguracoes() {
    UI.mountLayout({ page: "configuracoes", title: "⚙️ Configurações" });
    try { await ensureMeta(); } catch { return; }

    const chips = (items) => items.map((i) => `<span class="chip">${Utils.escapeHtml(i)}</span>`).join("");
    $("#cfg-income").innerHTML = chips(META.income_categories);
    $("#cfg-expense").innerHTML = chips(META.expense_categories);
    $("#cfg-payment").innerHTML = chips(META.payment_methods);
    $("#cfg-people").innerHTML = chips(META.people);

    // ---- Gerenciador de contas / saldos ----
    let editAccId = null; // id em edição (null = criando)

    const accForm = $("#acc-form");
    const accMsg = $("#acc-msg");

    function resetAccForm() {
      accForm.reset();
      editAccId = null;
      $("#acc-id").value = "";
      $("#acc-color").value = "#3B82F6";
      $("#acc-save").textContent = "💾 Adicionar conta";
      $("#acc-cancel").hidden = true;
      accMsg.textContent = "";
    }

    async function carregarContas() {
      let contas;
      try {
        contas = await Api.getAccounts();
      } catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();

      const lista = $("#acc-list");
      lista.innerHTML = "";
      if (!contas.length) {
        lista.innerHTML = `<p class="muted">Nenhuma conta ainda. Crie a primeira acima.</p>`;
        return;
      }
      for (const c of contas) {
        const neg = Number(c.current_balance) < 0;
        const row = document.createElement("div");
        row.className = "account-row";
        row.style.setProperty("--acc-color", c.color || "var(--info)");
        row.innerHTML = `
          <span class="a-icon">${Utils.escapeHtml(c.icon || "💰")}</span>
          <span>
            <span class="a-name">${Utils.escapeHtml(c.name)}</span>
            <span class="a-kind"> • ${Utils.escapeHtml(c.kind)}</span>
          </span>
          <span class="a-balance ${neg ? "neg" : ""}">${formatarMoeda(c.current_balance)}</span>
          <span class="a-actions">
            <button class="icon-btn" data-edit="${c.id}" title="Editar">✏️</button>
            <button class="icon-btn danger" data-del="${c.id}" title="Excluir">🗑</button>
          </span>`;
        lista.appendChild(row);
      }

      lista.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => editarConta(contas.find((x) => x.id === Number(b.dataset.edit)))));
      lista.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => excluirConta(Number(b.dataset.del))));
    }

    function editarConta(c) {
      if (!c) return;
      editAccId = c.id;
      $("#acc-id").value = c.id;
      $("#acc-name").value = c.name;
      $("#acc-kind").value = c.kind;
      $("#acc-initial").value = c.initial_balance;
      $("#acc-icon").value = c.icon || "";
      $("#acc-color").value = /^#[0-9a-fA-F]{6}$/.test(c.color) ? c.color : "#3B82F6";
      $("#acc-save").textContent = "💾 Salvar alterações";
      $("#acc-cancel").hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function excluirConta(id) {
      if (!confirm("Excluir esta conta? (só é possível se não houver transações nela)")) return;
      try {
        await Api.deleteAccount(id);
        UI.showMessage("ok", "Conta removida.");
        if (editAccId === id) resetAccForm();
        await carregarContas();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    accForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const payload = {
        name: $("#acc-name").value.trim(),
        kind: $("#acc-kind").value,
        initial_balance: parseFloat($("#acc-initial").value) || 0,
        color: $("#acc-color").value,
        icon: $("#acc-icon").value.trim() || "💰",
      };
      if (!payload.name) {
        accMsg.textContent = "⚠ Informe o nome da conta.";
        accMsg.className = "form-msg err";
        return;
      }
      $("#acc-save").disabled = true;
      try {
        if (editAccId === null) {
          await Api.createAccount(payload);
          UI.showMessage("ok", "Conta criada.");
        } else {
          await Api.updateAccount(editAccId, payload);
          UI.showMessage("ok", "Conta atualizada.");
        }
        resetAccForm();
        await carregarContas();
      } catch (e) {
        accMsg.textContent = "⚠ " + e.message;
        accMsg.className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#acc-save").disabled = false;
      }
    });

    $("#acc-cancel").addEventListener("click", resetAccForm);

    await carregarContas();
  }

  // =========================================================
  // PÁGINA: CONSELHOS IA
  // =========================================================
  async function initConselhos() {
    UI.mountLayout({
      page: "conselhos",
      title: "🤖 Conselhos IA",
      topbarExtra: periodHTML(),
    });

    const getPeriod = setupPeriod(() => {}); // só guarda o período
    $("#btn-gerar").addEventListener("click", gerar);

    // Mapeia a severidade do insight para a cor (variável CSS) e um ícone.
    const SEV = {
      success: { cor: "primary", ico: "✅" },
      info:    { cor: "info",    ico: "💡" },
      warning: { cor: "warning", ico: "⚠️" },
      danger:  { cor: "danger",  ico: "🚨" },
    };

    function cardInsight(ins) {
      const sev = SEV[ins.severity] || SEV.info;
      const selo = ins.source === "llm"
        ? `<span class="badge badge-llm">🤖 IA</span>`
        : `<span class="badge">📐 Regra</span>`;
      return `
        <div class="card insight-card" style="border-left:4px solid var(--${sev.cor})">
          <div class="insight-head">
            <h3>${sev.ico} ${Utils.escapeHtml(ins.title)}</h3>
            ${selo}
          </div>
          <p>${Utils.escapeHtml(ins.message)}</p>
        </div>`;
    }

    async function gerar() {
      const { year, month } = getPeriod();
      const out = $("#advice-output");
      out.innerHTML = `<div class="loading-box"><span class="spinner"></span> Analisando suas finanças… (a IA pode levar alguns segundos)</div>`;

      // 1) Tenta o endpoint /advice (regras + IA Groq).
      const advice = await Api.getAdvice(year, month);

      if (advice && advice.insights) {
        const fonte = advice.llm_used
          ? "🤖 IA Groq + 📐 regras locais"
          : "📐 Regras locais (IA não configurada/indisponível)";
        out.innerHTML = `
          <p class="muted" style="margin-bottom:12px">Fonte: ${fonte} • ${nomeMes(month)}/${year}</p>
          ${advice.insights.map(cardInsight).join("")}`;
        return;
      }

      // 2) Fallback local: API fora do ar — usa as regras do próprio front.
      let summary;
      try {
        summary = await Api.getMonthlyReport(year, month);
      } catch (e) { out.innerHTML = `<p class="form-msg err">⚠ ${e.message}</p>`; return; }

      const { resumo, dicas } = UI.conselhoLocal(summary);
      const blocoDicas = dicas.map((d) =>
        `<div class="card" style="border-left:4px solid var(--${d.tipo === "ok" ? "primary" : d.tipo === "err" ? "danger" : "info"})">
           <p>${Utils.escapeHtml(d.texto)}</p></div>`).join("");
      out.innerHTML = `
        <p class="muted" style="margin-bottom:12px">Fonte: 📐 Análise local (API indisponível) • ${nomeMes(month)}/${year}</p>
        <div class="card"><h3>Resumo analisado</h3><p>${Utils.escapeHtml(resumo)}</p></div>
        ${blocoDicas}`;
    }

    // Gera automaticamente ao abrir.
    await gerar();
  }

  // =========================================================
  // PÁGINA: CARTÕES
  // =========================================================
  async function initCartoes() {
    UI.mountLayout({ page: "cartoes", title: "💳 Cartões de crédito" });

    let editId = null; // id do cartão em edição (null = criando)
    const form = $("#card-form");

    function resetCardForm() {
      form.reset();
      editId = null;
      $("#c-id").value = "";
      $("#c-color").value = "#8B5CF6";
      $("#card-form-title").textContent = "➕ Novo cartão";
      $("#c-save").textContent = "💾 Adicionar cartão";
      $("#c-cancel").hidden = true;
      $("#c-msg").textContent = "";
    }

    async function carregar() {
      let cartoes;
      try {
        cartoes = await Api.getCards();
      } catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();

      // Cards visuais de uso de limite (topo).
      UI.renderCardCards(cartoes, $("#cards-cards"));

      // Lista de gerenciamento (editar/excluir).
      const lista = $("#card-list");
      lista.innerHTML = "";
      for (const c of cartoes) {
        const row = document.createElement("div");
        row.className = "card-row";
        row.style.setProperty("--acc-color", c.color || "#8B5CF6");
        row.innerHTML = `
          <span>
            <span class="c-name">💳 ${Utils.escapeHtml(c.name)}</span>
            <span class="c-meta"> • ${Utils.escapeHtml(c.brand)} • limite ${formatarMoeda(c.limit_total)} • fecha dia ${c.closing_day} / vence dia ${c.due_day} • ${Utils.escapeHtml(c.status)}</span>
          </span>
          <span class="c-actions">
            <button class="icon-btn" data-edit="${c.id}" title="Editar">✏️</button>
            <button class="icon-btn danger" data-del="${c.id}" title="Excluir">🗑</button>
          </span>`;
        lista.appendChild(row);
      }
      lista.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => editar(cartoes.find((x) => x.id === Number(b.dataset.edit)))));
      lista.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => excluir(Number(b.dataset.del))));
    }

    function editar(c) {
      if (!c) return;
      editId = c.id;
      $("#c-id").value = c.id;
      $("#c-name").value = c.name;
      $("#c-brand").value = c.brand;
      $("#c-limit").value = c.limit_total;
      $("#c-status").value = c.status;
      $("#c-closing").value = c.closing_day;
      $("#c-due").value = c.due_day;
      $("#c-color").value = /^#[0-9a-fA-F]{6}$/.test(c.color) ? c.color : "#8B5CF6";
      $("#card-form-title").textContent = `✏️ Editar cartão`;
      $("#c-save").textContent = "💾 Salvar alterações";
      $("#c-cancel").hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function excluir(id) {
      if (!confirm("Excluir este cartão? As transações antigas mantêm o histórico.")) return;
      try {
        await Api.deleteCard(id);
        UI.showMessage("ok", "Cartão removido.");
        if (editId === id) resetCardForm();
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const payload = {
        name: $("#c-name").value.trim(),
        brand: $("#c-brand").value,
        limit_total: parseFloat($("#c-limit").value) || 0,
        closing_day: parseInt($("#c-closing").value, 10) || 1,
        due_day: parseInt($("#c-due").value, 10) || 10,
        color: $("#c-color").value,
        status: $("#c-status").value,
      };
      if (!payload.name) {
        $("#c-msg").textContent = "⚠ Informe o nome do cartão.";
        $("#c-msg").className = "form-msg err";
        return;
      }
      $("#c-save").disabled = true;
      try {
        if (editId === null) {
          await Api.createCard(payload);
          UI.showMessage("ok", "Cartão criado.");
        } else {
          await Api.updateCard(editId, payload);
          UI.showMessage("ok", "Cartão atualizado.");
        }
        resetCardForm();
        await carregar();
      } catch (e) {
        $("#c-msg").textContent = "⚠ " + e.message;
        $("#c-msg").className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#c-save").disabled = false;
      }
    });

    $("#c-cancel").addEventListener("click", resetCardForm);

    await carregar();
  }

  // =========================================================
  // PÁGINA: ALERTAS
  // =========================================================
  async function initAlertas() {
    UI.mountLayout({ page: "alertas", title: "🔔 Alertas" });
    const now = new Date();

    async function carregar() {
      let alerts;
      try {
        alerts = await Api.getAlerts(now.getFullYear(), now.getMonth() + 1);
      } catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();
      UI.renderAlerts(alerts, $("#alerts-list"));
    }

    $("#alerts-reset").addEventListener("click", async () => {
      UI.clearReadAlerts();
      await carregar();
      UI.refreshAlertBadge();
      UI.showMessage("ok", "Alertas lidos reexibidos.");
    });

    await carregar();
  }

  // =========================================================
  // PÁGINA: METAS
  // =========================================================
  async function initMetas() {
    UI.mountLayout({ page: "metas", title: "🎯 Metas financeiras" });
    try { await ensureMeta(); } catch { return; }

    // Categorias de despesa para o tipo "limite de gasto".
    UI.fillSelect($("#g-category"), META.expense_categories);

    let editId = null;
    const form = $("#goal-form");

    // Mostra os campos certos conforme o tipo de meta.
    function aplicarTipo() {
      const kind = $("#g-kind").value;
      $("#g-category-wrap").hidden = kind !== "limite_gasto";
      // "Valor já alcançado" só faz sentido em poupança/dívida (no limite
      // de gasto o progresso é calculado pelas despesas do mês).
      $("#g-current-wrap").hidden = kind === "limite_gasto";
    }
    $("#g-kind").addEventListener("change", aplicarTipo);
    aplicarTipo();

    function resetGoalForm() {
      form.reset();
      editId = null;
      $("#g-id").value = "";
      $("#g-color").value = "#10B981";
      $("#goal-form-title").textContent = "➕ Nova meta";
      $("#g-save").textContent = "💾 Adicionar meta";
      $("#g-cancel").hidden = true;
      $("#g-msg").textContent = "";
      aplicarTipo();
    }

    async function carregar() {
      let metas;
      try { metas = await Api.getGoals(); }
      catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();

      UI.renderGoalCards(metas, $("#goals-cards"));

      const lista = $("#goal-list");
      lista.innerHTML = "";
      for (const g of metas) {
        const row = document.createElement("div");
        row.className = "goal-row";
        row.style.setProperty("--acc-color", g.color || "var(--primary)");
        const extra = g.kind === "limite_gasto"
          ? `categoria ${Utils.escapeHtml(g.category)}`
          : `${formatarMoeda(g.current_amount)} de ${formatarMoeda(g.target_amount)}`;
        row.innerHTML = `
          <span>
            <span class="g-name">🎯 ${Utils.escapeHtml(g.name)}</span>
            <span class="g-meta"> • ${UI_GOAL_LABEL(g.kind)} • alvo ${formatarMoeda(g.target_amount)} • ${extra}${g.end_date ? " • até " + formatarData(g.end_date) : ""}</span>
          </span>
          <span class="g-actions">
            <button class="icon-btn" data-edit="${g.id}" title="Editar">✏️</button>
            <button class="icon-btn danger" data-del="${g.id}" title="Excluir">🗑</button>
          </span>`;
        lista.appendChild(row);
      }
      lista.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => editar(metas.find((x) => x.id === Number(b.dataset.edit)))));
      lista.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => excluir(Number(b.dataset.del))));
    }

    function editar(g) {
      if (!g) return;
      editId = g.id;
      $("#g-id").value = g.id;
      $("#g-name").value = g.name;
      $("#g-kind").value = g.kind;
      $("#g-target").value = g.target_amount;
      aplicarTipo();
      if ([...$("#g-category").options].some((o) => o.value === g.category)) {
        $("#g-category").value = g.category;
      }
      $("#g-current").value = g.current_amount;
      $("#g-start").value = g.start_date || "";
      $("#g-end").value = g.end_date || "";
      $("#g-color").value = /^#[0-9a-fA-F]{6}$/.test(g.color) ? g.color : "#10B981";
      $("#goal-form-title").textContent = "✏️ Editar meta";
      $("#g-save").textContent = "💾 Salvar alterações";
      $("#g-cancel").hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function excluir(id) {
      if (!confirm("Excluir esta meta?")) return;
      try {
        await Api.deleteGoal(id);
        UI.showMessage("ok", "Meta removida.");
        if (editId === id) resetGoalForm();
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const kind = $("#g-kind").value;
      const payload = {
        name: $("#g-name").value.trim(),
        kind,
        target_amount: parseFloat($("#g-target").value) || 0,
        category: kind === "limite_gasto" ? $("#g-category").value : "",
        start_date: $("#g-start").value || "",
        end_date: $("#g-end").value || "",
        current_amount: kind === "limite_gasto" ? 0 : (parseFloat($("#g-current").value) || 0),
        color: $("#g-color").value,
      };
      if (!payload.name || !(payload.target_amount > 0)) {
        $("#g-msg").textContent = "⚠ Informe nome e um valor-alvo maior que zero.";
        $("#g-msg").className = "form-msg err";
        return;
      }
      $("#g-save").disabled = true;
      try {
        if (editId === null) {
          await Api.createGoal(payload);
          UI.showMessage("ok", "Meta criada.");
        } else {
          await Api.updateGoal(editId, payload);
          UI.showMessage("ok", "Meta atualizada.");
        }
        resetGoalForm();
        await carregar();
      } catch (e) {
        $("#g-msg").textContent = "⚠ " + e.message;
        $("#g-msg").className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#g-save").disabled = false;
      }
    });

    $("#g-cancel").addEventListener("click", resetGoalForm);

    await carregar();
  }

  // Rótulo amigável do tipo de meta (espelha o do ui.js para a lista).
  function UI_GOAL_LABEL(kind) {
    return { limite_gasto: "Limite de gasto", poupanca: "Poupança", divida: "Quitar dívida" }[kind] || kind;
  }

  // ---------- HTML do seletor de período (reaproveitado) ----------
  function periodHTML() {
    return `
      <div class="period">
        <label>Ano <input type="number" id="year" min="2000" max="2100" /></label>
        <label>Mês <select id="month"></select></label>
        <button id="reload" class="btn btn-ghost btn-sm">↻ Atualizar</button>
      </div>`;
  }

  // =========================================================
  // BOOTSTRAP — escolhe o init conforme data-page do <body>
  // =========================================================
  const PAGES = {
    dashboard: initDashboard,
    lancamentos: initLancamentos,
    cartoes: initCartoes,
    metas: initMetas,
    alertas: initAlertas,
    relatorios: initRelatorios,
    configuracoes: initConfiguracoes,
    conselhos: initConselhos,
  };

  document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    const init = PAGES[page];
    if (init) {
      init().catch((e) => UI.showStatus("Erro inesperado: " + e.message));
    } else {
      console.warn("Página sem init definido:", page);
    }
  });
})();
