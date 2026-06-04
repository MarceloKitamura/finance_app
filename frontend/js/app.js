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

  // Atalho seguro para um ícone SVG (icons.js é carregado antes deste arquivo).
  const ic = (name, opts) => (typeof Icons !== "undefined" ? Icons.svg(name, opts) : "");

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
      title: "Dashboard",
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
    UI.mountLayout({ page: "lancamentos", title: "Lançamentos" });

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
     * a menos que o usuário já tenha escolhido manualmente. O selo "IA"
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

    // ---- Autopreenchimento por gastos recorrentes / histórico ----
    const recBox = $("#rec-suggestions");

    /** Busca sugestões e mostra o dropdown sob o campo descrição. */
    async function mostrarSugestoes() {
      const desc = $("#description").value.trim();
      if (desc.length < 2) { esconderSugestoes(); return; }
      let sugestoes;
      try { sugestoes = await Api.suggestRecurring(desc); }
      catch { esconderSugestoes(); return; }
      if (!sugestoes || !sugestoes.length) { esconderSugestoes(); return; }

      recBox.innerHTML = "";
      sugestoes.forEach((s, i) => {
        const tag = s.source === "template"
          ? `${ic("recurring", { size: 12 })} recorrente`
          : `${ic("clock", { size: 12 })} histórico`;
        const item = document.createElement("div");
        item.className = "rec-suggest-item";
        item.innerHTML = `
          <span class="rec-suggest-main">
            <span class="rec-suggest-desc">${Utils.escapeHtml(s.description)}</span>
            <span class="rec-suggest-meta">${Utils.escapeHtml(s.category)} • ${Utils.escapeHtml(s.payment_method)}${s.occurrences > 1 ? " • " + s.occurrences + "x" : ""}</span>
          </span>
          <span class="rec-suggest-amount">${formatarMoeda(s.amount)}</span>
          <span class="rec-suggest-tag">${tag}</span>`;
        item.addEventListener("click", () => aplicarSugestao(s));
        recBox.appendChild(item);
      });
      recBox.hidden = false;
    }

    function esconderSugestoes() { recBox.hidden = true; recBox.innerHTML = ""; }

    /** Preenche o formulário inteiro a partir de uma sugestão escolhida. */
    function aplicarSugestao(s) {
      // Ajusta o tipo (e recarrega as categorias) se for diferente.
      const radio = document.querySelector(`input[name="type"][value="${s.type}"]`);
      if (radio && !radio.checked) { radio.checked = true; aplicarCategorias(); }

      $("#description").value = s.description;
      if (s.amount) $("#amount").value = s.amount;

      // Categoria: usa o select se existir; senão cai em "Outros" + custom.
      const catSelect = $("#category");
      if ([...catSelect.options].some((o) => o.value === s.category)) {
        catSelect.value = s.category;
        $("#custom-category-wrap").hidden = true;
      } else if (s.category) {
        catSelect.value = "Outros";
        $("#custom-category-wrap").hidden = false;
        $("#custom-category").value = s.category;
      }
      // Respeita a escolha e impede a IA de sobrescrever a categoria.
      categoriaManual = true;
      $("#cat-ai-badge").hidden = true;

      if ([...$("#payment_method").options].some((o) => o.value === s.payment_method)) {
        $("#payment_method").value = s.payment_method;
      }
      if ([...$("#account").options].some((o) => o.value === s.account)) {
        $("#account").value = s.account;
      }
      $("#card").value = (s.card && [...$("#card").options].some((o) => o.value === s.card)) ? s.card : "";

      // Quem gastou (pode ser nome livre → "Outro" + custom).
      if ([...$("#spent_by").options].some((o) => o.value === s.spent_by)) {
        $("#spent_by").value = s.spent_by;
        $("#custom-person-wrap").hidden = true;
      } else if (s.spent_by) {
        $("#spent_by").value = "Outro";
        $("#custom-person-wrap").hidden = false;
        $("#custom-person").value = s.spent_by;
      }

      esconderSugestoes();
      $("#amount").focus();
    }

    $("#description").addEventListener("input", debounce(mostrarSugestoes, 350));
    // Fecha o dropdown ao clicar fora ou apertar Esc.
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".rec-suggest-field")) esconderSugestoes();
    });
    $("#description").addEventListener("keydown", (e) => {
      if (e.key === "Escape") esconderSugestoes();
    });

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
      $("#form-title").textContent = "Nova transação";
      $("#btn-save").innerHTML = ic("save") + " Salvar";
      $("#btn-cancel-edit").hidden = true;
      $("#custom-category-wrap").hidden = true;
      $("#custom-person-wrap").hidden = true;
      if (typeof esconderSugestoes === "function") esconderSugestoes();
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
        msg.textContent = erros.join(" ");
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
        msg.textContent = e.message;
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

      $("#form-title").textContent = `Editar transação #${tx.id}`;
      $("#btn-save").innerHTML = ic("save") + " Salvar alterações";
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

      // Indicador de ordenação no cabeçalho (seta SVG na coluna ativa).
      $$("#table thead th.sortable").forEach((th) => {
        if (th.dataset.label == null) th.dataset.label = th.textContent.trim();
        const ativo = th.dataset.sort === ordem.campo;
        const seta = ativo ? " " + ic(ordem.asc ? "arrow-up" : "arrow-down", { size: 13 }) : "";
        th.innerHTML = th.dataset.label + seta;
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

    // Aba "Importar extrato" (mesma página). Recarrega a lista ao importar.
    await setupImportar({ onImported: carregar });
    UI.wireTabs($("#lanc-tabs"));
  }

  // =========================================================
  // PÁGINA: RELATÓRIOS
  // =========================================================
  async function initRelatorios() {
    UI.mountLayout({
      page: "relatorios",
      title: "Relatórios",
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
      const seta = !tem ? "—" : `${ic(delta >= 0 ? "arrow-up" : "arrow-down", { size: 12 })} ${Math.abs(delta).toFixed(1)}%`;
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
    UI.mountLayout({ page: "configuracoes", title: "Configurações" });
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
      $("#acc-save").innerHTML = ic("save") + " Adicionar conta";
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
          <span class="a-icon">${c.icon ? Utils.escapeHtml(c.icon) : ic("wallet")}</span>
          <span>
            <span class="a-name">${Utils.escapeHtml(c.name)}</span>
            <span class="a-kind"> • ${Utils.escapeHtml(c.kind)}</span>
          </span>
          <span class="a-balance ${neg ? "neg" : ""}">${formatarMoeda(c.current_balance)}</span>
          <span class="a-actions">
            <button class="icon-btn" data-edit="${c.id}" title="Editar" aria-label="Editar">${ic("edit")}</button>
            <button class="icon-btn danger" data-del="${c.id}" title="Excluir" aria-label="Excluir">${ic("trash")}</button>
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
      $("#acc-save").innerHTML = ic("save") + " Salvar alterações";
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
        icon: $("#acc-icon").value.trim(),
      };
      if (!payload.name) {
        accMsg.textContent = "Informe o nome da conta.";
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
        accMsg.textContent = e.message;
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
  // PÁGINA: CARTÕES
  // =========================================================
  async function initCartoes() {
    UI.mountLayout({ page: "cartoes", title: "Cartões de crédito" });

    let editId = null; // id do cartão em edição (null = criando)
    const form = $("#card-form");

    function resetCardForm() {
      form.reset();
      editId = null;
      $("#c-id").value = "";
      $("#c-color").value = "#8B5CF6";
      $("#card-form-title").textContent = "Novo cartão";
      $("#c-save").innerHTML = ic("save") + " Adicionar cartão";
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
            <span class="c-name">${ic("card", { size: 16 })}${Utils.escapeHtml(c.name)}</span>
            <span class="c-meta"> • ${Utils.escapeHtml(c.brand)} • limite ${formatarMoeda(c.limit_total)} • fecha dia ${c.closing_day} / vence dia ${c.due_day} • ${Utils.escapeHtml(c.status)}</span>
          </span>
          <span class="c-actions">
            <button class="icon-btn" data-edit="${c.id}" title="Editar" aria-label="Editar">${ic("edit")}</button>
            <button class="icon-btn danger" data-del="${c.id}" title="Excluir" aria-label="Excluir">${ic("trash")}</button>
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
      $("#card-form-title").textContent = `Editar cartão`;
      $("#c-save").innerHTML = ic("save") + " Salvar alterações";
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
        $("#c-msg").textContent = "Informe o nome do cartão.";
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
        $("#c-msg").textContent = e.message;
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
    UI.mountLayout({ page: "alertas", title: "Alertas" });
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
    UI.mountLayout({ page: "metas", title: "Metas financeiras" });
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
      $("#goal-form-title").textContent = "Nova meta";
      $("#g-save").innerHTML = ic("save") + " Adicionar meta";
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
            <span class="g-name">${ic("target", { size: 16 })}${Utils.escapeHtml(g.name)}</span>
            <span class="g-meta"> • ${UI_GOAL_LABEL(g.kind)} • alvo ${formatarMoeda(g.target_amount)} • ${extra}${g.end_date ? " • até " + formatarData(g.end_date) : ""}</span>
          </span>
          <span class="g-actions">
            <button class="icon-btn" data-edit="${g.id}" title="Editar" aria-label="Editar">${ic("edit")}</button>
            <button class="icon-btn danger" data-del="${g.id}" title="Excluir" aria-label="Excluir">${ic("trash")}</button>
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
      $("#goal-form-title").textContent = "Editar meta";
      $("#g-save").innerHTML = ic("save") + " Salvar alterações";
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
        $("#g-msg").textContent = "Informe nome e um valor-alvo maior que zero.";
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
        $("#g-msg").textContent = e.message;
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

  // =========================================================
  // SUB-VISÃO: GASTOS RECORRENTES (aba do Planejamento)
  // Pressupõe que o layout já foi montado e o META já carregado.
  // =========================================================
  async function setupRecorrentes() {
    let editId = null;
    const form = $("#rec-form");

    // ---- Preenche os selects do formulário ----
    UI.fillSelect($("#r-payment"), META.payment_methods);
    UI.fillSelect($("#r-spent-by"), META.people);
    UI.fillSelect($("#r-account"), META.accounts || []);
    UI.fillSelect($("#r-card"), META.cards || [], { keepFirst: true });
    aplicarCategorias();
    $("#r-type").addEventListener("change", aplicarCategorias);

    function aplicarCategorias() {
      const tipo = $("#r-type").value;
      const cats = tipo === "receita" ? META.income_categories : META.expense_categories;
      UI.fillSelect($("#r-category"), cats);
    }

    function resetForm() {
      form.reset();
      editId = null;
      $("#r-id").value = "";
      $("#r-day").value = "0";
      $("#r-active").value = "1";
      $("#rec-form-title").textContent = "Novo gasto recorrente";
      $("#r-save").innerHTML = ic("save") + " Adicionar";
      $("#r-cancel").hidden = true;
      $("#r-msg").textContent = "";
      aplicarCategorias();
    }

    /** Lê o formulário e monta o payload do template. */
    function lerForm() {
      return {
        description: $("#r-description").value.trim(),
        amount: parseFloat($("#r-amount").value) || 0,
        type: $("#r-type").value,
        category: $("#r-category").value,
        payment_method: $("#r-payment").value,
        spent_by: $("#r-spent-by").value || "Eu",
        account: $("#r-account").value || "Carteira",
        card: $("#r-card").value || "",
        day_of_month: parseInt($("#r-day").value, 10) || 0,
        active: parseInt($("#r-active").value, 10),
      };
    }

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const payload = lerForm();
      if (!payload.description || !(payload.amount > 0)) {
        $("#r-msg").textContent = "Informe descrição e um valor maior que zero.";
        $("#r-msg").className = "form-msg err";
        return;
      }
      $("#r-save").disabled = true;
      try {
        if (editId === null) {
          await Api.createRecurring(payload);
          UI.showMessage("ok", "Gasto recorrente criado.");
        } else {
          await Api.updateRecurring(editId, payload);
          UI.showMessage("ok", "Gasto recorrente atualizado.");
        }
        resetForm();
        await carregar();
      } catch (e) {
        $("#r-msg").textContent = e.message;
        $("#r-msg").className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#r-save").disabled = false;
      }
    });

    $("#r-cancel").addEventListener("click", resetForm);

    /** Preenche o formulário a partir de um template (edição). */
    function editar(t) {
      if (!t) return;
      editId = t.id;
      $("#r-id").value = t.id;
      $("#r-description").value = t.description;
      $("#r-amount").value = t.amount;
      $("#r-type").value = t.type;
      aplicarCategorias();
      if ([...$("#r-category").options].some((o) => o.value === t.category)) {
        $("#r-category").value = t.category;
      }
      if ([...$("#r-payment").options].some((o) => o.value === t.payment_method)) {
        $("#r-payment").value = t.payment_method;
      }
      if ([...$("#r-spent-by").options].some((o) => o.value === t.spent_by)) {
        $("#r-spent-by").value = t.spent_by;
      }
      if ([...$("#r-account").options].some((o) => o.value === t.account)) {
        $("#r-account").value = t.account;
      }
      $("#r-card").value = (t.card && [...$("#r-card").options].some((o) => o.value === t.card)) ? t.card : "";
      $("#r-day").value = t.day_of_month;
      $("#r-active").value = String(t.active);
      $("#rec-form-title").textContent = "Editar recorrente";
      $("#r-save").innerHTML = ic("save") + " Salvar alterações";
      $("#r-cancel").hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function excluir(id) {
      if (!confirm("Excluir este gasto recorrente?")) return;
      try {
        await Api.deleteRecurring(id);
        UI.showMessage("ok", "Removido.");
        if (editId === id) resetForm();
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    /** Cria um template a partir de um padrão detectado no histórico. */
    async function salvarDetectado(d) {
      try {
        await Api.createRecurring({
          description: d.description,
          amount: d.avg_amount,
          type: d.type,
          category: d.category,
          payment_method: d.payment_method,
          spent_by: d.spent_by,
          account: d.account,
          card: d.card,
          day_of_month: d.day_of_month,
          active: 1,
        });
        UI.showMessage("ok", `"${d.description}" salvo como recorrente.`);
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    // ---- Renderização ----

    function renderProximas(templates) {
      const box = $("#rec-next");
      box.innerHTML = "";
      const comData = templates
        .filter((t) => t.active && t.next_date)
        .sort((a, b) => (a.days_until ?? 999) - (b.days_until ?? 999));
      if (!comData.length) {
        box.innerHTML = `<p class="muted">Nenhuma cobrança projetada. Defina o "dia da cobrança" nos seus recorrentes.</p>`;
        return;
      }
      for (const t of comData) {
        const dias = t.days_until;
        const nivel = dias <= 3 ? "danger" : dias <= 7 ? "warning" : "ok";
        const card = document.createElement("article");
        card.className = "card credit-card";
        card.style.setProperty("--acc-color", nivel === "danger" ? "var(--danger)" : nivel === "warning" ? "var(--warning)" : "var(--primary)");
        card.innerHTML = `
          <div class="cc-top">
            <span class="cc-name">${ic("recurring", { size: 16 })}${Utils.escapeHtml(t.description)}</span>
            <span class="badge">${Utils.escapeHtml(t.category)}</span>
          </div>
          <div class="cc-invoice">
            <span class="cc-label">Próxima</span>
            <span class="cc-value">${formatarMoeda(t.amount)}</span>
          </div>
          <div class="cc-foot">
            <span>${formatarData(t.next_date)}</span>
            <span class="${dias <= 5 ? "cc-due-soon" : "muted"}">${dias <= 0 ? "hoje" : "em " + dias + "d"}</span>
          </div>`;
        box.appendChild(card);
      }
    }

    function renderDetectados(detectados) {
      const box = $("#rec-detected");
      box.innerHTML = "";
      if (!detectados.length) {
        box.innerHTML = `<p class="muted">Nada recorrente detectado nesta janela. Registre mais lançamentos para o sistema aprender seus padrões.</p>`;
        return;
      }
      for (const d of detectados) {
        const row = document.createElement("div");
        row.className = "goal-row";
        const btn = d.already_template
          ? `<span class="badge badge-ok">${ic("check", { size: 12 })}já salvo</span>`
          : `<button class="btn btn-ghost btn-sm" data-save>${ic("plus", { size: 15 })} Salvar</button>`;
        row.innerHTML = `
          <span>
            <span class="g-name">${ic("recurring", { size: 16 })}${Utils.escapeHtml(d.description)}</span>
            <span class="g-meta"> • ${formatarMoeda(d.avg_amount)} • ${Utils.escapeHtml(d.category)} • ${d.occurrences}x em ${d.months_present} meses${d.day_of_month ? " • ~dia " + d.day_of_month : ""} • próx. ${formatarData(d.next_expected)}</span>
          </span>
          <span class="g-actions">${btn}</span>`;
        box.appendChild(row);
        const saveBtn = row.querySelector("[data-save]");
        if (saveBtn) saveBtn.addEventListener("click", () => salvarDetectado(d));
      }
    }

    function renderLista(templates) {
      const lista = $("#rec-list");
      lista.innerHTML = "";
      if (!templates.length) {
        lista.innerHTML = `<p class="muted">Nenhum gasto recorrente salvo ainda.</p>`;
        return;
      }
      for (const t of templates) {
        const row = document.createElement("div");
        row.className = "card-row";
        const pausado = t.active ? "" : `<span class="badge"> pausado</span>`;
        row.innerHTML = `
          <span>
            <span class="c-name">${ic("recurring", { size: 16 })}${Utils.escapeHtml(t.description)} ${pausado}</span>
            <span class="c-meta"> • ${formatarMoeda(t.amount)} • ${Utils.escapeHtml(t.category)} • ${Utils.escapeHtml(t.payment_method)}${t.day_of_month ? " • dia " + t.day_of_month : ""}</span>
          </span>
          <span class="c-actions">
            <button class="icon-btn" data-edit="${t.id}" title="Editar" aria-label="Editar">${ic("edit")}</button>
            <button class="icon-btn danger" data-del="${t.id}" title="Excluir" aria-label="Excluir">${ic("trash")}</button>
          </span>`;
        lista.appendChild(row);
      }
      lista.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => editar(templates.find((x) => x.id === Number(b.dataset.edit)))));
      lista.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => excluir(Number(b.dataset.del))));
    }

    async function carregarDetectados() {
      const janela = Number($("#rec-window").value) || 6;
      const detectados = await Api.getDetectedRecurring(janela);
      renderDetectados(detectados);
    }
    $("#rec-window").addEventListener("change", carregarDetectados);

    async function carregar() {
      let templates;
      try { templates = await Api.getRecurring(); }
      catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();
      renderProximas(templates);
      renderLista(templates);
      await carregarDetectados();
    }

    await carregar();
  }

  // =========================================================
  // SUB-VISÃO: AGENDA DE VENCIMENTOS (aba do Planejamento)
  // Pressupõe que o layout já foi montado. Retorna { loadCashFlow }
  // para o gráfico ser re-renderizado quando a aba ficar visível
  // (Chart.js precisa do canvas com tamanho > 0).
  // =========================================================
  async function setupAgenda() {
    let editId = null;
    const form = $("#venc-form");

    // Níveis de urgência → cor/rótulo (espelha o `level` do backend).
    const LEVEL = {
      atrasado: { cor: "danger",  txt: "atrasado" },
      urgente:  { cor: "danger",  txt: "urgente" },
      proximo:  { cor: "warning", txt: "próximo" },
      ok:       { cor: "primary", txt: "em dia" },
      pago:     { cor: "primary", txt: "pago" },
    };

    // ---- Seletor de período do fluxo de caixa ----
    const cfMonth = $("#cf-month");
    if (cfMonth && !cfMonth.options.length) {
      MONTHS.forEach((nome, i) => {
        const opt = document.createElement("option");
        opt.value = i + 1; opt.textContent = nome; cfMonth.appendChild(opt);
      });
    }
    const now = new Date();
    $("#cf-year").value = now.getFullYear();
    cfMonth.value = now.getMonth() + 1;
    $("#cf-year").addEventListener("change", loadCashFlow);
    cfMonth.addEventListener("change", loadCashFlow);
    $("#venc-window").addEventListener("change", loadProximos);

    // ---- Formulário ----
    function resetForm() {
      form.reset();
      editId = null;
      $("#v-id").value = "";
      $("#v-due").value = hojeISO();
      $("#v-notify").value = "3";
      $("#v-status").value = "pendente";
      $("#venc-form-title").textContent = "Novo vencimento";
      $("#v-save").innerHTML = ic("save") + " Adicionar";
      $("#v-cancel").hidden = true;
      $("#v-msg").textContent = "";
    }

    function lerForm() {
      return {
        name: $("#v-name").value.trim(),
        due_date: $("#v-due").value,
        amount: parseFloat($("#v-amount").value) || 0,
        kind: $("#v-kind").value,
        recurrence: $("#v-recurrence").value,
        notify_days: parseInt($("#v-notify").value, 10) || 0,
        category: $("#v-category").value.trim(),
        notes: $("#v-notes").value.trim(),
        status: $("#v-status").value,
      };
    }

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const payload = lerForm();
      if (!payload.name || !payload.due_date) {
        $("#v-msg").textContent = "Informe nome e data de vencimento.";
        $("#v-msg").className = "form-msg err";
        return;
      }
      $("#v-save").disabled = true;
      try {
        if (editId === null) {
          await Api.createVencimento(payload);
          UI.showMessage("ok", "Vencimento criado.");
        } else {
          await Api.updateVencimento(editId, payload);
          UI.showMessage("ok", "Vencimento atualizado.");
        }
        resetForm();
        await carregar();
      } catch (e) {
        $("#v-msg").textContent = e.message;
        $("#v-msg").className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#v-save").disabled = false;
      }
    });

    $("#v-cancel").addEventListener("click", resetForm);

    function editar(v) {
      if (!v) return;
      editId = v.id;
      $("#v-id").value = v.id;
      $("#v-name").value = v.name;
      $("#v-amount").value = v.amount;
      $("#v-due").value = v.due_date.slice(0, 10);
      $("#v-kind").value = v.kind;
      $("#v-recurrence").value = v.recurrence;
      $("#v-notify").value = v.notify_days;
      $("#v-category").value = v.category || "";
      $("#v-notes").value = v.notes || "";
      $("#v-status").value = v.status === "pago" ? "pago" : "pendente";
      $("#venc-form-title").textContent = "Editar vencimento";
      $("#v-save").innerHTML = ic("save") + " Salvar alterações";
      $("#v-cancel").hidden = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function excluir(id) {
      if (!confirm("Excluir este vencimento?")) return;
      try {
        await Api.deleteVencimento(id);
        UI.showMessage("ok", "Removido.");
        if (editId === id) resetForm();
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    async function pagar(id) {
      try {
        await Api.payVencimento(id);
        UI.showMessage("ok", "Marcado como pago.");
        await carregar();
      } catch (e) { UI.showMessage("err", e.message); }
    }

    // ---- Renderização ----

    function renderProximos(itens) {
      const box = $("#venc-next");
      box.innerHTML = "";
      const pend = itens.filter((v) => v.status !== "pago");
      if (!pend.length) {
        box.innerHTML = `<p class="muted">Nenhum vencimento pendente nesta janela. Tudo em dia.</p>`;
        return;
      }
      for (const v of pend) {
        const lv = LEVEL[v.level] || LEVEL.ok;
        const card = document.createElement("article");
        card.className = "card credit-card";
        card.style.setProperty("--acc-color", `var(--${lv.cor})`);
        const quando = v.days_until < 0
          ? `atrasado há ${Math.abs(v.days_until)}d`
          : v.days_until === 0 ? "vence hoje" : `em ${v.days_until}d`;
        card.innerHTML = `
          <div class="cc-top">
            <span class="cc-name">${ic("pin", { size: 16 })}${Utils.escapeHtml(v.name)}</span>
            <span class="badge ${v.level === "atrasado" || v.level === "urgente" ? "badge-danger" : ""}">${lv.txt}</span>
          </div>
          <div class="cc-invoice">
            <span class="cc-label">${Utils.escapeHtml(v.kind)}${v.recurrence === "mensal" ? " • mensal" : ""}</span>
            <span class="cc-value">${formatarMoeda(v.amount)}</span>
          </div>
          <div class="cc-foot">
            <span>${formatarData(v.due_date)}</span>
            <span class="${v.days_until <= 3 ? "cc-due-soon" : "muted"}">${quando}</span>
          </div>
          <div class="flex gap" style="margin-top:8px">
            <button class="btn btn-primary btn-sm" data-pay="${v.id}">${ic("check", { size: 15 })} Pago</button>
          </div>`;
        box.appendChild(card);
      }
      box.querySelectorAll("[data-pay]").forEach((b) =>
        b.addEventListener("click", () => pagar(Number(b.dataset.pay))));
    }

    function renderCashFlow(cf) {
      // KPIs de resumo.
      const negTxt = cf.goes_negative_on
        ? `<span class="kpi-value expense">${formatarData(cf.goes_negative_on)}</span>`
        : `<span class="kpi-value income">não fica negativo</span>`;
      $("#cf-summary").innerHTML = `
        <article class="card kpi">
          <div class="kpi-top"><span class="kpi-label">Saldo inicial</span><span class="kpi-icon">${ic("bank", { size: 18 })}</span></div>
          <span class="kpi-value">${formatarMoeda(cf.starting_balance)}</span>
        </article>
        <article class="card kpi">
          <div class="kpi-top"><span class="kpi-label">Saldo projetado (fim)</span><span class="kpi-icon ${cf.ending_balance < 0 ? "expense" : "income"}">${ic("chart", { size: 18 })}</span></div>
          <span class="kpi-value ${cf.ending_balance < 0 ? "expense" : "income"}">${formatarMoeda(cf.ending_balance)}</span>
        </article>
        <article class="card kpi">
          <div class="kpi-top"><span class="kpi-label">Fica negativo em</span><span class="kpi-icon expense">${ic("alert-triangle", { size: 18 })}</span></div>
          ${negTxt}
        </article>`;

      // Gráfico de linha do saldo projetado.
      const labels = cf.days.map((d) => d.date.slice(8, 10));
      UI.renderLine("cf-chart", labels, [
        { label: "Saldo projetado", data: cf.days.map((d) => d.running_balance), color: "#3B82F6" },
      ]);

      // Tabela: só os dias que têm vencimentos.
      const tbody = $("#cf-tbody");
      tbody.innerHTML = "";
      const comItens = cf.days.filter((d) => d.items.length);
      $("#cf-empty").hidden = comItens.length > 0;
      for (const d of comItens) {
        const nomes = d.items.map((i) => Utils.escapeHtml(i.name)).join(", ");
        const neg = d.running_balance < 0;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${formatarData(d.date)}</td>
          <td>${nomes}</td>
          <td class="num amount despesa">${formatarMoeda(Math.abs(d.delta))}</td>
          <td class="num ${neg ? "amount despesa" : ""}">${formatarMoeda(d.running_balance)}</td>`;
        tbody.appendChild(tr);
      }
    }

    function renderLista(itens) {
      const lista = $("#venc-list");
      lista.innerHTML = "";
      if (!itens.length) {
        lista.innerHTML = `<p class="muted">Nenhum vencimento cadastrado.</p>`;
        return;
      }
      for (const v of itens) {
        const lv = LEVEL[v.level] || LEVEL.ok;
        const row = document.createElement("div");
        row.className = "card-row";
        row.style.setProperty("--acc-color", `var(--${lv.cor})`);
        const pagoTag = v.status === "pago" ? `<span class="badge badge-ok">${ic("check", { size: 12 })}pago</span>` : "";
        row.innerHTML = `
          <span>
            <span class="c-name">${ic("pin", { size: 16 })}${Utils.escapeHtml(v.name)} ${pagoTag}</span>
            <span class="c-meta"> • ${formatarMoeda(v.amount)} • vence ${formatarData(v.due_date)} • ${Utils.escapeHtml(v.kind)}${v.recurrence === "mensal" ? " • mensal" : ""}</span>
          </span>
          <span class="c-actions">
            ${v.status !== "pago" ? `<button class="icon-btn" data-pay="${v.id}" title="Marcar pago" aria-label="Marcar pago">${ic("check")}</button>` : ""}
            <button class="icon-btn" data-edit="${v.id}" title="Editar" aria-label="Editar">${ic("edit")}</button>
            <button class="icon-btn danger" data-del="${v.id}" title="Excluir" aria-label="Excluir">${ic("trash")}</button>
          </span>`;
        lista.appendChild(row);
      }
      lista.querySelectorAll("[data-pay]").forEach((b) =>
        b.addEventListener("click", () => pagar(Number(b.dataset.pay))));
      lista.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => editar(itens.find((x) => x.id === Number(b.dataset.edit)))));
      lista.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => excluir(Number(b.dataset.del))));
    }

    // ---- Carregamento ----
    let todos = [];

    async function loadProximos() {
      const janela = Number($("#venc-window").value) || 30;
      try {
        const prox = await Api.getVencimentos(janela);
        renderProximos(prox);
      } catch (e) { console.warn("Falha ao carregar próximos:", e.message); }
    }

    async function loadCashFlow() {
      const y = Number($("#cf-year").value) || now.getFullYear();
      const m = Number(cfMonth.value) || now.getMonth() + 1;
      try {
        const cf = await Api.getCashFlow(y, m);
        renderCashFlow(cf);
      } catch (e) { console.warn("Falha no fluxo de caixa:", e.message); }
    }

    async function carregar() {
      try { todos = await Api.getVencimentos(); }
      catch (e) { UI.showStatus(e.message); return; }
      UI.clearStatus();
      renderLista(todos);
      await loadProximos();
      await loadCashFlow();
    }

    await carregar();
    return { loadCashFlow };
  }

  // =========================================================
  // PÁGINA: PLANEJAMENTO (Recorrentes + Agenda em abas)
  // =========================================================
  async function initPlanejamento() {
    UI.mountLayout({ page: "planejamento", title: "Planejamento" });
    try { await ensureMeta(); } catch { return; }

    await setupRecorrentes();
    const agenda = await setupAgenda();

    // Ao abrir a aba Agenda, re-renderiza o gráfico de fluxo (que foi
    // desenhado escondido na carga inicial e precisa do canvas visível).
    UI.wireTabs($("#plan-tabs"), {
      onChange: (key) => { if (key === "agenda" && agenda) agenda.loadCashFlow(); },
    });
  }

  // =========================================================
  // SUB-VISÃO: IMPORTAR EXTRATO (aba de Lançamentos)
  // Pressupõe layout montado e META carregado. `onImported` (opcional)
  // roda após gravar, para a lista de lançamentos se atualizar.
  // =========================================================
  async function setupImportar({ onImported } = {}) {
    let formato = "csv";     // "csv" | "ofx"
    let conteudo = "";       // texto bruto do arquivo
    let headers = [];        // cabeçalhos do CSV
    let itens = [];          // itens da pré-visualização

    const todasCategorias = [...new Set([...META.expense_categories, ...META.income_categories])];

    // ---- Dropzone + leitura do arquivo ----
    const dz = $("#dropzone");
    const fileInput = $("#file-input");

    dz.addEventListener("click", () => fileInput.click());
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
    dz.addEventListener("drop", (e) => {
      e.preventDefault();
      dz.classList.remove("dragover");
      if (e.dataTransfer.files.length) lerArquivo(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) lerArquivo(fileInput.files[0]);
    });

    function lerArquivo(file) {
      $("#dz-file").textContent = file.name;
      const nome = file.name.toLowerCase();
      formato = (nome.endsWith(".ofx") || nome.endsWith(".qfx")) ? "ofx" : "csv";
      const reader = new FileReader();
      reader.onload = () => { conteudo = reader.result; iniciarPreview(); };
      reader.onerror = () => UI.showMessage("err", "Não consegui ler o arquivo.");
      reader.readAsText(file, "utf-8");
    }

    // ---- Passo 1: decidir entre mapear (CSV) ou já pré-visualizar (OFX) ----
    async function iniciarPreview() {
      $("#preview-section").hidden = true;
      if (formato === "ofx") {
        $("#map-section").hidden = true;
        await rodarPreview(null);
        return;
      }
      // CSV: busca cabeçalhos para o usuário mapear.
      let prev;
      try { prev = await Api.previewImport({ format: "csv", content: conteudo }); }
      catch (e) { UI.showMessage("err", e.message); return; }
      headers = prev.headers || [];
      if (!headers.length) { UI.showMessage("err", "CSV vazio ou ilegível."); return; }
      montarMapeamento(headers, prev.sample || []);
      $("#map-section").hidden = false;
      $("#map-section").scrollIntoView({ behavior: "smooth" });
    }

    function montarMapeamento(headers, sample) {
      const opcoes = headers.map((h, i) => `<option value="${i}">${Utils.escapeHtml(h || ("Coluna " + (i + 1)))}</option>`).join("");
      ["map-date", "map-amount", "map-description"].forEach((id) => { $("#" + id).innerHTML = opcoes; });
      // Palpites por nome de coluna.
      headers.forEach((h, i) => {
        const n = (h || "").toLowerCase();
        if (/(data|date|dia)/.test(n)) $("#map-date").value = i;
        if (/(valor|amount|montante|vlr)/.test(n)) $("#map-amount").value = i;
        if (/(desc|hist|memo|lan|detalhe)/.test(n)) $("#map-description").value = i;
      });
      UI.fillSelect($("#map-account"), META.accounts || []);
      UI.fillSelect($("#map-payment"), META.payment_methods);
    }

    $("#map-apply").addEventListener("click", () => {
      const mapping = {
        date: Number($("#map-date").value),
        amount: Number($("#map-amount").value),
        description: Number($("#map-description").value),
        default_type: $("#map-type").value,
        default_account: $("#map-account").value,
        default_payment: $("#map-payment").value,
      };
      rodarPreview(mapping);
    });

    // ---- Passo 2: pré-visualização ----
    async function rodarPreview(mapping) {
      let prev;
      try {
        prev = await Api.previewImport({ format: formato, content: conteudo, mapping });
      } catch (e) { UI.showMessage("err", e.message); return; }
      itens = prev.items || [];
      renderPreview();
      $("#preview-section").hidden = false;
      $("#preview-section").scrollIntoView({ behavior: "smooth" });
    }

    function renderPreview() {
      const tbody = $("#prev-tbody");
      tbody.innerHTML = "";
      $("#prev-empty").hidden = itens.length > 0;
      $("#preview-count").textContent = itens.length
        ? `${itens.length} transação(ões) • ${itens.filter((i) => i.duplicate).length} possível(is) duplicata(s)`
        : "";

      itens.forEach((it, idx) => {
        const tr = document.createElement("tr");
        if (it.duplicate) tr.className = "is-dup";
        const cats = todasCategorias.map((c) =>
          `<option value="${Utils.escapeHtml(c)}"${c === it.category_suggested ? " selected" : ""}>${Utils.escapeHtml(c)}</option>`).join("");
        tr.innerHTML = `
          <td><input type="checkbox" data-check="${idx}" ${it.include ? "checked" : ""} /></td>
          <td>${it.date ? formatarData(it.date) : '<span class="cc-due-soon">sem data</span>'}</td>
          <td><span class="tag ${it.type}">${it.type}</span></td>
          <td class="num amount ${it.type}">${formatarMoeda(it.amount)}</td>
          <td>${Utils.escapeHtml(it.description)}</td>
          <td><select data-cat="${idx}">${cats}</select></td>
          <td>${it.duplicate ? `<span class="cc-due-soon" title="Possível duplicata">${ic("alert-triangle", { size: 16 })}</span>` : "—"}</td>`;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll("[data-check]").forEach((c) =>
        c.addEventListener("change", () => { itens[Number(c.dataset.check)].include = c.checked; }));
      tbody.querySelectorAll("[data-cat]").forEach((s) =>
        s.addEventListener("change", () => { itens[Number(s.dataset.cat)].category = s.value; }));
      $("#check-all").checked = itens.every((i) => i.include);
    }

    function marcar(fn) {
      itens.forEach((it) => { it.include = fn(it); });
      renderPreview();
    }
    $("#sel-all").addEventListener("click", () => marcar(() => true));
    $("#sel-none").addEventListener("click", () => marcar(() => false));
    $("#sel-nondup").addEventListener("click", () => marcar((it) => !it.duplicate && !!it.date));
    $("#check-all").addEventListener("change", (e) => marcar(() => e.target.checked));

    // ---- Passo 3: importar ----
    $("#btn-import").addEventListener("click", async () => {
      const selecionados = itens.filter((i) => i.include);
      if (!selecionados.length) {
        UI.showMessage("err", "Nenhuma transação selecionada.");
        return;
      }
      // Garante que a categoria escolhida (ou a sugerida) vai no payload.
      const payload = selecionados.map((i) => ({
        date: i.date,
        description: i.description,
        amount: i.amount,
        type: i.type,
        category: i.category || i.category_suggested || "Outros",
        payment_method: i.payment_method,
        spent_by: i.spent_by,
        account: i.account,
        card: i.card,
        include: true,
      }));
      $("#btn-import").disabled = true;
      $("#import-msg").textContent = "Importando…";
      $("#import-msg").className = "form-msg";
      try {
        const res = await Api.confirmImport(payload);
        UI.showMessage("ok", `${res.imported} importada(s), ${res.skipped} pulada(s).`);
        $("#import-msg").textContent = `${res.imported} importada(s), ${res.skipped} pulada(s).`;
        $("#import-msg").className = "form-msg ok";
        if (res.errors && res.errors.length) {
          console.warn("Erros de importação:", res.errors);
        }
        // Remove da tela os que foram gravados.
        itens = itens.filter((i) => !i.include);
        renderPreview();
        // Atualiza a lista de lançamentos (estamos dentro da página de Lançamentos).
        if (onImported && res.imported) onImported();
      } catch (e) {
        $("#import-msg").textContent = e.message;
        $("#import-msg").className = "form-msg err";
        UI.showMessage("err", e.message);
      } finally {
        $("#btn-import").disabled = false;
      }
    });
  }

  // =========================================================
  // PÁGINA: IA FINANCEIRA (score de saúde + análise/conselhos da IA)
  // Une o antigo Gestor IA com os Conselhos: o score e a previsão são
  // determinísticos; os insights/conselhos vêm da Groq (fallback: regras).
  // =========================================================
  async function initIA() {
    UI.mountLayout({
      page: "ia",
      title: "IA Financeira",
      topbarExtra: periodHTML(),
    });

    const getPeriod = setupPeriod(load);
    $("#btn-refresh").addEventListener("click", load);

    // Cor por faixa do score.
    const FAIXA = {
      saudavel: { cor: "#10B981", txt: "Saudável" },
      atencao:  { cor: "#F59E0B", txt: "Atenção" },
      critica:  { cor: "#EF4444", txt: "Crítica" },
    };
    // Severidade do insight → cor/ícone (igual à página de conselhos).
    const SEV = {
      success: { cor: "primary", ico: "success" },
      info:    { cor: "info",    ico: "lightbulb" },
      warning: { cor: "warning", ico: "alert-triangle" },
      danger:  { cor: "danger",  ico: "danger" },
    };

    function nivelBarra(score) {
      return score >= 70 ? "ok" : score >= 40 ? "warning" : "danger";
    }

    function cardInsight(ins) {
      const sev = SEV[ins.severity] || SEV.info;
      const selo = ins.source === "llm"
        ? `<span class="badge badge-llm">${ic("ai", { size: 12 })}IA</span>`
        : `<span class="badge">${ic("info", { size: 12 })}Regra</span>`;
      return `
        <div class="card insight-card" style="border-left:4px solid var(--${sev.cor})">
          <div class="insight-head">
            <h3><span style="color:var(--${sev.cor})">${ic(sev.ico, { size: 17 })}</span> ${Utils.escapeHtml(ins.title)}</h3>
            ${selo}
          </div>
          <p>${Utils.escapeHtml(ins.message)}</p>
        </div>`;
    }

    function render(data) {
      const out = $("#gestor-output");
      const fx = FAIXA[data.faixa] || FAIXA.atencao;

      // Barras das sub-métricas.
      const metricas = Object.values(data.breakdown)
        .sort((a, b) => b.weight - a.weight)
        .map((m) => `
          <div class="metric-row">
            <div class="metric-head">
              <span>${Utils.escapeHtml(m.label)} <span class="muted">(peso ${m.weight}%)</span></span>
              <span><strong>${m.score}</strong>/100</span>
            </div>
            <div class="metric-bar"><span class="metric-bar-fill ${nivelBarra(m.score)}" data-target="${m.score}"></span></div>
          </div>`).join("");

      const f = data.forecast;
      const previsaoTipo = f.is_projection ? "Projeção para o fim do mês" : "Saldo real (mês fechado)";
      const saldoCls = f.projected_balance < 0 ? "expense" : "income";

      const fonte = data.llm_used ? "IA Groq + score determinístico" : "Score determinístico (IA não configurada)";

      out.innerHTML = `
        <section class="card">
          <div class="score-hero">
            <div class="score-gauge" style="--val:0;--col:${fx.cor}" data-target="${data.score}">
              <div class="score-gauge-inner">
                <div>
                  <div class="score-number" style="--col:${fx.cor}" data-target="${data.score}">0</div>
                  <div class="score-of">de 100</div>
                </div>
              </div>
            </div>
            <div class="score-hero-text">
              <span class="score-faixa" style="--col:${fx.cor}">${fx.txt}</span>
              <h2 style="margin:10px 0 4px">Saúde financeira de ${nomeMes(data.month)}/${data.year}</h2>
              <p class="muted">${fonte}</p>
              ${metricas}
            </div>
          </div>
        </section>

        <section class="card">
          <h2>Previsão de saldo</h2>
          <p class="muted" style="margin:0 0 10px">${previsaoTipo}</p>
          <span class="kpi-value ${saldoCls}" style="font-size:2.2em">${formatarMoeda(f.projected_balance)}</span>
          <div class="account-flow" style="margin-top:12px">
            <span class="up">${ic("arrow-up", { size: 13 })} receita prevista ${formatarMoeda(f.projected_income)}</span>
            <span class="down">${ic("arrow-down", { size: 13 })} despesa prevista ${formatarMoeda(f.projected_expense)}</span>
          </div>
        </section>

        <section class="card">
          <h2>Insights</h2>
          <div class="insights-list">${data.insights.map(cardInsight).join("")}</div>
        </section>`;
    }

    /** Anima o medidor (preenche), o número (conta) e as barras (crescem). */
    function animar(out) {
      requestAnimationFrame(() => {
        const g = out.querySelector(".score-gauge");
        if (g) g.style.setProperty("--val", g.dataset.target);
        out.querySelectorAll(".metric-bar-fill").forEach((b) => {
          b.style.width = (b.dataset.target || 0) + "%";
        });
        const num = out.querySelector(".score-number");
        if (num) contarAte(num, Number(num.dataset.target) || 0);
      });
    }

    /** Conta de 0 até `alvo` com easing suave (acompanha o medidor). */
    function contarAte(el, alvo, dur = 1100) {
      const inicio = performance.now();
      function passo(agora) {
        const p = Math.min((agora - inicio) / dur, 1);
        const eased = 0.5 - Math.cos(Math.PI * p) / 2; // easeInOutSine
        el.textContent = Math.round(alvo * eased);
        if (p < 1) requestAnimationFrame(passo);
      }
      requestAnimationFrame(passo);
    }

    async function load() {
      const { year, month } = getPeriod();
      const out = $("#gestor-output");
      out.innerHTML = `<div class="loading-box"><span class="spinner"></span> Calculando sua saúde financeira… (a IA pode levar alguns segundos)</div>`;
      try {
        const data = await Api.getHealthScore(year, month);
        UI.clearStatus();
        render(data);
        animar(out);
      } catch (e) {
        out.innerHTML = `<p class="form-msg err">${ic("alert-triangle", { size: 15 })} ${Utils.escapeHtml(e.message)}</p>`;
      }
    }

    await load();
  }

  // ---------- HTML do seletor de período (reaproveitado) ----------
  function periodHTML() {
    return `
      <div class="period">
        <label>Ano <input type="number" id="year" min="2000" max="2100" /></label>
        <label>Mês <select id="month"></select></label>
        <button id="reload" class="btn btn-ghost btn-sm">${ic("refresh", { size: 15 })} Atualizar</button>
      </div>`;
  }

  // =========================================================
  // BOOTSTRAP — escolhe o init conforme data-page do <body>
  // =========================================================
  const PAGES = {
    dashboard: initDashboard,
    lancamentos: initLancamentos,
    planejamento: initPlanejamento,
    cartoes: initCartoes,
    metas: initMetas,
    alertas: initAlertas,
    relatorios: initRelatorios,
    ia: initIA,
    configuracoes: initConfiguracoes,
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
