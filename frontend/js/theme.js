/* =========================================================
   Finance App — TEMA CLARO/ESCURO (theme.js)
   ---------------------------------------------------------
   Gerencia o tema da interface (escuro = padrão, claro = opcional).

   COMO FUNCIONA
   - O tema é só um atributo no <html>: data-theme="dark" | "light".
   - As cores de cada tema vivem em CSS (style.css = escuro/base,
     light-theme.css = sobrescreve quando data-theme="light").
   - A preferência fica salva no localStorage e é reaplicada no load.

   POR QUE ESTE ARQUIVO É CARREGADO NO <head> (e não no fim do body)?
   Para aplicar o tema ANTES da primeira pintura da tela. Se carregasse
   no fim, a página piscaria no escuro e só depois mudaria pro claro
   (o famoso "flash of wrong theme"). Por isso o trecho de aplicação
   roda imediatamente (IIFE), mesmo antes do <body> existir.

   API pública (objeto global `Theme`):
   - Theme.current()        -> "dark" | "light"
   - Theme.set(tema)        -> força um tema e salva
   - Theme.toggle()         -> alterna e salva
   - Theme.buttonHTML()     -> HTML do botão (a UI injeta na topbar)
   - Theme.wireButton()     -> liga o clique e ajusta o ícone do botão
   ========================================================= */

const Theme = (() => {
  const STORAGE_KEY = "finance-theme";
  const DEFAULT = "dark"; // tema padrão pedido no projeto

  /** Lê a preferência salva; se não houver, usa o padrão (escuro). */
  function stored() {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      return v === "light" || v === "dark" ? v : DEFAULT;
    } catch (_) {
      // localStorage pode estar bloqueado (modo privado): cai no padrão.
      return DEFAULT;
    }
  }

  /** Aplica o tema no <html> (data-theme) — é o que o CSS observa. */
  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
  }

  /** Tema atual segundo o <html> (fonte da verdade na tela). */
  function current() {
    return document.documentElement.getAttribute("data-theme") || DEFAULT;
  }

  /** Define um tema, aplica, salva e atualiza o botão (se existir). */
  function set(theme) {
    const t = theme === "light" ? "light" : "dark";
    apply(t);
    try { localStorage.setItem(STORAGE_KEY, t); } catch (_) {}
    refreshButton();
    // Avisa o resto do app (ex.: gráficos podem se redesenhar).
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: t } }));
    return t;
  }

  /** Alterna claro <-> escuro. */
  function toggle() {
    return set(current() === "dark" ? "light" : "dark");
  }

  // ---------- Botão de alternância (sol/lua) ----------

  /** HTML do botão; a UI injeta isso na topbar. */
  function buttonHTML() {
    return `<button id="theme-toggle" class="theme-toggle" type="button"
              aria-label="Alternar tema" title="Alternar tema claro/escuro"></button>`;
  }

  /** Ajusta o ícone do botão conforme o tema atual. */
  function refreshButton() {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    const dark = current() === "dark";
    // No escuro mostramos a lua; no claro, o sol (representam o estado atual).
    // Ícone SVG via Icons (icons.js); fallback textual se não estiver carregado.
    if (typeof Icons !== "undefined") {
      btn.innerHTML = Icons.svg(dark ? "moon" : "sun");
    } else {
      btn.textContent = dark ? "Escuro" : "Claro";
    }
    btn.setAttribute("aria-pressed", String(!dark));
  }

  /** Liga o clique do botão (chamado pela UI depois de montar a topbar). */
  function wireButton() {
    const btn = document.getElementById("theme-toggle");
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", toggle);
    refreshButton();
  }

  // Aplica o tema salvo IMEDIATAMENTE (antes da pintura). Sem esperar DOM.
  apply(stored());

  return { current, set, toggle, buttonHTML, wireButton, refreshButton };
})();
