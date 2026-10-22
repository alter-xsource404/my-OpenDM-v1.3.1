const assert = require("assert"), fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const code = fs.readFileSync(path.join(__dirname, "../../extension/content.js"), "utf8");
const dom = new JSDOM("<!doctype html><title>(2) My Clip - YouTube</title><body><video id=v></video></body>", { url: "https://site.test/watch", runScripts: "outside-only", pretendToBeVisual: true });
const w = dom.window, sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let shadow, storageSet = [], sentMsgs = [], listeners = {}, storageData = { floating: true, hiddenSites: [], pos: null };
const orig = w.Element.prototype.attachShadow;
w.Element.prototype.attachShadow = function (o) { return (shadow = orig.call(this, { mode: "open" })); };  // test-only: let us look inside
w.Element.prototype.setPointerCapture = () => {};
const P = "https://site.test/watch";
const ITEMS = [
  { url: "https://cdn.test/v/master.m3u8", kind: "hls", size: 0, page: P },
  { url: "https://cdn.test/v/mid/index.m3u8", kind: "hls", size: 0, page: P },      // child of the master -> hidden
  { url: "https://cdn.test/low.mp4", kind: "file", size: 0, page: P },
  { url: "https://cdn.test/vertical.mp4?sig=1", kind: "file", size: 0, page: P },
  { url: "https://cdn.test/init-0.m4s", kind: "file", size: 0, page: P },          // stream fragment -> hidden
  { url: "https://cdn.test/song.m4a", kind: "file", size: 0, page: P },
  { url: "https://cdn.test/voice.m4a", kind: "file", size: 0, page: P }];   // 12.3 s: the sound track that belongs to vertical.mp4
const VARS = [{ height: 720, bandwidth: 2800000, fps: 60, url: "https://cdn.test/v/mid/index.m3u8" }, { height: 360, bandwidth: 900000, fps: 0, url: "https://cdn.test/v/low/index.m3u8" }];
const PROBES = {
  "https://cdn.test/low.mp4": { video: true, audio: true, width: 640, height: 360, duration: 65, size: 3145728, segment: false, useUrl: "https://cdn.test/low.mp4" },
  "https://cdn.test/vertical.mp4?sig=1": { video: true, audio: false, width: 720, height: 1280, duration: 12, size: 5242880, segment: false, useUrl: "https://cdn.test/vertical.mp4?sig=1" },
  "https://cdn.test/init-0.m4s": { video: false, audio: false, width: 0, height: 0, duration: 0, size: 900, segment: true },
  "https://cdn.test/song.m4a": { video: false, audio: true, width: 0, height: 0, duration: 200, size: 4000000, segment: false, useUrl: "https://cdn.test/song.m4a" },
  "https://cdn.test/voice.m4a": { video: false, audio: true, width: 0, height: 0, duration: 12.3, size: 1048576, segment: false, useUrl: "https://cdn.test/voice.m4a?clean" } };
