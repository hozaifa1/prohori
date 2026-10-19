/* Prohori PWA: vanilla JS, no dependencies. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MIN_PX_PER_MM = 8;
  const MIN_BLUR_VAR = 150;
  const MAX_TILT_DEG = 45;
  const ICONS = "/static/icons.svg#i-";

  const ACTIONS = {
    reshoot_steadier: { title: "Hold steadier", tone: "warn", icon: "hand-palm" },
    move_closer: { title: "Move closer", tone: "warn", icon: "arrows-in" },
    relight: { title: "Fix the lighting", tone: "warn", icon: "sun" },
    reposition_marker: { title: "Reposition the board", tone: "warn", icon: "crosshair" },
    accept_with_widened_uncertainty: { title: "Accept, wider uncertainty", tone: "ok", icon: "check-circle" },
    accept: { title: "Accept", tone: "ok", icon: "seal-check" },
    abandon_and_log: { title: "Abandon and log", tone: "bad", icon: "prohibit" },
  };

  const REASONS = {
    low_resolution: `Board resolution too low (need at least ${MIN_PX_PER_MM} px/mm)`,
    too_few_corners: "Too few board corners found",
    blurry: "Image too blurry",
    glare: "Too much glare",
    oblique: "Camera angle too steep",
  };
  const reasonText = (r) => REASONS[r] || String(r).replace(/_/g, " ");
  const ERRORS = {
    board_not_found: "Calibration board not found in this frame",
  };
  const errorText = (e) => ERRORS[e] || String(e).replace(/_/g, " ");

  const state = {
    sessionId: null,
    stream: null,
    busy: false,
    view: "capture",
    cracks: [],
    sel: 0,
    certified: false,
  };

  // ---------------------------------------------------------------- helpers
  function h(tag, props, ...kids) {
    const e = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === "class") e.className = v;
        else if (k === "text") e.textContent = v;
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else e.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return e;
  }
  const SVGNS = "http://www.w3.org/2000/svg";
  function icon(name, cls) {
    const s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("class", "ic" + (cls ? " " + cls : ""));
    s.setAttribute("aria-hidden", "true");
    const u = document.createElementNS(SVGNS, "use");
    u.setAttribute("href", ICONS + name);
    s.append(u);
    return s;
  }
  // keep a value and its unit on one line ("0.38 mm")
  const nb = (t) => String(t).replace(/(\d) (mm|px\/mm|ms)(?![a-z])/g, "$1 $2");
  // server rationales mention gate codes like low_resolution: show them as words
  const words = (t) => String(t).replace(/([a-z])_(?=[a-z])/g, "$1 ");
  const num = (x) => typeof x === "number" && isFinite(x);
  const fmt = (x, d = 2) => (num(x) ? x.toFixed(d) : "n/a");
  const fmtMs = (x) => (x < 10 ? x.toFixed(2) : String(Math.round(x)));
  const pref = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  let toastTimer = null;
  function toast(msg, ms = 6000) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, ms);
  }

  function setView(v) {
    state.view = v;
    $("view-capture").hidden = v !== "capture";
    $("view-result").hidden = v !== "result";
    window.scrollTo({ top: 0 });
    if (v === "capture") startCamera(); else stopCamera();
  }

  // ----------------------------------------------------------------- camera
  const video = $("cam");

  function camMessage(title, detail, withRetry) {
    const box = $("cam-msg");
    box.replaceChildren(
      h("strong", { text: title }),
      h("span", { text: detail }),
      withRetry ? h("button", { class: "btn small", type: "button", onclick: startCamera, text: "Try the camera again" }) : null
    );
    box.hidden = false;
    $("stage-tip").hidden = true;
  }

  async function startCamera() {
    if (state.stream || state.view !== "capture") return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camMessage("Camera unavailable here",
        window.isSecureContext ? "This browser has no camera API. Use Upload photo below." : "Phones only allow the camera over HTTPS. Use Upload photo below.");
      return;
    }
    let stream = null;
    try {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 } },
          audio: false,
        });
      } catch (e) {
        if (e && (e.name === "OverconstrainedError" || e.name === "NotFoundError")) {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } else { throw e; }
      }
    } catch (e) {
      const denied = e && (e.name === "NotAllowedError" || e.name === "SecurityError");
      camMessage(denied ? "Camera permission needed" : "Could not start the camera",
        denied ? "Allow camera access in the browser, or use Upload photo below." : "Use Upload photo below, or try again.", true);
      return;
    }
    if (state.view !== "capture") { stream.getTracks().forEach((t) => t.stop()); return; }
    state.stream = stream;
    video.srcObject = stream;
    $("cam-msg").hidden = true;
    $("stage-tip").hidden = false;
    try {
      const track = stream.getVideoTracks()[0];
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      if (caps.focusMode && caps.focusMode.includes("continuous")) {
        await track.applyConstraints({ advanced: [{ focusMode: "continuous" }] });
      }
    } catch { /* optional */ }
    video.play().catch(() => {});
  }

  function stopCamera() {
    if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
    video.srcObject = null;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopCamera(); else if (state.view === "capture") startCamera();
  });

  function captureFrame() {
    return new Promise((resolve, reject) => {
      if (!state.stream || !video.videoWidth) { reject(new Error("The camera is not ready yet. Use Upload photo instead.")); return; }
      const c = document.createElement("canvas");
      c.width = video.videoWidth; c.height = video.videoHeight;
      c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
      c.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not capture a frame."))), "image/jpeg", 0.92);
    });
  }

  // Huge gallery photos: shrink client-side so we stay under the server limit.
  async function shrinkIfHuge(file) {
    if (file.size <= 14 * 1024 * 1024) return file;
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const s = Math.min(1, 4096 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("Image too large."))), "image/jpeg", 0.9));
  }

  // ---------------------------------------------------------------- measure
  function setBusy(on, sub) {
    state.busy = on;
    $("busy").hidden = !on;
    if (sub) $("busy-sub").textContent = sub;
    $("btn-shutter").disabled = on;
  }

  async function measure(blob, name) {
    if (state.busy) return;
    setBusy(true, "Uploading frame");
    const t0 = performance.now();
    const tick = setInterval(() => {
      const s = ((performance.now() - t0) / 1000).toFixed(1);
      $("busy-sub").textContent = `Analysing on server, ${s} s`;
    }, 100);
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), 90000);
    try {
      const body = new FormData();
      body.append("image", blob, name || "frame.jpg");
      if (state.sessionId) body.append("session_id", state.sessionId);
      body.append("policy", $("policy").value);
      const r = await fetch("/api/measure", { method: "POST", body, signal: ctrl.signal });
      let data = null;
      try { data = await r.json(); } catch { /* non-JSON error */ }
      if (!r.ok) throw new Error((data && data.detail) || `Server error ${r.status}`);
      state.sessionId = data.session_id;
      const roundTrip = performance.now() - t0;
      render(data, roundTrip);
      setView("result");
      loadTrace(data.session_id, data.step);
    } catch (e) {
      const msg = e.name === "AbortError" ? "The server took too long. Try again." : (e.message || "Request failed");
      toast(msg);
    } finally {
      clearInterval(tick); clearTimeout(to);
      setBusy(false);
    }
  }

  // ----------------------------------------------------------------- render
  function actionInfo(a) {
    return ACTIONS[a] || { title: (a || "Unknown").replace(/_/g, " "), tone: "info", icon: "info" };
  }

  // One quality gauge. The gate's own reasons are authoritative; thresholds are the fallback.
  function gauge(label, value, unit, note, fail) {
    return h("div", { class: "gauge" + (fail ? " fail" : "") },
      h("div", { class: "gauge-top" }, h("span", { text: label }), icon(fail ? "warning" : "check-circle")),
      h("div", { class: "gauge-v" }, value, unit ? h("small", { text: unit }) : null),
      note ? h("div", { class: "gauge-n", text: note }) : null);
  }

  function renderGauges(obs, reasons) {
    const box = $("chips");
    box.replaceChildren();
    if (!obs) return;
    const has = (r) => reasons.includes(r);
    if (num(obs.corners)) box.append(gauge("Board corners", String(obs.corners), `/${obs.corners_total ?? "?"}`, null, has("too_few_corners")));
    if (num(obs.px_per_mm)) box.append(gauge("Scale", fmt(obs.px_per_mm, 1), "px/mm", `need ${MIN_PX_PER_MM} or more`, has("low_resolution") || obs.px_per_mm < MIN_PX_PER_MM));
    if (num(obs.blur_var)) box.append(gauge("Sharpness", fmt(obs.blur_var, 0), null, `need ${MIN_BLUR_VAR} or more`, has("blurry")));
    if (num(obs.obliquity_deg)) box.append(gauge("Tilt", fmt(obs.obliquity_deg, 0), "°", `max ${MAX_TILT_DEG}°`, has("oblique")));
    if (num(obs.glare_frac)) box.append(gauge("Glare", fmt(obs.glare_frac * 100, 0), "%", "lower is better", has("glare")));
  }

  function renderHero(animate) {
    const hero = $("hero");
    const c = state.cracks[state.sel];
    const cert = state.certified;
    hero.replaceChildren();
    const badge = h("span", { class: "badge " + (cert ? "ok" : "warn") },
      icon(cert ? "seal-check" : "warning"), cert ? "Certified" : "Not certified");
    if (!c) {
      hero.append(
        h("div", { class: "hero-top" }, h("span", { class: "hero-id", text: "No measurement" }), badge),
        h("div", { class: "hero-num" }, h("span", { class: "n none", text: "No reading" })));
      return;
    }
    const sub = [];
    if (num(c.true_width_mm)) {
      const delta = num(c.width_mm) ? c.width_mm - c.true_width_mm : null;
      sub.push(h("span", null, "Ground truth ", h("b", { text: `${fmt(c.true_width_mm)} mm` }),
        delta != null ? h("b", { text: ` (${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(2)})` }) : null));
    }
    if (num(c.length_mm)) sub.push(h("span", null, "Length ", h("b", { text: `${fmt(c.length_mm, 1)} mm` })));
    hero.append(
      h("div", { class: "hero-top" }, h("span", { class: "hero-id", text: `Crack ${c.id ?? ""}`.trim() }), badge),
      h("div", { class: "hero-num" },
        num(c.width_mm)
          ? [h("span", { class: "n", text: fmt(c.width_mm) }), h("span", { class: "u", text: "mm" })]
          : h("span", { class: "n none", text: "n/a" })),
      num(c.uncertainty_mm)
        ? h("div", { class: "hero-pm" }, h("span", { class: "pm", text: `± ${fmt(c.uncertainty_mm)}` }), h("span", { class: "pm-note", text: "mm uncertainty" }))
        : null,
      sub.length ? h("div", { class: "hero-sub" }, sub) : null);
    if (animate) {
      hero.classList.remove("swap");
      void hero.offsetWidth;
      hero.classList.add("swap");
    }
  }

  function renderPicker() {
    const box = $("cracks");
    box.replaceChildren();
    if (state.cracks.length < 2) return;
    state.cracks.forEach((c, i) => {
      box.append(h("button", {
        class: "tile", type: "button", "aria-pressed": i === state.sel ? "true" : "false",
        "aria-label": `Crack ${c.id}: ${fmt(c.width_mm)} millimetres`,
        onclick: () => { state.sel = i; renderPicker(); renderHero(true); },
      },
      h("span", { class: "tile-id", text: String(c.id ?? i + 1) }),
      h("span", { class: "tile-w", text: fmt(c.width_mm) }),
      h("span", { class: "tile-u", text: num(c.uncertainty_mm) ? `±${fmt(c.uncertainty_mm)}` : "" })));
    });
  }

  function metaSpan(label, value) {
    return h("span", null, label ? label + " " : "", h("b", { text: value }));
  }

  function render(data, roundTripMs) {
    const m = data.measurement || {};
    const d = data.decision || {};
    const gate = m.gate || {};
    const reasons = Array.isArray(gate.reasons) ? gate.reasons : [];
    const info = actionInfo(d.action);

    // agent banner
    const banner = $("banner");
    banner.className = "banner " + info.tone;
    $("banner-action").textContent = info.title;
    $("banner-icon").setAttribute("href", ICONS + info.icon);
    $("banner-step").textContent = num(data.step) ? `Step ${data.step + 1}` : "";
    $("banner-text").textContent = nb(d.instruction || "No instruction returned.");
    $("banner-why").textContent = words(d.rationale || "");
    $("banner-why").hidden = !d.rationale;
    const meta = $("banner-meta");
    meta.replaceChildren(metaSpan("policy", d.policy || "n/a"));
    if (d.model) meta.append(metaSpan("model", d.model));
    if (num(d.latency_ms)) meta.append(metaSpan("agent", `${fmtMs(d.latency_ms)} ms`));
    meta.append(metaSpan("server", `${Math.round(data.server_ms)} ms`), metaSpan("round trip", `${(roundTripMs / 1000).toFixed(1)} s`));

    // overlay
    const wrap = $("overlay-wrap");
    wrap.classList.remove("zoom");
    $("overlay-img").src = "data:image/jpeg;base64," + data.overlay_jpeg_b64;

    renderGauges(m.observation, reasons);

    // gate: only what needs attention
    const g = $("gate");
    g.replaceChildren();
    if (m.error) {
      g.append(h("div", { class: "reason bad" }, icon("x-circle"),
        h("div", null, errorText(m.error), h("small", { text: String(m.error) }))));
    }
    if (gate.certified === false) {
      for (const r of reasons) {
        if (m.error && r === "too_few_corners") continue;
        g.append(h("div", { class: "reason" }, icon("warning"), h("div", null, reasonText(r))));
      }
    }

    // measurements
    state.cracks = Array.isArray(m.cracks) ? m.cracks : [];
    state.sel = 0;
    state.certified = gate.certified === true && !m.error;
    renderHero(false);
    renderPicker();
  }

  // ------------------------------------------------------------------ trace
  function hhmmss(iso) {
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleTimeString([], { hour12: false });
  }

  // goodDir: which direction is an improvement for this signal (+1 up, -1 down)
  function ochip(label, value, cur, prev, dec, unit, goodDir, fail) {
    const parts = [label, h("b", { text: value })];
    if (prev != null && num(cur) && num(prev) && Math.abs(cur - prev) >= Math.pow(10, -dec)) {
      const diff = cur - prev;
      const better = goodDir > 0 ? diff > 0 : diff < 0;
      parts.push(h("span", { class: "d " + (better ? "good" : fail ? "worse" : "flat"), text: `${diff > 0 ? "+" : "−"}${Math.abs(diff).toFixed(dec)}${unit || ""}` }));
    }
    return h("span", { class: "ochip" + (fail ? " fail" : "") }, parts);
  }

  function renderTrace(steps, curStep) {
    const list = $("trace");
    list.replaceChildren();
    $("trace-count").textContent = steps.length ? `${steps.length} step${steps.length === 1 ? "" : "s"}` : "";
    if (!steps.length) { list.append(h("li", { class: "trace-empty", text: "No steps recorded yet." })); return; }
    steps.forEach((s, i) => {
      const prev = i > 0 ? (steps[i - 1].observation || {}) : null;
      const o = s.observation || {};
      const d = s.decision || {};
      const info = actionInfo(d.action || s.action);
      const reasons = (s.gate && Array.isArray(s.gate.reasons)) ? s.gate.reasons : [];
      const has = (r) => reasons.includes(r);
      const idx = s.step ?? i;

      // meta line: when, which policy, how long
      const meta = h("div", { class: "step-meta" });
      if (idx === curStep) meta.append(h("span", { class: "now", text: "latest" }));
      meta.append(h("span", null, h("b", { text: `Step ${i + 1}` }), s.ts ? ` ${hhmmss(s.ts)}` : ""));
      meta.append(metaSpan("policy", d.policy || s.policy_requested || "n/a"));
      if (d.model) meta.append(metaSpan("model", d.model));
      const vis = s.timing_ms && num(s.timing_ms.total) ? s.timing_ms.total : s.server_ms;
      if (num(vis)) meta.append(metaSpan("vision", `${Math.round(vis)} ms`));
      if (num(d.latency_ms)) meta.append(metaSpan("agent", `${fmtMs(d.latency_ms)} ms`));
      if (num(d.input_tokens) || num(d.output_tokens)) meta.append(metaSpan("tokens", `${d.input_tokens ?? 0} in / ${d.output_tokens ?? 0} out`));
      if (d.fallback_reason) meta.append(h("span", { class: "fb", text: `fallback: ${String(d.fallback_reason).replace(/_/g, " ")}` }));

      // what vision saw (with change since the previous step)
      const obs = h("div", { class: "step-obs" });
      const p = prev;
      if (num(o.corners)) obs.append(ochip("corners", `${o.corners}/${o.corners_total ?? "?"}`, o.corners, p && p.corners, 0, "", 1, has("too_few_corners")));
      if (num(o.px_per_mm)) obs.append(ochip("scale", `${fmt(o.px_per_mm, 1)} px/mm`, o.px_per_mm, p && p.px_per_mm, 1, "", 1, has("low_resolution")));
      if (num(o.blur_var)) obs.append(ochip("sharpness", fmt(o.blur_var, 0), o.blur_var, p && p.blur_var, 0, "", 1, has("blurry")));
      if (num(o.obliquity_deg)) obs.append(ochip("tilt", `${fmt(o.obliquity_deg, 0)}°`, o.obliquity_deg, p && p.obliquity_deg, 0, "°", -1, has("oblique")));
      if (num(o.glare_frac) && o.glare_frac > 0) obs.append(ochip("glare", `${fmt(o.glare_frac * 100, 0)}%`, o.glare_frac, p && p.glare_frac, 2, "", -1, has("glare")));
      const first = (s.cracks || [])[0];
      if (first && num(first.width_mm)) obs.append(h("span", { class: "ochip" }, `${first.id ?? "width"}`, h("b", { text: `${fmt(first.width_mm)} mm` })));
      obs.append(h("span", { class: "ochip" + (s.gate && s.gate.certified ? "" : " fail") }, "gate", h("b", { text: s.gate && s.gate.certified ? "certified" : "not certified" })));

      // what the agent decided
      const act = h("div", { class: "act " + (info.tone === "info" ? "" : info.tone) },
        h("div", { class: "act-head" }, icon(info.icon), h("span", { text: info.title }),
          h("span", { class: "act-code", text: d.action || s.action || "" })),
        h("div", { class: "act-instr", text: nb(d.instruction || "") }),
        d.rationale ? h("div", { class: "act-why", text: words(d.rationale) }) : null);

      list.append(h("li", { class: "step" + (idx === curStep ? " cur" : "") },
        h("div", { class: "step-n", text: String(i + 1) }),
        h("div", { class: "step-body" }, meta, obs, icon("arrow-right", "flow"), act)));
    });
  }

  async function loadTrace(sid, curStep) {
    try {
      const r = await fetch("/api/trace/" + encodeURIComponent(sid), { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      renderTrace(await r.json(), curStep);
    } catch {
      $("trace").replaceChildren(h("li", { class: "trace-empty", text: "Trace unavailable." }));
    }
  }

  // ---------------------------------------------------------------- samples
  let samplesLoaded = false;
  async function openSamples() {
    const dlg = $("samples");
    if (!samplesLoaded) {
      try {
        const r = await fetch("/api/samples");
        const list = await r.json();
        $("sample-list").replaceChildren(...list.map((s) => h("button", {
          class: "sample", type: "button",
          onclick: () => runSample(s),
        }, h("img", { src: s.url, alt: "" }), h("div", null, h("b", { text: s.label }), h("span", { text: s.note || "" })))));
        samplesLoaded = true;
      } catch { toast("Could not load the samples."); return; }
    }
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
  }

  async function runSample(s) {
    const dlg = $("samples");
    if (dlg.close) dlg.close(); else dlg.removeAttribute("open");
    try {
      const r = await fetch(s.url);
      if (!r.ok) throw new Error("sample missing");
      await measure(await r.blob(), `${s.id}.jpg`);
    } catch (e) { toast(e.message || "Could not load the sample."); }
  }

  // ----------------------------------------------------------------- wiring
  async function handleFile(input) {
    const f = input.files && input.files[0];
    input.value = "";
    if (!f) return;
    try { await measure(await shrinkIfHuge(f), f.name || "photo.jpg"); }
    catch (e) { toast(e.message || "Could not read that photo."); }
  }

  function newInspection() {
    state.sessionId = null;
    $("trace").replaceChildren();
    $("trace-count").textContent = "";
    setView("capture");
  }

  $("btn-shutter").addEventListener("click", async () => {
    if (state.busy) return;
    try { await measure(await captureFrame(), "frame.jpg"); }
    catch (e) { toast(e.message || "Capture failed."); }
  });
  $("file-cam").addEventListener("change", (e) => handleFile(e.target));
  $("file-gallery").addEventListener("change", (e) => handleFile(e.target));
  $("btn-demo").addEventListener("click", openSamples);
  $("btn-new").addEventListener("click", newInspection);
  $("btn-retake").addEventListener("click", () => setView("capture"));
  $("overlay-img").addEventListener("click", () => $("overlay-wrap").classList.toggle("zoom"));
  $("policy").value = pref.get("prohori.policy", "rules");
  $("policy").addEventListener("change", (e) => pref.set("prohori.policy", e.target.value));

  fetch("/health").then((r) => r.json()).then((j) => {
    const foot = $("foot");
    foot.replaceChildren(...[j.arch, j.instance, j.opencv ? `OpenCV ${j.opencv}` : null, j.version ? `build ${j.version}` : null]
      .filter(Boolean).map((t) => h("span", { text: t })));
  }).catch(() => { $("foot").textContent = "server unreachable"; });

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  setView("capture");
})();
