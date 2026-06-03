/* =========================================================
   Finance App — INTERFACE (ui.js)
   ---------------------------------------------------------
   Tudo que MEXE NO DOM e desenha dados mora aqui:
   - monta o layout (sidebar + topbar) injetado em todas as páginas;
   - toasts e faixas de status;
   - preenche <select>;
   - renderiza KPIs, tabela de transações e gráficos (Chart.js);
   - gera o conselho local (fallback) baseado em regras.

   As páginas (via app.js) chamam estas funções passando dados já
   prontos. UI não chama a API — quem orquestra é o app.js.
   ========================================================= */

const UI = (() => {
  const { $, escapeHtml, formatarMoeda, formatarData, corSaldo } = Utils;

  // Definição dos itens de navegação. `href` é relativo À RAIZ do
  // frontend; ajustamos o prefixo conforme a página esteja em /pages.
  const NAV = [
    { id: "dashboard",      label: "Dashboard",     ico: "📊", href: "index.html" },
    { id: "lancamentos",    label: "Lançamentos",   ico: "💸", href: "pages/lancamentos.html" },
    { id: "cartoes",        label: "Cartões",       ico: "💳", href: "pages/cartoes.html" },
    { id: "metas",          label: "Metas",         ico: "🎯", href: "pages/metas.html" },
    { id: "alertas",        label: "Alertas",       ico: "🔔", href: "pages/alertas.html" },
    { id: "relatorios",     label: "Relatórios",    ico: "📈", href: "pages/relatorios.html" },
    { id: "configuracoes",  label: "Configurações", ico: "⚙️", href: "pages/configuracoes.html" },
    { id: "conselhos",      label: "Conselhos IA",  ico: "🤖", href: "pages/conselhos.html" },
  ];

  /**
   * Monta sidebar + topbar e injeta nos placeholders #sidebar / #topbar.
   * `page`  = id do item ativo (data-page do <body>).
   * `title` = título exibido na topbar.
   * `topbarExtra` = HTML opcional à direita da topbar (ex: seletor de período).
   * Retorna nada; depois de montar, liga o hamburguer do mobile.
   */
  function mountLayout({ page, title, topbarExtra = "" }) {
    // Estamos dentro de /pages/ ? Então subimos um nível nos links.
    const inPages = location.pathname.replace(/\\/g, "/").includes("/pages/");
    const prefix = inPages ? "../" : "";

    const links = NAV.map((n) => `
      <a class="nav-link ${n.id === page ? "active" : ""}" href="${prefix}${n.href}">
        <span class="ico">${n.ico}</span><span>${n.label}</span>
        ${n.id === "alertas" ? `<span class="nav-badge" id="nav-alert-badge" hidden></span>` : ""}
      </a>`).join("");

    const sidebar = $("#sidebar");
    if (sidebar) {
      sidebar.className = "sidebar";
      sidebar.innerHTML = `
        <div class="brand">💰 <span>Finance</span></div>
        <nav>${links}</nav>
        <div class="foot">v1.0 • API local</div>`;
    }

    const topbar = $("#topbar");
    if (topbar) {
      topbar.className = "topbar";
      // Botão de tema (sol/lua) fica à direita de tudo. theme.js já existe
      // (carregado no <head>); o typeof protege caso falte em alguma página.
      const themeBtn = typeof Theme !== "undefined" ? Theme.buttonHTML() : "";
      topbar.innerHTML = `
        <button class="hamburger" id="hamburger" aria-label="Menu">☰</button>
        <span class="page-title">${escapeHtml(title)}</span>
        <span class="spacer"></span>
        ${topbarExtra}
        ${themeBtn}`;
      // Liga o clique do botão de tema depois que ele já está no DOM.
      if (typeof Theme !== "undefined") Theme.wireButton();
    }

    // Menu deslizante no mobile.
    const backdrop = $("#backdrop");
    const ham = $("#hamburger");
    const closeMenu = () => {
      $("#sidebar")?.classList.remove("open");
      backdrop?.classList.remove("show");
    };
    ham?.addEventListener("click", () => {
      $("#sidebar")?.classList.toggle("open");
      backdrop?.classList.toggle("show");
    });
    backdrop?.addEventListener("click", closeMenu);

    // Atualiza o contador de alertas não lidos na sidebar (sem travar a UI).
    refreshAlertBadge();
  }

  // ---------- Alertas: leitura (localStorage) + badge ----------

  const ALERTS_READ_KEY = "finance-alerts-read";

  /** Conjunto de keys de alertas já marcados como lidos. */
  function readAlertKeys() {
    try { return new Set(JSON.parse(localStorage.getItem(ALERTS_READ_KEY) || "[]")); }
    catch (_) { return new Set(); }
  }
  function saveAlertKeys(set) {
    try { localStorage.setItem(ALERTS_READ_KEY, JSON.stringify([...set])); } catch (_) {}
  }
  function alertIsRead(key) { return readAlertKeys().has(key); }
  function markAlertRead(key) { const s = readAlertKeys(); s.add(key); saveAlertKeys(s); }
  function clearReadAlerts() { saveAlertKeys(new Set()); }
  function unreadAlerts(list) { const s = readAlertKeys(); return (list || []).filter((a) => !s.has(a.key)); }

  /** Busca os alertas do mês atual e mostra a contagem de não lidos. */
  async function refreshAlertBadge() {
    const badge = $("#nav-alert-badge");
    if (!badge || typeof Api === "undefined") return;
    try {
      const now = new Date();
      const alerts = await Api.getAlerts(now.getFullYear(), now.getMonth() + 1);
      const n = unreadAlerts(alerts).length;
      badge.textContent = String(n);
      badge.hidden = n === 0;
    } catch (_) {
      badge.hidden = true; // API fora do ar: não mostra badge.
    }
  }

  // ---------- Mensagens ----------

  /**
   * Toast flutuante. type: "ok" | "err" | "info". Some sozinho.
   */
  function showMessage(type, text, ms = 3500) {
    let box = $("#toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "toast";
      document.body.appendChild(box);
    }
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = text;
    box.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 250);
    }, ms);
  }

  /** Faixa de status fixa (ex: API offline). Use o placeholder #status. */
  function showStatus(text, kind = "err") {
    const box = $("#status");
    if (!box) { showMessage(kind, text); return; }
    box.textContent = text;
    box.className = `status ${kind}`;
    box.hidden = false;
  }
  function clearStatus() { const b = $("#status"); if (b) b.hidden = true; }

  // ---------- Selects ----------

  /** Preenche um <select> com strings. keepFirst mantém o 1º <option>. */
  function fillSelect(select, items, { keepFirst = false } = {}) {
    if (!select) return;
    const first = keepFirst ? select.firstElementChild : null;
    select.innerHTML = "";
    if (first) select.appendChild(first);
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = item;
      opt.textContent = item;
      select.appendChild(opt);
    }
  }

  // ---------- KPIs ----------

  /**
   * Atualiza os 4 KPIs do dashboard a partir do resumo mensal.
   * O card de saldo recebe a faixa lateral colorida (corSaldo()).
   */
  function renderKPIs(summary) {
    $("#kpi-incomes").textContent = formatarMoeda(summary.total_incomes);
    $("#kpi-expenses").textContent = formatarMoeda(summary.total_expenses);
    $("#kpi-count").textContent = summary.count;

    const bal = $("#kpi-balance");
    bal.textContent = formatarMoeda(summary.balance);

    // Faixa lateral: aplica is-pos / is-neg / is-zero no card pai.
    const card = $("#card-balance");
    if (card) {
      card.classList.remove("is-pos", "is-neg", "is-zero");
      card.classList.add(corSaldo(summary.balance));
    }
  }

  // ---------- Cards de saldos (contas) ----------

  /**
   * Desenha um card por conta dentro de `container`. Cada conta vem do
   * endpoint /accounts já com `current_balance`. O ícone e a cor (faixa
   * superior) são os definidos pelo usuário. Saldo negativo fica vermelho.
   * `data` = lista de contas; `container` = elemento alvo.
   */
  function renderAccountCards(accounts, container) {
    if (!container) return;
    container.innerHTML = "";
    if (!accounts || !accounts.length) {
      container.innerHTML = `<p class="muted">Nenhuma conta cadastrada. Crie em Configurações.</p>`;
      return;
    }
    for (const a of accounts) {
      const neg = Number(a.current_balance) < 0;
      const card = document.createElement("article");
      card.className = "card account-card";
      card.style.setProperty("--acc-color", a.color || "var(--info)");
      card.innerHTML = `
        <div class="account-top">
          <span class="account-icon">${escapeHtml(a.icon || "💰")}</span>
          <span class="account-name">${escapeHtml(a.name)}</span>
        </div>
        <span class="account-balance ${neg ? "neg" : ""}">${formatarMoeda(a.current_balance)}</span>
        <div class="account-flow">
          <span class="up">▲ ${formatarMoeda(a.income)}</span>
          <span class="down">▼ ${formatarMoeda(a.expense)}</span>
        </div>`;
      container.appendChild(card);
    }
  }

  // ---------- Cards de cartões de crédito ----------

  /**
   * Desenha um card por cartão de crédito em `container`. Mostra a fatura
   * do mês vs limite com uma barra de uso (verde/âmbar/vermelho) e os dias
   * até o vencimento. `cards` vem do endpoint /cards.
   */
  function renderCardCards(cards, container) {
    if (!container) return;
    container.innerHTML = "";
    if (!cards || !cards.length) {
      container.innerHTML = `<p class="muted">Nenhum cartão cadastrado. Crie na página Cartões.</p>`;
      return;
    }
    for (const c of cards) {
      const pct = Math.min(100, Math.max(0, Number(c.usage_pct) || 0));
      // Cor da barra conforme o uso do limite.
      const nivel = pct >= 80 ? "danger" : pct >= 50 ? "warning" : "ok";
      const venceLogo = c.days_until_due <= 5;
      const card = document.createElement("article");
      card.className = "card credit-card";
      card.style.setProperty("--acc-color", c.color || "var(--purple, #8B5CF6)");
      card.innerHTML = `
        <div class="cc-top">
          <span class="cc-name">💳 ${escapeHtml(c.name)}</span>
          <span class="badge ${c.status === "bloqueado" ? "badge-danger" : ""}">${escapeHtml(c.brand)}</span>
        </div>
        <div class="cc-invoice">
          <span class="cc-label">Fatura do mês</span>
          <span class="cc-value">${formatarMoeda(c.invoice)}</span>
        </div>
        <div class="cc-bar"><span class="cc-bar-fill ${nivel}" style="width:${pct}%"></span></div>
        <div class="cc-foot">
          <span>${pct.toFixed(0)}% de ${formatarMoeda(c.limit_total)}</span>
          <span class="${venceLogo ? "cc-due-soon" : "muted"}">vence em ${c.days_until_due}d</span>
        </div>
        <div class="cc-foot"><span class="muted">Disponível: ${formatarMoeda(c.available)}</span></div>`;
      container.appendChild(card);
    }
  }

  // ---------- Cards de metas financeiras ----------

  // Rótulos amigáveis por tipo de meta.
  const GOAL_KIND_LABEL = {
    limite_gasto: "Limite de gasto",
    poupanca: "Poupança",
    divida: "Quitar dívida",
  };

  /**
   * Desenha um card por meta em `container`, com barra de progresso.
   * Em limite_gasto, ultrapassar o alvo fica vermelho (estourou); nos
   * demais, chegar a 100% fica verde (atingida). `goals` vem de /goals.
   */
  function renderGoalCards(goals, container) {
    if (!container) return;
    container.innerHTML = "";
    if (!goals || !goals.length) {
      container.innerHTML = `<p class="muted">Nenhuma meta cadastrada. Crie na página Metas.</p>`;
      return;
    }
    for (const g of goals) {
      const pct = Math.max(0, Number(g.pct) || 0);
      const barW = Math.min(100, pct);
      // Cor da barra: limite_gasto inverte a lógica (cheio = ruim).
      let nivel;
      if (g.kind === "limite_gasto") {
        nivel = g.exceeded ? "danger" : pct >= 80 ? "warning" : "ok";
      } else {
        nivel = g.status === "atingida" ? "ok" : "info";
      }
      const prazo = g.days_left == null
        ? ""
        : g.days_left < 0
          ? `<span class="cc-due-soon">prazo vencido há ${Math.abs(g.days_left)}d</span>`
          : `<span class="muted">faltam ${g.days_left}d</span>`;
      const sub = g.kind === "limite_gasto" && g.category
        ? `${GOAL_KIND_LABEL[g.kind]} • ${escapeHtml(g.category)}`
        : GOAL_KIND_LABEL[g.kind] || g.kind;

      const card = document.createElement("article");
      card.className = "card goal-card";
      card.style.setProperty("--acc-color", g.color || "var(--primary)");
      card.innerHTML = `
        <div class="cc-top">
          <span class="cc-name">🎯 ${escapeHtml(g.name)}</span>
          ${g.status === "atingida" ? `<span class="badge badge-ok">✓ atingida</span>` : g.exceeded ? `<span class="badge badge-danger">estourou</span>` : ""}
        </div>
        <div class="goal-sub muted">${sub}</div>
        <div class="cc-invoice">
          <span class="cc-value">${formatarMoeda(g.current_value)}</span>
          <span class="cc-label">de ${formatarMoeda(g.target_amount)}</span>
        </div>
        <div class="cc-bar"><span class="cc-bar-fill ${nivel}" style="width:${barW}%"></span></div>
        <div class="cc-foot"><span>${pct.toFixed(0)}%</span>${prazo}</div>`;
      container.appendChild(card);
    }
  }

  // ---------- Lista de alertas ----------

  /**
   * Renderiza os alertas (não lidos) em `container`. Cada um tem um botão
   * "marcar como lido" que esconde o alerta (guardado no localStorage) e
   * re-renderiza. `onChange` roda após marcar (ex: atualizar badge/seção).
   */
  function renderAlerts(alerts, container, { onChange } = {}) {
    if (!container) return;
    const visiveis = unreadAlerts(alerts);
    container.innerHTML = "";
    if (!visiveis.length) {
      container.innerHTML = `<p class="muted">Nenhum alerta pendente. Tudo em ordem! 🎉</p>`;
      return;
    }
    const corPorSev = { danger: "danger", warning: "warning", info: "info" };
    for (const a of visiveis) {
      const cor = corPorSev[a.severity] || "info";
      const card = document.createElement("div");
      card.className = "card alert-item";
      card.style.borderLeft = `4px solid var(--${cor})`;
      card.innerHTML = `
        <div class="alert-body">
          <h3>${a.icon || "🔔"} ${escapeHtml(a.title)}</h3>
          <p>${escapeHtml(a.message)}</p>
        </div>
        <button class="btn btn-ghost btn-sm" data-read="${escapeHtml(a.key)}">✓ Lido</button>`;
      container.appendChild(card);
    }
    container.querySelectorAll("[data-read]").forEach((b) =>
      b.addEventListener("click", () => {
        markAlertRead(b.dataset.read);
        renderAlerts(alerts, container, { onChange });
        refreshAlertBadge();
        if (onChange) onChange();
      }));
  }

  // ---------- Tabela de transações ----------

  /**
   * Renderiza linhas na tabela. `opts`:
   *  - tbody: elemento <tbody> alvo
   *  - emptyEl: elemento mostrado quando vazio
   *  - onDelete(id), onEdit(transaction): callbacks dos botões (opcionais)
   *  - withActions: mostra a coluna de ações (default true)
   */
  function renderTransactionsTable(transactions, opts = {}) {
    const { tbody, emptyEl, onDelete, onEdit, withActions = true } = opts;
    if (!tbody) return;
    tbody.innerHTML = "";
    if (emptyEl) emptyEl.hidden = transactions.length > 0;

    for (const t of transactions) {
      const tr = document.createElement("tr");
      const acoes = withActions ? `
        <td class="num">
          ${onEdit ? `<button class="icon-btn" data-edit="${t.id}" title="Editar">✏️</button>` : ""}
          ${onDelete ? `<button class="icon-btn danger" data-del="${t.id}" title="Excluir">🗑</button>` : ""}
        </td>` : "";

      tr.innerHTML = `
        <td>${formatarData(t.date)}</td>
        <td><span class="tag ${t.type}">${t.type}</span></td>
        <td>${escapeHtml(t.category)}</td>
        <td class="col-optional">${escapeHtml(t.spent_by)}</td>
        <td class="col-optional">${escapeHtml(t.payment_method)}</td>
        <td class="col-optional">${escapeHtml(t.account)}</td>
        <td class="num amount ${t.type}">${formatarMoeda(t.amount)}</td>
        <td class="col-optional">${escapeHtml(t.description)}</td>
        ${acoes}`;
      tbody.appendChild(tr);
    }

    if (onDelete) {
      tbody.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => onDelete(Number(b.dataset.del))));
    }
    if (onEdit) {
      tbody.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => {
          const tx = transactions.find((x) => x.id === Number(b.dataset.edit));
          if (tx) onEdit(tx);
        }));
    }
  }

  // ---------- Gráficos (Chart.js) ----------

  // Guarda as instâncias por id de canvas para destruir antes de
  // redesenhar (Chart.js não deixa dois gráficos no mesmo canvas).
  const charts = {};
  const PALETTE = [
    "#10B981", "#EF4444", "#3B82F6", "#F59E0B", "#8B5CF6",
    "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
  ];

  function destroyChart(canvasId) {
    if (charts[canvasId]) { charts[canvasId].destroy(); delete charts[canvasId]; }
  }

  /**
   * Lê uma variável CSS do tema atual (ex: "--text"). Assim os gráficos
   * acompanham o tema claro/escuro sem cores fixas. `fallback` é usado se
   * a variável não existir.
   */
  function cssVar(name, fallback = "#000") {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
    return v || fallback;
  }

  /** Mostra "sem dados" no lugar do gráfico quando o objeto está vazio. */
  function chartEmptyOrData(canvasId, obj) {
    const canvas = $("#" + canvasId);
    if (!canvas) return false;
    const wrap = canvas.parentElement;
    const entries = Array.isArray(obj) ? obj : Object.entries(obj || {});
    const vazio = !entries.length || entries.every(([, v]) => !v);
    let empty = wrap.querySelector(".chart-empty");
    if (vazio) {
      destroyChart(canvasId);
      canvas.style.display = "none";
      if (!empty) {
        empty = document.createElement("div");
        empty.className = "chart-empty";
        empty.textContent = "Sem dados neste período.";
        wrap.appendChild(empty);
      }
      return false;
    }
    if (empty) empty.remove();
    canvas.style.display = "";
    return true;
  }

  /** Gráfico de pizza/rosca. data = { rótulo: valor }. */
  function renderPie(canvasId, data) {
    if (!chartEmptyOrData(canvasId, data)) return;
    destroyChart(canvasId);
    const labels = Object.keys(data);
    charts[canvasId] = new Chart($("#" + canvasId), {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data: Object.values(data),
          backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length]),
          borderColor: cssVar("--card", "#1E293B"),
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: "right", labels: { color: cssVar("--text", "#F1F5F9"), boxWidth: 12 } },
          tooltip: { callbacks: { label: (c) => `${c.label}: ${formatarMoeda(c.parsed)}` } },
        },
      },
    });
  }

  /**
   * Gráfico de barras. data = { rótulo: valor }.
   * `color` pode ser string (cor única) ou função(label)->cor.
   */
  function renderBar(canvasId, data, color = "#3B82F6") {
    if (!chartEmptyOrData(canvasId, data)) return;
    destroyChart(canvasId);
    const labels = Object.keys(data);
    const cores = labels.map((l, i) =>
      typeof color === "function" ? color(l) : color);
    charts[canvasId] = new Chart($("#" + canvasId), {
      type: "bar",
      data: { labels, datasets: [{ data: Object.values(data), backgroundColor: cores, borderRadius: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => formatarMoeda(c.parsed.y) } },
        },
        scales: {
          x: { ticks: { color: cssVar("--muted", "#94A3B8") }, grid: { display: false } },
          y: { ticks: { color: cssVar("--muted", "#94A3B8"), callback: (v) => formatarMoeda(v) }, grid: { color: cssVar("--border", "#334155") } },
        },
      },
    });
  }

  /**
   * Gráfico de barras AGRUPADAS (comparação lado a lado).
   * `labels` = eixo X; `series` = [{ label, data: [...], color }].
   * Usado para "categoria: mês atual vs anterior".
   */
  function renderGroupedBars(canvasId, labels, series) {
    const algumDado = series.some((s) => s.data.some((v) => v));
    if (!labels.length || !algumDado) { chartEmptyOrData(canvasId, {}); return; }
    const canvas = $("#" + canvasId);
    if (canvas) { canvas.style.display = ""; const e = canvas.parentElement.querySelector(".chart-empty"); if (e) e.remove(); }
    destroyChart(canvasId);
    charts[canvasId] = new Chart($("#" + canvasId), {
      type: "bar",
      data: {
        labels,
        datasets: series.map((s) => ({
          label: s.label,
          data: s.data,
          backgroundColor: s.color,
          borderRadius: 6,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: cssVar("--text", "#F1F5F9") } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${formatarMoeda(c.parsed.y)}` } },
        },
        scales: {
          x: { ticks: { color: cssVar("--muted", "#94A3B8") }, grid: { display: false } },
          y: { ticks: { color: cssVar("--muted", "#94A3B8"), callback: (v) => formatarMoeda(v) }, grid: { color: cssVar("--border", "#334155") } },
        },
      },
    });
  }

  /**
   * Gráfico de linha (evolução). `labels` = eixo X (meses).
   * `series` = [{ label, data: [...], color }]
   */
  function renderLine(canvasId, labels, series) {
    const algumDado = series.some((s) => s.data.some((v) => v));
    if (!algumDado) { chartEmptyOrData(canvasId, {}); return; }
    const canvas = $("#" + canvasId);
    if (canvas) { canvas.style.display = ""; const e = canvas.parentElement.querySelector(".chart-empty"); if (e) e.remove(); }
    destroyChart(canvasId);
    charts[canvasId] = new Chart($("#" + canvasId), {
      type: "line",
      data: {
        labels,
        datasets: series.map((s) => ({
          label: s.label,
          data: s.data,
          borderColor: s.color,
          backgroundColor: s.color + "33",
          tension: .3,
          fill: true,
          pointRadius: 3,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: cssVar("--text", "#F1F5F9") } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${formatarMoeda(c.parsed.y)}` } },
        },
        scales: {
          x: { ticks: { color: cssVar("--muted", "#94A3B8") }, grid: { color: cssVar("--border", "#334155") } },
          y: { ticks: { color: cssVar("--muted", "#94A3B8"), callback: (v) => formatarMoeda(v) }, grid: { color: cssVar("--border", "#334155") } },
        },
      },
    });
  }

  /**
   * Recolore os gráficos já desenhados quando o tema muda. Como o Chart.js
   * desenha num <canvas> (e não em DOM/CSS), ele não acompanha as variáveis
   * sozinho — então atualizamos eixos, legendas e bordas na mão.
   */
  function recolorCharts() {
    const text = cssVar("--text", "#F1F5F9");
    const muted = cssVar("--muted", "#94A3B8");
    const border = cssVar("--border", "#334155");
    const card = cssVar("--card", "#1E293B");
    for (const ch of Object.values(charts)) {
      const o = ch.options || {};
      if (o.plugins?.legend?.labels) o.plugins.legend.labels.color = text;
      for (const axis of Object.values(o.scales || {})) {
        if (axis.ticks) axis.ticks.color = muted;
        if (axis.grid && axis.grid.color) axis.grid.color = border;
      }
      // Borda das fatias do doughnut acompanha o fundo do card.
      ch.data?.datasets?.forEach((ds) => {
        if (ch.config.type === "doughnut") ds.borderColor = card;
      });
      ch.update("none");
    }
  }

  // Ao alternar tema, recolore os gráficos visíveis (sem recarregar dados).
  window.addEventListener("themechange", recolorCharts);

  // ---------- Conselho local (fallback baseado em regras) ----------

  /**
   * Gera conselhos a partir do resumo mensal SEM usar IA externa.
   * Retorna { resumo, dicas: [{tipo, texto}] }. Usado quando o
   * endpoint de IA não está disponível (ver Api.generateConselho).
   */
  function conselhoLocal(summary) {
    const dicas = [];
    const { total_incomes: rec, total_expenses: desp, balance: saldo } = summary;
    const taxaGasto = rec > 0 ? desp / rec : (desp > 0 ? 1 : 0);

    if (summary.count === 0) {
      dicas.push({ tipo: "info", texto: "Ainda não há lançamentos neste mês. Comece registrando suas receitas e despesas para receber análises." });
      return { resumo: "Sem dados suficientes para análise.", dicas };
    }

    // Saldo
    if (saldo < 0) {
      dicas.push({ tipo: "err", texto: `Seu saldo está negativo em ${formatarMoeda(Math.abs(saldo))}. As despesas superaram as receitas — vale revisar os gastos do mês.` });
    } else if (taxaGasto > 0.9 && rec > 0) {
      dicas.push({ tipo: "err", texto: `Você gastou ${(taxaGasto * 100).toFixed(0)}% do que recebeu. A margem está apertada; tente segurar despesas não essenciais.` });
    } else if (rec > 0) {
      dicas.push({ tipo: "ok", texto: `Boa! Você guardou ${formatarMoeda(saldo)} (${((saldo / rec) * 100).toFixed(0)}% das receitas). Considere direcionar parte para investimentos.` });
    }

    // Maior categoria de despesa
    const cats = Object.entries(summary.expenses_by_category || {}).sort((a, b) => b[1] - a[1]);
    if (cats.length) {
      const [cat, val] = cats[0];
      const pct = desp > 0 ? (val / desp) * 100 : 0;
      dicas.push({ tipo: pct > 40 ? "err" : "info", texto: `Maior gasto: "${cat}" com ${formatarMoeda(val)} (${pct.toFixed(0)}% das despesas).${pct > 40 ? " Concentração alta — observe se dá pra reduzir." : ""}` });
    }

    // Pessoa que mais gastou
    const pessoas = Object.entries(summary.expenses_by_person || {}).sort((a, b) => b[1] - a[1]);
    if (pessoas.length > 1) {
      dicas.push({ tipo: "info", texto: `Quem mais gastou: ${pessoas[0][0]} (${formatarMoeda(pessoas[0][1])}).` });
    }

    const resumo = `No mês você teve ${formatarMoeda(rec)} de receitas e ${formatarMoeda(desp)} de despesas, ` +
                   `resultando em saldo de ${formatarMoeda(saldo)} em ${summary.count} lançamento(s).`;
    return { resumo, dicas };
  }

  return {
    mountLayout, showMessage, showStatus, clearStatus, fillSelect,
    renderKPIs, renderAccountCards, renderCardCards, renderGoalCards, renderTransactionsTable,
    renderAlerts, refreshAlertBadge, unreadAlerts, markAlertRead, clearReadAlerts,
    renderPie, renderBar, renderLine, renderGroupedBars, destroyChart,
    conselhoLocal,
  };
})();