w.chrome = {
  runtime: { onMessage: { addListener: (f) => (listeners.msg = f) },
    sendMessage: async (m) => { sentMsgs.push(m); if (m.cmd === "list") return ITEMS; if (m.cmd === "variants") return m.url.endsWith("master.m3u8") ? VARS : []; if (m.cmd === "probe") return PROBES[m.url] || null; return { ok: true }; } },
  storage: { onChanged: { addListener: (f) => (listeners.chg = f) }, local: { get: async () => storageData, set: async (o) => storageSet.push(o) } },
};
const q = (s) => shadow.querySelector(s), qa = (s) => [...shadow.querySelectorAll(s)];
const fire = (t, type, init = {}) => t.dispatchEvent(new w.MouseEvent(type, { bubbles: true, button: 0, ...init }));
const lastJob = () => sentMsgs.filter((m) => m.cmd === "send").pop().job;
const rowWith = (txt) => qa(".row").find((r) => r.textContent.includes(txt));
(async () => {
  w.eval(code); await sleep(200);
  assert.strictEqual(q(".badge").textContent, "5"); console.log("PASS bubble counts 5 entries (child playlist and stream fragment are hidden)");
  const b = q(".bubble"); fire(b, "pointerdown", { clientX: 5, clientY: 5 }); fire(b, "pointerup"); await sleep(50);
  const rows = qa(".row"); assert.strictEqual(rows.length, 5);
  const labels = rows.map((r) => r.querySelector(".meta, select").tagName === "SELECT" ? "HLS" : r.querySelector(".meta").textContent);
  assert.deepStrictEqual(labels, ["HLS", "720p · 0:12 · 5.0 MB · + sound", "360p · 1:05 · 3.0 MB", "Audio only · 0:12 · 1.0 MB", "Audio only · 3:20 · 3.8 MB"]);
  console.log("PASS rows sorted best-first, each labelled with its real quality:\n      " + labels.join("\n      "));
  const names = rows.map((r) => r.querySelector(".name").value); assert(names.every((n) => n === "My Clip"), names);
  console.log("PASS every name box is pre-filled with the video's title, cleaned up (\"(2) My Clip - YouTube\" -> \"My Clip\")");
  const sel = rows[0].querySelector("select");
  assert.deepStrictEqual([...sel.options].map((o) => o.textContent), ["Best available", "720p60 · 2.8 Mbps", "360p · 900 kbps"]); console.log("PASS HLS quality dropdown still lists every rendition");

  rows[0].querySelector(".dl").onclick(); await sleep(40);
  let j = lastJob(); assert.deepStrictEqual([j.url, j.kind, j.filename, j.quality, j.bandwidth], ["https://cdn.test/v/master.m3u8", "hls", "My Clip 720p", 0, 0]);
  console.log("PASS HLS 'Best available' -> file name carries the real best height:", JSON.stringify(j.filename));
  sel.value = "1"; sel.onchange(); rows[0].querySelector(".dl").onclick(); await sleep(40);
  j = lastJob(); assert.deepStrictEqual([j.filename, j.quality, j.bandwidth], ["My Clip 360p", 360, 900000]); console.log("PASS HLS 360p chosen -> quality=360, bandwidth=900000, name \"My Clip 360p\"");

  const vrow = rowWith("+ sound"); const nb = vrow.querySelector(".name"); const mix = vrow.querySelector(".mix input");
  assert(mix && mix.checked); assert(!rowWith("360p").querySelector(".mix"), "a video that already has sound gets no checkbox");
  nb.value = "Holiday: Rome?"; nb.dispatchEvent(new w.Event("input")); vrow.querySelector(".dl").onclick(); await sleep(40);
  j = lastJob(); assert.deepStrictEqual([j.url, j.audioUrl, j.filename, j.kind], ["https://cdn.test/vertical.mp4?sig=1", "https://cdn.test/voice.m4a?clean", "Holiday- Rome 720p.mp4", undefined]);
  console.log("PASS silent video is paired with the audio of the same length (not the 3-minute song); job carries both URLs:", JSON.stringify(j.filename));
  mix.checked = false; mix.onchange(); vrow.querySelector(".dl").disabled = false; vrow.querySelector(".dl").onclick(); await sleep(40);
  assert.strictEqual(lastJob().audioUrl, undefined); console.log("PASS unchecking 'Add the sound' sends the video alone");
  rowWith("Audio only").querySelector(".dl").onclick(); await sleep(40);
  assert.strictEqual(lastJob().filename, "My Clip.m4a"); console.log("PASS audio-only file is saved as .m4a");

  // hover button + settings (unchanged behaviour)
  const v = w.document.getElementById("v"); v.getBoundingClientRect = () => ({ left: 100, top: 100, right: 740, bottom: 460, width: 640, height: 360 });
  Object.defineProperty(v, "currentSrc", { value: "https://cdn.test/direct.mp4" });
  await sleep(200); fire(v, "mousemove", { clientX: 300, clientY: 300 }); assert.strictEqual(q(".hover").style.display, "flex");
  q(".hover").click(); await sleep(50); assert(sentMsgs.some((m) => m.cmd === "found" && m.url === "https://cdn.test/direct.mp4")); console.log("PASS hover button over a large <video> reports its source and opens the panel");
  v.getBoundingClientRect = () => ({ left: 0, top: 0, right: 100, bottom: 60, width: 100, height: 60 }); await sleep(150); fire(v, "mousemove");
  assert.strictEqual(q(".hover").style.display, "none"); console.log("PASS tiny videos (ads/thumbnails) get no button");
  const host = () => w.document.documentElement.lastElementChild;
  listeners.chg({ floating: { newValue: false } }); assert.strictEqual(host().style.display, "none");
  listeners.chg({ floating: { newValue: true } }); assert.strictEqual(host().style.display, "");
  [...qa(".head button")].find((x) => x.title.startsWith("Hide")).click();
  assert.strictEqual(JSON.stringify(storageSet.pop()), JSON.stringify({ hiddenSites: ["site.test"] })); assert.strictEqual(host().style.display, "none");
  console.log("PASS popup toggle and the x button hide/show the panel");
  assert(!/innerHTML/.test(code)); console.log("PASS no innerHTML anywhere in content.js");
})().catch((e) => { console.error("FAIL", e.message); process.exit(1); });
