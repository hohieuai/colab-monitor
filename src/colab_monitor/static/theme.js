"use strict";
// Runs before first paint (loaded synchronously in <head>) so a saved theme never flashes.
try {
  const t = localStorage.getItem("theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch {}
