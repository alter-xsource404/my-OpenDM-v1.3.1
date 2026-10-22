// OpenDM floating video sniffer: a draggable panel with a quality picker, plus a
// "Download video" button that appears when you hover a <video>. Runs in every frame;
// only the top frame draws the panel. Everything lives in a closed shadow root.
(() => {
  "use strict";
  if (window.__opendmSniffer || !document.documentElement) return;
  window.__opendmSniffer = true;

  const api = globalThis.browser ?? globalThis.chrome;
  const isTop = window === window.top;
  /* ICON-BEGIN */ const ICON = "data:image/png;base64,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"; /* ICON-END */

  const CSS = `
    :host{all:initial;--bg:#fff;--fg:#111827;--bd:#e5e7eb;--chip:#e5e7eb}
    @media (prefers-color-scheme:dark){:host{--bg:#1f2937;--fg:#f3f4f6;--bd:#374151;--chip:#374151}}
    *{box-sizing:border-box;font:13px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
    .box{position:fixed;right:20px;bottom:90px;color:var(--fg)}
    .bubble{width:46px;height:46px;border-radius:50%;background:#2563eb;box-shadow:0 4px 14px #0006;cursor:pointer;
            display:flex;align-items:center;justify-content:center;position:relative;touch-action:none}
    .bubble img{width:28px;height:28px;pointer-events:none}
    .badge{position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;border-radius:9px;background:#ef4444;color:#fff;
           font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;padding:0 4px}
    .panel{width:min(360px,calc(100vw - 24px));max-height:min(70vh,520px);display:flex;flex-direction:column;background:var(--bg);
           border:1px solid var(--bd);border-radius:12px;box-shadow:0 10px 30px #0006;overflow:hidden}
    .head{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#2563eb;color:#fff;cursor:move;user-select:none;touch-action:none}
    .head b{flex:1;font-size:13px}
    .head button{all:unset;cursor:pointer;width:22px;height:22px;text-align:center;border-radius:5px;line-height:22px;font-size:16px}
    .head button:hover{background:#fff3}
    .body{overflow:auto;padding:2px 10px}
    .row{padding:9px 0;border-bottom:1px solid var(--bd)} .row:last-child{border:0}
    .t{display:flex;gap:6px;align-items:center;margin-bottom:6px}
    .name{flex:1;min-width:0;padding:5px 7px;border-radius:6px;border:1px solid var(--bd);background:var(--bg);color:var(--fg);font-weight:600}
    .chip{font-size:10px;font-weight:700;padding:1px 6px;border-radius:8px;background:var(--chip)}
    .ctl{display:flex;gap:8px;align-items:center}
    select{flex:1;min-width:0;padding:5px 6px;border-radius:6px;border:1px solid var(--bd);background:var(--bg);color:var(--fg)}
    .meta{flex:1;min-width:0;opacity:.85}
    .mix{display:block;margin:0 0 7px;font-size:12px;cursor:pointer}
    .mix input{margin:0 6px 0 0;vertical-align:middle}
    .dl{padding:6px 12px;border:0;border-radius:6px;background:#2563eb;color:#fff;font-weight:600;cursor:pointer}
    .dl:disabled{opacity:.6;cursor:default}
    .empty{padding:14px 2px;opacity:.75}
    .foot{padding:6px 10px;font-size:11px;opacity:.8;border-top:1px solid var(--bd);min-height:26px}
    .foot.err{color:#ef4444;opacity:1}
    .hover{position:fixed;display:none;padding:6px 12px 6px 8px;background:#2563eb;color:#fff;border-radius:16px;
           box-shadow:0 3px 10px #0007;cursor:pointer;font-weight:600;align-items:center;gap:6px;z-index:1}
    .hover img{width:18px;height:18px}
  `;

  // ---------- helpers ----------
  const el = (tag, props = {}, ...kids) => { const e = document.createElement(tag); Object.assign(e, props); e.append(...kids); return e; };
  const send = async (msg) => { try { return await api.runtime.sendMessage(msg); } catch { return undefined; } };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const fmtSize = (n) => (n >= 1073741824 ? (n / 1073741824).toFixed(2) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.ceil(n / 1024) + " KB");
  const qLabel = (v) => {
    const rate = v.bandwidth >= 1e6 ? (v.bandwidth / 1e6).toFixed(1) + " Mbps" : Math.round(v.bandwidth / 1000) + " kbps";
    return `${v.height ? v.height + "p" + (v.fps > 30 ? v.fps : "") : "Audio / other"} · ${rate}`;
  };
  const nameOf = (it) => {
    let n = "";
    try { n = decodeURIComponent(new URL(it.url).pathname.split("/").pop() || ""); } catch {}
    if (it.kind === "hls" && (!n || /^(index|master|playlist|manifest|chunklist|main)\.m3u8?$/i.test(n)) && document.title) return document.title;
    return n || it.url;
  };
  const fmtDur = (s) => { s = Math.round(s); return s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const safeName = (s) => String(s || "").replace(/[\/\\:]+/g, "-").replace(/[?*"<>|\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 120).trim();
  const fileExt = (u) => { try { const m = new URL(u).pathname.match(/\.([a-z0-9]{2,4})$/i); return m ? m[1].toLowerCase() : "mp4"; } catch { return "mp4"; } };

  // Best guess at the video's caption: the playing <video>'s own label, then the page's social/meta title, then <h1>/<title>.
  const SITE_TAIL = /\s*[-|\u2013\u2014\u00b7]\s*(YouTube|Facebook|Instagram|TikTok|Twitter|X|Vimeo|Dailymotion|Reddit|Twitch|Bilibili)\s*$/i;
  const GENERIC = /^(facebook|instagram|youtube|tiktok|twitter|x|vimeo|home|watch|reels?|video|videos|log ?in.*|untitled)$/i;
  function cleanTitle(t) {
    t = String(t || "").replace(/\s+/g, " ").trim().replace(/^\(\d+\+?\)\s*/, "");
    const ig = t.match(/^.{1,80}? on Instagram:\s*["\u201c](.+?)["\u201d]?\s*$/s);
    return (ig ? ig[1] : t).replace(SITE_TAIL, "").trim();
  }
  function captionGuess() {
    const meta = (s) => document.querySelector(s)?.content;
    const vids = [...document.querySelectorAll("video")];
    const v = vids.find((x) => !x.paused && !x.ended) || vids[0];
    const cands = [v?.getAttribute("aria-label"), v?.title, v?.closest("figure")?.querySelector("figcaption")?.textContent,
      meta("meta[property='og:title']"), meta("meta[name='twitter:title']"), document.querySelector("h1")?.textContent,
      document.title, meta("meta[property='og:description']")];
    for (const x of cands) { const t = safeName(cleanTitle(x)); if (t.length >= 3 && !GENERIC.test(t)) return t; }
    return safeName(location.hostname) || "video";
  }
  const extOf = (u) => { try { return (new URL(u).pathname.match(/\.([a-z0-9]{2,4})$/i)?.[1] || "FILE").toUpperCase(); } catch { return "FILE"; } };

  // ---------- state ----------
  let cfg = { floating: true, hiddenSites: [] };
  const pos = { right: 20, bottom: 90 };
  let items = [], expanded = false, status = { text: "", err: false }, footEl = null, refreshTimer = 0;
  const variants = new Map();  // stream url -> null (loading) | [{height,bandwidth,fps,url}]
  const choice = new Map();    // stream url -> chosen option index ("" = best)
  const probes = new Map();    // file url -> undefined | null (checking) | {width,height,duration,video,audio,segment,size,useUrl} | false
  const mixOn = new Map();     // video url -> add the separate audio track? (default yes)
  const names = new Map();     // url -> file name shown in the box (guessed from the caption, editable)

  // ---------- shadow host ----------
  const host = el("div");
  host.style.cssText = "all:initial;position:fixed;top:0;left:0;width:0;height:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  try { const sh = new CSSStyleSheet(); sh.replaceSync(CSS); root.adoptedStyleSheets = [sh]; }  // works even under strict page CSP
  catch { root.append(el("style", { textContent: CSS })); }
  const box = el("div", { className: "box" });
  const hover = el("div", { className: "hover" }, el("img", { src: ICON }), el("span", { textContent: "Download video" }));
  root.append(box, hover);
  document.documentElement.append(host);

  const visible = () => cfg.floating && !cfg.hiddenSites.includes(location.hostname);
  function applyVisibility() { host.style.display = visible() ? "" : "none"; if (!visible()) hideHover(); }
  function applyPos() { box.style.right = pos.right + "px"; box.style.bottom = pos.bottom + "px"; }

  // ---------- dragging (the bubble also acts as a click target) ----------
  function enableDrag(handle, onClick) {
    handle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button")) return;
      const sx = e.clientX, sy = e.clientY, r0 = pos.right, b0 = pos.bottom;
      let moved = false;
      try { handle.setPointerCapture(e.pointerId); } catch {}
      const move = (m) => {
        if (Math.abs(m.clientX - sx) + Math.abs(m.clientY - sy) > 4) moved = true;
        pos.right = clamp(r0 - (m.clientX - sx), 0, innerWidth - 60);
        pos.bottom = clamp(b0 - (m.clientY - sy), 0, innerHeight - 60);
        applyPos();
      };
      const up = () => {
        handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up);
        if (moved) api.storage.local.set({ pos }); else if (onClick) onClick();
      };
      handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", up);
    });
  }

  // ---------- panel ----------
  function setStatus(text, err = false) { status = { text, err }; if (footEl) { footEl.textContent = text; footEl.className = "foot" + (err ? " err" : ""); } }
  const errorHint = (e = "") =>
    /not paired/i.test(e) ? "OpenDM isn't connected yet. Open OpenDM once: it registers itself with your browser. (Or paste a token in this extension's options.)"
    : /replied 401|token/i.test(e) ? "OpenDM and the extension disagree about the pairing token. Restart OpenDM, or re-paste the token in the extension's options."
    : /fetch|network|refused/i.test(e) || !e ? "OpenDM isn't running (or the port is wrong). Start it and try again." : e;

  function shownItems() {
    const kids = new Set();  // hide the per-quality playlists of a master we already list
    for (const v of variants.values()) (v || []).forEach((x) => kids.add(x.url));
    const height = (it) => { const p = probes.get(it.url); return p && p.video ? Math.min(p.width, p.height) : 0; };
    return items.filter((it) => !kids.has(it.url) && !(probes.get(it.url) || {}).segment)   // segments are pieces of a stream, not videos
      .reverse().sort((x, y) => (y.kind === "hls") - (x.kind === "hls") || height(y) - height(x));
  }

  // Facebook, Instagram and other DASH sites serve picture and sound as two separate files.
  // For a silent video, find the audio-only file of the same length so both can be fetched and merged.
  function audioPartner(it) {
    const p = probes.get(it.url);
    if (!p || !p.video || p.audio) return null;
    const cands = items.filter((x) => x.kind === "file" && x.url !== it.url)
      .map((x) => ({ x, q: probes.get(x.url) })).filter(({ q }) => q && q.audio && !q.video && !q.segment)
      .sort((a, b) => Math.abs((a.q.duration || 0) - (p.duration || 0)) - Math.abs((b.q.duration || 0) - (p.duration || 0)));
    const best = cands[0];
    return best && (!p.duration || !best.q.duration || Math.abs(best.q.duration - p.duration) <= 2.5) ? best : null;
  }

  function row(it) {
    const isHls = it.kind === "hls";
    const vs = isHls ? variants.get(it.url) : undefined;
    const p = isHls ? undefined : probes.get(it.url);
    if (!names.has(it.url)) names.set(it.url, captionGuess());
    const nameBox = el("input", { className: "name", type: "text", value: names.get(it.url), spellcheck: false, title: "File name - you can edit it" });
    nameBox.oninput = () => names.set(it.url, nameBox.value);
    const dl = el("button", { className: "dl", textContent: "Download" });
    const partner = isHls ? null : audioPartner(it);
    let mix = null;
    if (partner) {
      mix = el("input", { type: "checkbox", checked: mixOn.get(it.url) !== false });
      mix.onchange = () => mixOn.set(it.url, mix.checked);
    }
    let sel = null, mid;
    if (isHls) {
      sel = el("select");
      if (vs == null) { sel.append(el("option", { value: "", textContent: "Loading qualities…" })); sel.disabled = true; }
      else if (!vs.length) { sel.append(el("option", { value: "", textContent: "Original (single quality)" })); sel.disabled = true; }
      else {
        sel.append(el("option", { value: "", textContent: "Best available" }));
        vs.forEach((v, i) => sel.append(el("option", { value: String(i), textContent: qLabel(v) })));
        sel.value = choice.get(it.url) ?? "";
        sel.onchange = () => choice.set(it.url, sel.value);
      }
      mid = sel;
    } else {  // direct file: show what the MP4 header says (resolution, length, size, sound)
      const bits = [];
      if (p === undefined || p === null) bits.push("Checking quality…");
      else if (p) {
        if (p.video) bits.push(Math.min(p.width, p.height) + "p"); else if (p.audio) bits.push("Audio only");
        if (p.duration) bits.push(fmtDur(p.duration));
      }
      const size = (p && p.size) || it.size;
      if (size) bits.push(fmtSize(size));
      if (p && p.video && !p.audio) bits.push(partner ? "+ sound" : "no sound");
      mid = el("div", { className: "meta", textContent: bits.join(" · ") || "Direct file", title: p && p.video ? `${p.width}×${p.height}` : "" });
    }

    dl.onclick = async () => {
      const v = sel && sel.value !== "" && vs ? vs[+sel.value] : null;
      const eff = v || (vs && vs.length ? vs[0] : null);  // "Best available" is the first (highest) one
      const q = isHls ? (eff && eff.height ? eff.height + "p" : "") : (p && p.video ? Math.min(p.width, p.height) + "p" : "");
      const base = [safeName(nameBox.value) || "video", q].filter(Boolean).join(" ");
      dl.disabled = true; dl.textContent = "Sending…";
      const r = await send({ cmd: "send", job: {
        url: isHls ? it.url : (p && p.useUrl) || it.url, referer: it.page || location.href, kind: isHls ? "hls" : undefined,
        audioUrl: mix && mix.checked ? (probes.get(partner.x.url)?.useUrl || partner.x.url) : undefined,
        filename: isHls ? base : base + "." + (mix && mix.checked ? "mp4" : p && p.audio && !p.video ? "m4a" : fileExt(it.url)),
        quality: v?.height || 0, bandwidth: v?.bandwidth || 0 } });
      if (r?.ok) { dl.textContent = "Sent ✔"; setStatus("Sent to OpenDM" + (isHls ? (v ? " (" + qLabel(v) + ")" : " (best quality)") : q ? " (" + q + (mix && mix.checked ? ", with sound" : "") + ")" : "")); }
      else { dl.disabled = false; dl.textContent = "Download"; setStatus(errorHint(r?.error), true); }
    };
    return el("div", { className: "row" },
      el("div", { className: "t" }, nameBox, el("span", { className: "chip", textContent: isHls ? "HLS" : extOf(it.url) })),
      ...(mix ? [el("label", { className: "mix" }, mix, "Add the sound (merges the separate audio track)")] : []),
      el("div", { className: "ctl" }, mid, dl));
  }

  function render() {
    if (!isTop) return;
    if (root.activeElement && ["SELECT", "INPUT"].includes(root.activeElement.tagName)) { setTimeout(render, 800); return; }  // don't interrupt typing or an open dropdown
    box.replaceChildren(); footEl = null;
    const list = shownItems();
    if (!expanded) {
      if (list.length) {
        const bubble = el("div", { className: "bubble", title: "OpenDM: videos detected on this page" },
          el("img", { src: ICON }), el("div", { className: "badge", textContent: String(list.length) }));
        enableDrag(bubble, () => { expanded = true; render(); });
        box.append(bubble);
      }
      return;
    }
    const head = el("div", { className: "head" }, el("img", { src: ICON, width: 18, height: 18 }), el("b", { textContent: "OpenDM Video Sniffer" }),
      el("button", { textContent: "–", title: "Minimize", onclick: () => { expanded = false; render(); } }),
      el("button", { textContent: "×", title: "Hide on this site (re-enable from the toolbar popup)", onclick: hideSite }));
    enableDrag(head);
    const body = el("div", { className: "body" });
    if (list.length) list.forEach((it) => body.append(row(it)));
    else body.append(el("div", { className: "empty", textContent: "No video detected yet. Start playing the video (switching its quality in the player can help) and it will appear here." }));
    footEl = el("div", { className: "foot", textContent: status.text || "Edit the name if you like, pick a quality, then press Download." });
    setStatus(status.text || "Edit the name if you like, pick a quality, then press Download.", status.err);
    box.append(el("div", { className: "panel" }, head, body, footEl));
  }

  function hideSite() {
    cfg.hiddenSites = [...new Set([...cfg.hiddenSites, location.hostname])];
    api.storage.local.set({ hiddenSites: cfg.hiddenSites });
    applyVisibility();
  }

  async function refresh() {
    if (!isTop) return;
    const r = await send({ cmd: "list" });
    items = Array.isArray(r) ? r : [];
    for (const it of items) {
      if (it.kind === "hls" && !variants.has(it.url)) {
        variants.set(it.url, null);
        send({ cmd: "variants", url: it.url }).then((v) => { variants.set(it.url, Array.isArray(v) ? v : []); render(); });
      }
    }
    for (const it of items) {
      if (it.kind === "file" && !probes.has(it.url)) {
        probes.set(it.url, null);
        send({ cmd: "probe", url: it.url }).then((r) => { probes.set(it.url, r || false); render(); });
      }
    }
    render();
  }
  const refreshSoon = () => { clearTimeout(refreshTimer); refreshTimer = setTimeout(refresh, 300); };

  function openPanel() { if (isTop) { expanded = true; refresh(); } else send({ cmd: "open-panel" }); }

  // ---------- "Download video" button over a hovered <video> (all frames) ----------
  let hoverVideo = null, hideTimer = 0, lastMove = 0;
  function hideHover() { hover.style.display = "none"; hoverVideo = null; }
  hover.addEventListener("mousedown", (e) => e.stopPropagation());
  hover.addEventListener("click", (e) => {
    e.stopPropagation(); e.preventDefault();
    const src = hoverVideo?.currentSrc || hoverVideo?.src || "";
    if (/^https?:/i.test(src)) send({ cmd: "found", url: src });
    hideHover(); openPanel();
  });
  window.addEventListener("mousemove", (e) => {
    const now = performance.now();
    if (now - lastMove < 120 || !visible()) return;
    lastMove = now;
    const path = e.composedPath ? e.composedPath() : [];
    if (path.includes(host)) { clearTimeout(hideTimer); return; }  // pointer is on our own button
    const v = path.find((n) => n.tagName === "VIDEO") || (document.elementsFromPoint?.(e.clientX, e.clientY) || []).find((n) => n.tagName === "VIDEO");
    const r = v?.getBoundingClientRect();
    clearTimeout(hideTimer);
    if (!v || r.width < 240 || r.height < 135) return hideHover();
    hoverVideo = v;
    hover.style.display = "flex";
    const w = hover.offsetWidth || 150;
    hover.style.left = clamp(r.right - w - 10, Math.max(r.left, 4), Math.max(4, innerWidth - w - 4)) + "px";
    hover.style.top = Math.max(r.top + 10, 6) + "px";
    hideTimer = setTimeout(hideHover, 2500);
  }, { capture: true, passive: true });

  // ---------- wiring ----------
  api.runtime.onMessage.addListener((m) => {
    if (!isTop) return;
    if (m?.cmd === "media-updated") refreshSoon();
    if (m?.cmd === "open-panel") { expanded = true; refresh(); }
  });
  api.storage.onChanged.addListener((ch) => {
    for (const k of ["floating", "hiddenSites"]) if (ch[k]) cfg[k] = ch[k].newValue ?? (k === "floating" ? true : []);
    applyVisibility(); render();
  });
  api.storage.local.get({ floating: true, hiddenSites: [], pos: null }).then((c) => {
    cfg = { floating: c.floating, hiddenSites: c.hiddenSites };
    if (c.pos) Object.assign(pos, { right: clamp(c.pos.right, 0, innerWidth - 60), bottom: clamp(c.pos.bottom, 0, innerHeight - 60) });
    applyPos(); applyVisibility(); refresh();
  });
})();
