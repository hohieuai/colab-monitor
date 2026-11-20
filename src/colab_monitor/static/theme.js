"use strict";
// Runs before first paint (loaded synchronously in <head>) so a saved theme or a collapsed sidebar never flashes.
try {
  const t = localStorage.getItem("theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  if (localStorage.getItem("sidebar") === "collapsed") document.documentElement.dataset.sidebar = "collapsed";
} catch {}
