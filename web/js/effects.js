// Effets « film radiographique », écrits pour ce projet (sans bibliothèque).
// Inspirés de l'esprit des composants React Bits (texte qui se « décrypte », grain de film),
// mais réimplémentés en JS natif : pas de React ni d'étape de build, tout marche hors ligne.

export const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Grain de film : une petite tuile de bruit générée une fois, répétée à sa taille réelle (grain fin).
export function filmNoise(el) {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = size;
  c.height = size;
  const ctx = c.getContext("2d");
  const img = ctx.createImageData(size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.random() * 255;
    img.data[i] = v * 0.75; img.data[i + 1] = v; img.data[i + 2] = v; img.data[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  el.style.backgroundImage = `url(${c.toDataURL()})`;
}

// Texte qui se « décrypte » : des glyphes aléatoires laissent place au vrai texte, lettre par lettre.
export function decrypt(el, duration = 900) {
  const target = el.textContent;
  if (reducedMotion) return;
  const glyphs = "▚▞▖▗▘▙█▓▒░01#%$&";
  const t0 = performance.now();
  const tick = now => {
    const k = Math.min(1, (now - t0) / duration);
    const n = Math.floor(k * target.length);
    el.textContent = target.slice(0, n) + [...target.slice(n)].map(c => c === " " ? " " : glyphs[Math.floor(Math.random() * glyphs.length)]).join("");
    if (k < 1) requestAnimationFrame(tick); else el.textContent = target;
  };
  requestAnimationFrame(tick);
}

// Balayage : la ligne de scan descend et révèle les couches au fur et à mesure.
export function scan(scanlineEl, revealEls, total = 2600) {
  if (reducedMotion) {
    revealEls.forEach(el => el.classList.add("on"));
    return;
  }
  scanlineEl.classList.remove("run");
  void scanlineEl.offsetWidth;                // relance l'animation CSS
  scanlineEl.classList.add("run");
  const maxY = Math.max(...revealEls.map(el => Number(el.dataset.y || 0)), 1);
  revealEls.forEach(el => {
    const y = Number(el.dataset.y || 0);
    setTimeout(() => el.classList.add("on"), 120 + (y / maxY) * (total - 300));
  });
}
