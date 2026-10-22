const api = globalThis.browser ?? globalThis.chrome;
const sess = api.storage.session ?? api.storage.local;
const $ = (id) => document.getElementById(id);
(async () => {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  let host = ""; try { host = new URL(tab.url).hostname; } catch {}
  const c = await api.storage.local.get({ intercept: true, floating: true, hiddenSites: [] });
  $("on").checked = c.intercept; $("float").checked = c.floating;
  $("host").textContent = host || "this page"; $("site").checked = !c.hiddenSites.includes(host); $("site").disabled = !host;
  $("on").onchange = (e) => api.storage.local.set({ intercept: e.target.checked });
  $("float").onchange = (e) => api.storage.local.set({ floating: e.target.checked });
  $("site").onchange = async (e) => {
    const cur = (await api.storage.local.get({ hiddenSites: [] })).hiddenSites.filter((h) => h !== host);
    api.storage.local.set({ hiddenSites: e.target.checked ? cur : [...cur, host] });
  };
  const key = "media:" + tab.id, n = ((await sess.get(key))[key] ?? []).length;
  $("count").textContent = n ? `${n} video${n > 1 ? "s" : ""} detected on this page.` : "No video detected yet. Press play on the video.";
  $("open").onclick = async () => {
    try { await api.tabs.sendMessage(tab.id, { cmd: "open-panel" }, { frameId: 0 }); window.close(); }
    catch { $("count").textContent = "The panel can't run on this page (browser pages, the web store, or a page opened before the extension was installed - reload it)."; }
  };
  api.runtime.sendMessage({ cmd: "status" }).then((s) => {
    $("conn").textContent = s?.mode === "native" || s?.mode === "manual" ? "OpenDM: connected \u2714" + (s.mode === "native" && !s.running ? " (starts when needed)" : "")
      : "OpenDM: not connected. Open OpenDM once to set it up.";
  }).catch(() => {});
  $("opt").onclick = () => { api.runtime.openOptionsPage(); window.close(); };
})();
