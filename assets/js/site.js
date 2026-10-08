/* Comportamento do site. Sem dependencias, e tudo opcional: sem JavaScript o
   site continua completo, so sem o botao de tema e com datas absolutas. */
(function () {
  "use strict";
  var root = document.documentElement;
  var lang = root.getAttribute("lang") || "en";

  // Tema claro/escuro. O <head> ja aplicou a escolha salva antes de pintar;
  // aqui so liga o botao e grava a troca.
  var toggle = document.querySelector("[data-theme-toggle]");
  function isDark() { return root.getAttribute("data-theme") === "dark"; }
  function syncToggle() {
    if (toggle) toggle.setAttribute("aria-pressed", isDark() ? "true" : "false");
  }
  if (toggle) {
    toggle.hidden = false;
    syncToggle();
    toggle.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) { /* navegacao privada */ }
      syncToggle();
    });
  }

  // "ha 2 h", "ontem". O HTML e gerado uma vez e servido por dias; um horario
  // relativo escrito no build ficaria errado. Acima de uma semana, mantem a
  // data absoluta que ja veio no HTML.
  var rtf = null, short = null;
  try { rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto", style: "short" }); } catch (e) {}
  try { short = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short" }); } catch (e) {}
  // Inicio do dia no fuso de quem le: "ontem" e o dia anterior no calendario,
  // nao "entre 24 e 48 horas atras".
  function startOfDay(t) { var d = new Date(t); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); }
  if (rtf) {
    var now = Date.now();
    var times = document.querySelectorAll("time[data-relative]");
    for (var i = 0; i < times.length; i++) {
      var el = times[i];
      var at = Date.parse(el.getAttribute("datetime"));
      if (isNaN(at)) continue;
      var diff = (at - now) / 1000;
      if (diff > 300) continue;  // no futuro de verdade: fica a data absoluta
      var seconds = Math.min(diff, -60);  // relogio adiantado alguns minutos
      var abs = Math.abs(seconds);
      var text = null, relative = true;
      if (abs < 3600) text = rtf.format(Math.round(seconds / 60), "minute");
      else if (abs < 86400) text = rtf.format(Math.round(seconds / 3600), "hour");
      else {
        var days = Math.max(1, Math.round((startOfDay(now) - startOfDay(at)) / 86400000));
        if (days < 7) text = rtf.format(-days, "day");
        // Mais velho que uma semana: data curta ("25 de set."). Ano so quando
        // nao e o atual - numa coluna estreita a data longa quebra em duas linhas.
        else if (short && new Date(at).getFullYear() === new Date(now).getFullYear()) {
          text = short.format(at);
          relative = false;
        }
      }
      if (text) {
        if (!el.title) el.title = el.textContent.trim();
        el.textContent = text;
        // "Atualizado em 2 de outubro" vira "Atualizado ha 2 h": a preposicao
        // so serve para a data absoluta.
        var label = relative && el.parentNode && el.parentNode.querySelector("[data-relative-label]");
        if (label) label.textContent = label.getAttribute("data-relative-label");
      }
    }
  }

  // Data de hoje no topo, pelo relogio de quem le.
  var today = document.querySelectorAll("[data-today]");
  if (today.length) {
    var d = new Date();
    var weekday = "", date = "";
    try {
      weekday = new Intl.DateTimeFormat(lang, { weekday: "long" }).format(d);
      date = new Intl.DateTimeFormat(lang, { day: "numeric", month: "long", year: "numeric" }).format(d);
    } catch (e) {}
    if (date) {
      var iso = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" +
        String(d.getDate()).padStart(2, "0");
      for (var j = 0; j < today.length; j++) {
        var node = today[j];
        var time = document.createElement("time");
        time.setAttribute("datetime", iso);
        if (weekday) {
          var wd = document.createElement("span");
          wd.className = "weekday";
          wd.textContent = weekday + ", ";
          time.appendChild(wd);
        }
        time.appendChild(document.createTextNode(date));
        node.textContent = "";
        node.appendChild(time);
        node.hidden = false;
      }
    }
  }

  // Contadores da capa ("matérias hoje", "nesta semana"): o build deixou a
  // conta da hora em que rodou; aqui ela é refeita pelo relógio de quem lê.
  var stats = document.querySelector("[data-stats]");
  if (stats) {
    var stamps = (stats.getAttribute("data-times") || "").split(",");
    var dayStart = new Date(); dayStart.setHours(0, 0, 0, 0);
    var weekAgo = Date.now() - 7 * 86400000, todayN = 0, weekN = 0;
    for (var k = 0; k < stamps.length; k++) {
      var ts = Date.parse(stamps[k]);
      if (isNaN(ts)) continue;
      if (ts >= weekAgo) weekN++;
      if (ts >= dayStart.getTime()) todayN++;
    }
    var outToday = stats.querySelector('[data-stat="today"]');
    var outWeek = stats.querySelector('[data-stat="week"]');
    if (outToday) outToday.textContent = todayN;
    if (outWeek) outWeek.textContent = weekN;
  }

  // Compartilhar: folha nativa quando o aparelho tem; senão, copia o link.
  var toast = document.querySelector("[data-toast]");
  function copied() {
    if (!toast) return;
    toast.classList.add("on");
    setTimeout(function () { toast.classList.remove("on"); }, 1800);
  }
  function copy(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(copied, function () { window.prompt("", url); });
    } else {
      window.prompt("", url);
    }
  }
  var copyButtons = document.querySelectorAll("[data-copy]");
  for (var c = 0; c < copyButtons.length; c++) {
    copyButtons[c].addEventListener("click", function () { copy(this.getAttribute("data-copy")); });
  }
  var shareButtons = document.querySelectorAll("[data-share]");
  for (var s = 0; s < shareButtons.length; s++) {
    shareButtons[s].addEventListener("click", function () {
      var url = this.getAttribute("data-share");
      if (navigator.share) {
        navigator.share({ title: this.getAttribute("data-share-title") || document.title, url: url })
          .catch(function () {});
      } else {
        copy(url);
      }
    });
  }
})();
