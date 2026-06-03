/* =========================================================
   Finance App — UTILS (utils.js)
   ---------------------------------------------------------
   Funções auxiliares "puras": formatação, datas, validação e
   pequenos helpers. Nada aqui fala com a API nem com o DOM
   (exceto os atalhos $/$$). Tudo é exposto no objeto global
   `Utils` para os outros módulos usarem.
   ========================================================= */

const Utils = (() => {
  const MONTHS = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
  ];

  /** Formata número como moeda BRL: 1234.5 -> "R$ 1.234,50". */
  function formatarMoeda(valor) {
    const n = Number(valor) || 0;
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  /** "YYYY-MM-DD" -> "DD/MM/AAAA". Tolera valores vazios. */
  function formatarData(iso) {
    if (!iso) return "";
    const [y, m, d] = String(iso).slice(0, 10).split("-");
    return d && m && y ? `${d}/${m}/${y}` : iso;
  }

  /** "YYYY-MM-DD" -> objeto Date local (sem fuso bagunçar o dia). */
  function parseDate(str) {
    if (!str) return null;
    const [y, m, d] = String(str).slice(0, 10).split("-").map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
  }

  /** Data de hoje no formato do <input type="date">: "YYYY-MM-DD". */
  function hojeISO() {
    const now = new Date();
    const off = now.getTimezoneOffset();
    return new Date(now.getTime() - off * 60000).toISOString().slice(0, 10);
  }

  /** Nome do mês (1-12) -> "Janeiro". */
  function nomeMes(m) { return MONTHS[(m - 1 + 12) % 12]; }

  /**
   * Decide a classe da faixa lateral do card de saldo a partir do valor.
   * Retorna a classe CSS: "is-pos" (azul), "is-neg" (vermelho), "is-zero".
   * Combina com as regras em cards.css.
   */
  function corSaldo(saldo) {
    const n = Number(saldo) || 0;
    if (n > 0) return "is-pos";
    if (n < 0) return "is-neg";
    return "is-zero";
  }

  /**
   * Valida os dados de uma transação ANTES de enviar à API.
   * (A API valida de novo; isto é só pra dar feedback rápido ao usuário.)
   * Retorna { ok: boolean, erros: string[] }.
   */
  function validarTransacao(data) {
    const erros = [];
    if (!data.date) erros.push("Informe a data.");
    if (!data.description || !data.description.trim()) erros.push("Informe a descrição.");
    if (!(Number(data.amount) > 0)) erros.push("O valor deve ser maior que zero.");
    if (data.type !== "receita" && data.type !== "despesa") erros.push("Tipo inválido.");
    if (!data.category || !data.category.trim()) erros.push("Escolha uma categoria.");
    if (!data.payment_method) erros.push("Escolha a forma de pagamento.");
    return { ok: erros.length === 0, erros };
  }

  /** Calcula variação percentual de `anterior` para `atual`. */
  function variacaoPct(atual, anterior) {
    if (!anterior) return atual ? 100 : 0;
    return ((atual - anterior) / Math.abs(anterior)) * 100;
  }

  /** Soma uma lista de objetos por uma chave numérica. */
  function somaPor(lista, chave) {
    return lista.reduce((acc, x) => acc + (Number(x[chave]) || 0), 0);
  }

  /**
   * Agrupa e soma valores. Ex: agrupaSoma(txs, "category", "amount")
   * -> { Mercado: 300, Lazer: 120, ... } (ordenado do maior pro menor).
   */
  function agrupaSoma(lista, chaveGrupo, chaveValor) {
    const acc = {};
    for (const item of lista) {
      const k = item[chaveGrupo] || "—";
      acc[k] = (acc[k] || 0) + (Number(item[chaveValor]) || 0);
    }
    return Object.fromEntries(
      Object.entries(acc).sort((a, b) => b[1] - a[1])
    );
  }

  /** Debounce: adia a execução até parar de "disparar" por `ms`. */
  function debounce(fn, ms = 250) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  /** Escapa texto para inserir com segurança em innerHTML. */
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  // Atalhos de DOM (usados pelos outros módulos e nas páginas).
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  return {
    MONTHS, formatarMoeda, formatarData, parseDate, hojeISO, nomeMes,
    corSaldo, validarTransacao, variacaoPct, somaPor, agrupaSoma,
    debounce, escapeHtml, $, $$,
  };
})();
