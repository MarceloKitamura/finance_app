/* =========================================================
   Finance App — ÍCONES (icons.js)
   ---------------------------------------------------------
   Sistema de ícones SVG de traço (estilo Lucide/Feather) que
   substitui os emojis da interface. Cada ícone herda a cor do
   texto ao redor (stroke="currentColor"), então acompanha tema,
   estados (hover/ativo) e cores semânticas sem ajuste extra.

   COMO USAR
   - Em HTML estático: <i data-icon="plus"></i>
     (o hydrate() roda no DOMContentLoaded e injeta o SVG).
     Tamanho opcional: <i data-icon="plus" data-size="18"></i>
   - Em JS (template strings): Icons.svg("plus")
     Opções: Icons.svg("plus", { size: 18, cls: "minha-classe" })

   API pública (objeto global `Icons`):
   - Icons.svg(name, opts)   -> string com o <svg> inline
   - Icons.hydrate(root)     -> troca placeholders [data-icon] por SVG
   - Icons.has(name)         -> o ícone existe?
   ========================================================= */

const Icons = (() => {
  // Conteúdo interno de cada ícone (viewBox 0 0 24 24, traço).
  // Mantemos só os paths — o wrapper <svg> é montado em svg().
  const PATHS = {
    // ---- Navegação ----
    dashboard:
      '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    transactions:
      '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>',
    calendar:
      '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 2v4"/><path d="M16 2v4"/>',
    card:
      '<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>',
    target:
      '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    bell:
      '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    chart:
      '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    ai:
      '<path d="M12 3v3"/><path d="M12 18v3"/><path d="M4.5 12h-1.5"/><path d="M21 12h-1.5"/><path d="M12 7.5 13.6 11 17 12l-3.4 1L12 16.5 10.4 13 7 12l3.4-1z"/>',
    settings:
      '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',

    // ---- Ações / utilitários ----
    wallet:
      '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/><path d="M18 12h.01"/>',
    plus:
      '<path d="M5 12h14"/><path d="M12 5v14"/>',
    save:
      '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
    edit:
      '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    trash:
      '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    search:
      '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    filter:
      '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    download:
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    upload:
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    eye:
      '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    refresh:
      '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/>',
    check:
      '<polyline points="20 6 9 17 4 12"/>',
    menu:
      '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
    file:
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    user:
      '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    recurring:
      '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    pin:
      '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    clock:
      '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    bank:
      '<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
    droplet:
      '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>',
    forecast:
      '<circle cx="12" cy="10" r="7"/><path d="M5 21h14"/><path d="M9.5 6.5a3.5 3.5 0 0 1 3-1.5"/>',

    // ---- Setas ----
    "arrow-right":
      '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "arrow-left":
      '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "arrow-up":
      '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
    "arrow-down":
      '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',

    // ---- Estados / severidade ----
    "alert-triangle":
      '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    lightbulb:
      '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    info:
      '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    success:
      '<path d="M21.8 10A10 10 0 1 1 17 3.34"/><path d="m9 11 3 3L22 4"/>',
    danger:
      '<path d="M12 16h.01"/><path d="M12 8v4"/><path d="M15.31 2a2 2 0 0 1 1.42.59l4.68 4.68A2 2 0 0 1 22 8.69v6.62a2 2 0 0 1-.59 1.42l-4.68 4.68a2 2 0 0 1-1.42.59H8.69a2 2 0 0 1-1.42-.59l-4.68-4.68A2 2 0 0 1 2 15.31V8.69a2 2 0 0 1 .59-1.42l4.68-4.68A2 2 0 0 1 8.69 2z"/>',

    // ---- Tema ----
    sun:
      '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon:
      '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  };

  // Apelidos: nomes amigáveis que apontam para um ícone existente.
  const ALIAS = {
    receita: "arrow-up",
    despesa: "arrow-down",
    brand: "wallet",
    "line-chart": "chart",
    pie: "chart",
    person: "user",
    "trending-down": "danger",
  };

  function resolve(name) {
    if (PATHS[name]) return name;
    if (ALIAS[name] && PATHS[ALIAS[name]]) return ALIAS[name];
    return null;
  }

  function has(name) {
    return resolve(name) != null;
  }

  /**
   * Retorna o <svg> de um ícone como string.
   * opts.size  -> largura/altura em px (default 20)
   * opts.cls   -> classe(s) extra(s) no <svg>
   */
  function svg(name, opts = {}) {
    const key = resolve(name);
    if (!key) return ""; // ícone desconhecido: não quebra a UI.
    const size = opts.size || 20;
    const cls = opts.cls ? ` ${opts.cls}` : "";
    return (
      `<svg class="ic-svg${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" ` +
      `fill="none" stroke="currentColor" stroke-width="1.75" ` +
      `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[key]}</svg>`
    );
  }

  /**
   * Substitui placeholders <i data-icon="nome"> pelo SVG correspondente.
   * Idempotente: marca os já processados com data-hydrated.
   */
  function hydrate(root = document) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-icon]").forEach((el) => {
      if (el.dataset.hydrated) return;
      const name = el.getAttribute("data-icon");
      const size = el.getAttribute("data-size");
      const markup = svg(name, size ? { size: Number(size) } : {});
      if (!markup) return;
      el.classList.add("ic");
      el.innerHTML = markup;
      el.dataset.hydrated = "1";
    });
  }

  // Hidrata o HTML estático assim que o DOM estiver pronto.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => hydrate());
  } else {
    hydrate();
  }

  return { svg, hydrate, has };
})();
