/* Prohori PWA: vanilla JS, no dependencies. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MIN_PX_PER_MM = 8;
  const MIN_BLUR_VAR = 150;
  const MAX_TILT_DEG = 45;
  const ICONS = "/static/icons.svg#i-";
  // Printed ChArUco board: 7 x 5 squares of 20 mm = 140 x 100 mm (src/prohori/board.py).
  const BOARD_LONG_MM = 140;
  const BOARD_SHORT_MM = 100;
  const MAX_BOARD_FILL = 0.6; // a board filling more than this share of the frame leaves no room for the crack
  const JOINT_RE = /^[A-Za-z0-9_-]{1,64}$/;

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
  // Reason codes of the deployed (conformal) gate, in plain words (mirrors REASON_SHORT in src/prohori/agent.py).
  // The deployed gate has no single-number thresholds, so none are quoted here.
  const CRC_REASONS = {
    too_few_corners: "Board not fully seen", low_resolution: "Too far for this crack's width", blurry: "Picture is soft",
    oblique: "Angle too steep", glare: "Glare", noisy: "Grainy picture", low_coverage: "Crack partly out of view",
    unstable_width: "Width readings not stable", mask_blowup: "Outline smeared", mask_holes: "Outline has holes",
    mask_fragmented: "Outline broken up", low_confidence: "Not enough confidence", invalid_image: "Unreadable image",
  };
  const isCrc = (gate) => !!gate && typeof gate.mode === "string" && gate.mode.startsWith("crc");
  const reasonText = (r, crc) => (crc && CRC_REASONS[r]) || REASONS[r] || String(r).replace(/_/g, " ");
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
    crc: false,         // the deployed per-crack gate (cracks carry certified/status/interval_mm)
    cam: null,          // {w, h, photoW, photoH} from the live track
    imageCapture: null,
    lastCapture: null,  // {live, w, h, via} of the frame that was just sent
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
    const track = stream.getVideoTracks()[0];
    try {
      const st = track.getSettings ? track.getSettings() : {};
      state.cam = { w: st.width || 0, h: st.height || 0, photoW: 0, photoH: 0 };
      console.info("[prohori] getUserMedia track settings", JSON.stringify(st));
      showCamInfo();
    } catch { /* optional */ }
    try {
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      if (caps.focusMode && caps.focusMode.includes("continuous")) {
        await track.applyConstraints({ advanced: [{ focusMode: "continuous" }] });
      }
    } catch { /* optional */ }
    // ImageCapture.takePhoto() gives the full sensor resolution (the video stream is usually 720p-1080p).
    try {
      if (typeof ImageCapture === "function") {
        state.imageCapture = new ImageCapture(track);
        state.imageCapture.getPhotoCapabilities().then((pc) => {
          const w = pc.imageWidth && pc.imageWidth.max, h = pc.imageHeight && pc.imageHeight.max;
          if (state.cam && w && h) {
            state.cam.photoW = w; state.cam.photoH = h;
            console.info("[prohori] photo capabilities (max)", w, "x", h);
            showCamInfo();
          }
        }).catch(() => {});
      }
    } catch { state.imageCapture = null; }
    video.play().catch(() => {});
  }

  function stopCamera() {
    if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
    video.srcObject = null;
    state.imageCapture = null;
  }

  // Would a frame of w x h plausibly reach the 8 px/mm gate? Estimate: the board must fill most of the frame.
  function tooSmallToCertify(w, h) {
    if (!w || !h) return false;
    const long = Math.max(w, h), short = Math.min(w, h);
    const fill = Math.max(MIN_PX_PER_MM * BOARD_LONG_MM / long, MIN_PX_PER_MM * BOARD_SHORT_MM / short);
    return fill > MAX_BOARD_FILL;
  }
  const smallHint = (w, h) => `Live camera is ${w}×${h} — for the sharpest result use Upload photo (native camera)`;

  // Small mono line under the viewfinder: what the browser really gave us (and a gentle hint if it is too little).
  function showCamInfo(captured) {
    const info = $("cam-info"), hint = $("cam-hint");
    const c = state.cam;
    if (!c || !c.w) { info.hidden = true; hint.hidden = true; return; }
    const parts = [`Live camera ${c.w}×${c.h}`];
    if (c.photoW) parts.push(`photo up to ${c.photoW}×${c.photoH}`);
    if (captured) parts.push(`last shot ${captured.w}×${captured.h} via ${captured.via}`);
    info.textContent = parts.join(" · ");
    info.hidden = false;
    // what a shutter press would produce: the still (if takePhoto works) or the video frame
    const w = captured ? captured.w : (c.photoW || c.w), h = captured ? captured.h : (c.photoH || c.h);
    const small = tooSmallToCertify(w, h);
    hint.textContent = small ? smallHint(w, h) : "";
    hint.hidden = !small;
  }

  function blobToJpeg(canvas, q) {
    return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not capture a frame."))), "image/jpeg", q));
  }

  async function bitmapSize(blob) {
    try {
      const bmp = await createImageBitmap(blob);
      const s = { w: bmp.width, h: bmp.height };
      if (bmp.close) bmp.close();
      return s;
    } catch { return { w: 0, h: 0 }; }
  }

  // Full-resolution still when the browser supports ImageCapture, else a grab of the video frame.
  async function captureStill() {
    if (!state.stream || !video.videoWidth) throw new Error("The camera is not ready yet. Use Upload photo instead.");
    if (state.imageCapture && state.cam) {
      try {
        const opts = state.cam.photoW && state.cam.photoH ? { imageWidth: state.cam.photoW, imageHeight: state.cam.photoH } : undefined;
        const blob = await state.imageCapture.takePhoto(opts);
        if (blob && blob.size) {
          const s = await bitmapSize(blob);
          return { blob, w: s.w, h: s.h, via: "takePhoto" };
        }
      } catch (e) {
        console.warn("[prohori] takePhoto failed, using the video frame", e && e.name);
      }
    }
    const c = document.createElement("canvas");
    c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
    return { blob: await blobToJpeg(c, 0.92), w: c.width, h: c.height, via: "frame grab" };
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopCamera(); else if (state.view === "capture") startCamera();
  });

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

  async function measure(blob, name, meta) {
    if (state.busy) return;
    const joint = jointValue();
    if (joint === false) { toast("Joint ID: use letters, digits, - or _ (up to 64)."); return; }
    state.lastCapture = meta || { live: false, w: 0, h: 0, via: "upload" };
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
      if (joint) body.append("joint_id", joint);
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

  // Joint ID: "" when empty, false when invalid, else the trimmed id. Remembered per device.
  function jointValue() {
    const v = $("joint").value.trim();
    if (!v) return "";
    return JOINT_RE.test(v) ? v : false;
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

  // crc: the deployed gate weighs all of these together, so no per-number pass mark is shown; a gauge is marked only
  // when the gate names it as a reason.
  function renderGauges(obs, reasons, crc) {
    const box = $("chips");
    box.replaceChildren();
    if (!obs) return;
    const has = (r) => reasons.includes(r);
    if (num(obs.corners)) box.append(gauge("Board corners", String(obs.corners), `/${obs.corners_total ?? "?"}`, null, has("too_few_corners")));
    if (num(obs.px_per_mm)) box.append(gauge("Scale", fmt(obs.px_per_mm, 1), "px/mm", crc ? "thin cracks need more" : `need ${MIN_PX_PER_MM} or more`, has("low_resolution") || (!crc && obs.px_per_mm < MIN_PX_PER_MM)));
    if (num(obs.blur_var)) box.append(gauge("Sharpness", fmt(obs.blur_var, 0), null, crc ? "higher is better" : `need ${MIN_BLUR_VAR} or more`, has("blurry")));
    if (num(obs.obliquity_deg)) box.append(gauge("Tilt", fmt(obs.obliquity_deg, 0), "°", crc ? "lower is better" : `max ${MAX_TILT_DEG}°`, has("oblique")));
    if (num(obs.glare_frac)) box.append(gauge("Glare", fmt(obs.glare_frac * 100, 0), "%", "lower is better", has("glare")));
    if (crc && num(obs.noise_sigma)) box.append(gauge("Grain", fmt(obs.noise_sigma, 1), null, "lower is better", has("noisy")));
  }

  function renderHero(animate) {
    const hero = $("hero");
    const c = state.cracks[state.sel];
    // deployed gate: each crack carries its own verdict; legacy gate: the capture's verdict applies to every crack
    const cert = state.crc && c ? c.certified === true : state.certified;
    hero.replaceChildren();
    const badge = h("span", { class: "badge " + (cert ? "ok" : "warn") },
      icon(cert ? "seal-check" : "warning"), cert ? "Certified" : state.crc ? "Flagged" : "Not certified");
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
    hero.append(...[
      h("div", { class: "hero-top" }, h("span", { class: "hero-id", text: `Crack ${c.id ?? ""}`.trim() }), badge),
      h("div", { class: "hero-num" },
        num(c.width_mm)
          ? [h("span", { class: "n", text: fmt(c.width_mm) }), h("span", { class: "u", text: "mm" })]
          : h("span", { class: "n none", text: "n/a" })),
      Array.isArray(c.interval_mm) && c.interval_mm.length === 2 && num(c.interval_mm[0]) && num(c.interval_mm[1])
        ? h("div", { class: "hero-pm" }, h("span", { class: "pm", text: `${fmt(c.interval_mm[0])} to ${fmt(c.interval_mm[1])}` }),
            h("span", { class: "pm-note", text: `mm, ${Math.round((c.interval_level || 0.9) * 100)}% range` }))
        : num(c.uncertainty_mm)
          ? h("div", { class: "hero-pm" }, h("span", { class: "pm", text: `± ${fmt(c.uncertainty_mm)}` }), h("span", { class: "pm-note", text: "mm uncertainty" }))
          : null,
      state.crc && !cert && Array.isArray(c.reasons) && c.reasons.length
        ? h("div", { class: "hero-why" }, c.reasons.map((r) => h("span", { class: "rchip", text: reasonText(r, true) })))
        : null,
      sub.length ? h("div", { class: "hero-sub" }, sub) : null].filter(Boolean));
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
      const flagged = state.crc && c.certified !== true;
      box.append(h("button", {
        class: "tile" + (flagged ? " flagged" : ""), type: "button", "aria-pressed": i === state.sel ? "true" : "false",
        "aria-label": `Crack ${c.id}: ${fmt(c.width_mm)} millimetres` + (state.crc ? (flagged ? ", flagged" : ", certified") : ""),
        onclick: () => { state.sel = i; renderPicker(); renderHero(true); },
      },
      h("span", { class: "tile-top" }, h("span", { class: "tile-id", text: String(c.id ?? i + 1) }),
        state.crc ? icon(flagged ? "warning" : "seal-check", "tile-st") : null),
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
    const red = data.redaction;
    if (red && red.faces > 0) meta.append(metaSpan("faces blurred", String(red.faces)));
    if (red && red.status === "unavailable") meta.append(h("span", { class: "warnmeta", text: "face blur unavailable, image not stored" }));

    // overlay
    const wrap = $("overlay-wrap");
    wrap.classList.remove("zoom");
    $("overlay-img").src = "data:image/jpeg;base64," + data.overlay_jpeg_b64;

    const crc = isCrc(gate);
    renderGauges(m.observation, reasons, crc);

    // gate: only what needs attention
    const g = $("gate");
    g.replaceChildren();
    if (m.error) {
      g.append(h("div", { class: "reason bad" }, icon("x-circle"),
        h("div", null, errorText(m.error), h("small", { text: String(m.error) }))));
    }
    if (crc && num(gate.cracks_total) && gate.cracks_total > 0) {
      // summary of the per-crack verdicts
      const nc = gate.cracks_certified || 0, nt = gate.cracks_total, nf = nt - nc;
      g.append(h("div", { class: "reason " + (nc ? "ok" : "") }, icon(nc ? "seal-check" : "warning"),
        h("div", null, nc ? `${nc} of ${nt} cracks certified` : `No crack certified (${nt} measured)`,
          h("small", { text: nc
            ? (nf ? `${nf} flagged: still measured, with a wider range, but not certified. Tap a crack to see why.` : "All measured cracks passed the gate.")
            : "All readings are shown with their 90% range, but none can be vouched for." }))));
    }
    if (gate.certified === false) {
      for (const r of reasons) {
        if (m.error && r === "too_few_corners") continue;
        g.append(h("div", { class: "reason" }, icon("warning"), h("div", null, reasonText(r, crc))));
      }
    }
    // a small live-camera frame is the usual reason for "too low resolution": say so, gently
    const lc = state.lastCapture;
    if (lc && lc.live && lc.w && tooSmallToCertify(lc.w, lc.h) && gate.certified !== true) {
      g.append(h("div", { class: "reason soft" }, icon("info"), h("div", null, smallHint(lc.w, lc.h))));
    }
    renderEscalation(data.escalation);
    renderJoint(data.joint);

    // measurements
    state.cracks = Array.isArray(m.cracks) ? m.cracks : [];
    state.crc = crc;
    state.certified = gate.certified === true && !m.error;
    // open on the most trustworthy crack: lowest predicted error among the certified ones, else among all
    const rank = (c) => (num(c.risk_ratio) ? c.risk_ratio : Infinity);
    let best = 0;
    if (crc && state.cracks.length) {
      const all = state.cracks.map((c, i) => i);
      const cert = all.filter((i) => state.cracks[i].certified === true);
      const pool = cert.length ? cert : all;
      best = pool.reduce((a, i) => (rank(state.cracks[i]) < rank(state.cracks[a]) ? i : a), pool[0]);
    }
    state.sel = best;
    renderHero(false);
    renderPicker();
  }

  // ------------------------------------------------- escalation + joint history
  const WHY = {
    abandon_and_log: "The agent could not get a certifiable reading.",
    widening: "Wider than last visit, beyond measurement uncertainty.",
    trend: "Visits show a steady widening trend.",
  };

  function renderEscalation(e) {
    const box = $("esc");
    box.replaceChildren();
    box.hidden = true;
    if (!e) return;
    let title, sub;
    if (e.escalated) {
      title = "Escalated to engineer";
      sub = (e.why || []).map((w) => WHY[w]).filter(Boolean).join(" ");
      if (e.sns === "failed") sub += " The e-mail could not be sent; the request is logged.";
      else if (e.sns === "local_only") sub += " Logged here; no notification channel is set.";
      sub += " Review requested, not a safety verdict.";
    } else if (e.suppressed === "rate_limit") {
      title = "Engineer already notified";
      sub = "A review request for this joint went out within the last hour.";
    } else return;
    box.append(icon("hard-hat"), h("div", null, h("b", { text: title }), h("span", { text: sub.trim() })));
    box.hidden = false;
  }

  function signed(x, d = 2) { return `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(d)}`; }
  function agoText(days) {
    if (!num(days)) return "";
    if (days < 1) return `${Math.max(1, Math.round(days * 24))} h ago`;
    return `${Math.round(days)} day${Math.round(days) === 1 ? "" : "s"} ago`;
  }

  // visits: [{width_mm, uncertainty_mm}], drawn as dots with +/- u bars; the last one is today's.
  function sparkline(visits) {
    const W = 300, H = 76, padX = 14, padY = 10;
    const svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "spark");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Width at each visit with its uncertainty");
    const lo = Math.min(...visits.map((v) => v.width_mm - (v.uncertainty_mm || 0)));
    const hi = Math.max(...visits.map((v) => v.width_mm + (v.uncertainty_mm || 0)));
    const span = Math.max(hi - lo, 0.05);
    const x = (i) => (visits.length === 1 ? W / 2 : padX + (i * (W - 2 * padX)) / (visits.length - 1));
    const y = (w) => H - padY - ((w - lo) / span) * (H - 2 * padY);
    const mk = (tag, attrs) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
    if (visits.length > 1) {
      svg.append(mk("polyline", { class: "sp-line", points: visits.map((v, i) => `${x(i)},${y(v.width_mm)}`).join(" ") }));
    }
    visits.forEach((v, i) => {
      const u = v.uncertainty_mm || 0;
      svg.append(mk("line", { class: "sp-bar", x1: x(i), x2: x(i), y1: y(v.width_mm + u), y2: y(v.width_mm - u) }));
      svg.append(mk("circle", { class: "sp-dot" + (i === visits.length - 1 ? " now" : ""), cx: x(i), cy: y(v.width_mm), r: i === visits.length - 1 ? 6 : 4.5 }));
    });
    return svg;
  }

  function renderJoint(j) {
    const card = $("joint-card");
    card.replaceChildren();
    card.hidden = true;
    if (!j || !j.id || !(j.n_visits > 0)) return;
    const visits = (j.visits || []).filter((v) => num(v.width_mm));
    const ch = j.change, tr = j.trend;

    card.append(h("div", { class: "jc-top" },
      h("span", { class: "jc-id" }, icon("tag"), `Joint ${j.id}`),
      h("span", { class: "jc-n", text: `${j.n_visits} visit${j.n_visits === 1 ? "" : "s"}` })));

    if (ch && num(ch.delta_mm)) {
      const tone = ch.significant ? (ch.direction === "wider" ? "bad" : "ok") : "flat";
      const label = ch.significant ? (ch.direction === "wider" ? "Wider, beyond uncertainty" : "Narrower, beyond uncertainty") : "Within measurement uncertainty";
      card.append(h("div", { class: "jc-change " + tone },
        h("div", { class: "jc-delta" }, h("span", { class: "n", text: signed(ch.delta_mm) }), h("span", { class: "u", text: "mm" })),
        h("div", { class: "jc-what" }, h("b", { text: label }),
          h("span", { text: `since last visit${num(ch.days) ? `, ${agoText(ch.days)}` : ""}` }))));
      if (num(ch.threshold_mm)) {
        card.append(h("p", { class: "jc-rule", text: nb(`A change counts only above ±${fmt(ch.threshold_mm)} mm (${Math.round((ch.level || 0.9) * 100)}% combined uncertainty of both visits).`) }));
      }
    } else if (j.n_visits === 1) {
      card.append(h("p", { class: "jc-first", text: j.logged ? "First certified visit saved. Measure again next visit to see change." : "No certified visit saved yet." }));
    }

    if (visits.length) card.append(sparkline(visits));

    if (tr && num(tr.slope_mm_per_30d)) {
      const t = tr.significant ? (tr.direction === "widening" ? "bad" : "ok") : "flat";
      card.append(h("div", { class: "jc-trend " + t },
        icon("trend-up"),
        h("div", null,
          h("b", { text: `${signed(tr.slope_mm_per_30d)} mm per 30 days` }),
          h("span", { text: nb(`${tr.n} visits, ${Math.round((tr.level || 0.9) * 100)}% interval ${signed(tr.slope_lo_mm_per_30d)} to ${signed(tr.slope_hi_mm_per_30d)}. ${tr.significant ? "Interval excludes zero." : "Not distinguishable from no change."}`) }))));
    } else if (j.n_visits >= 1 && j.n_visits < 3) {
      card.append(h("p", { class: "jc-need", text: `Trend appears after 3 visits (${3 - j.n_visits} more).` }));
    }

    if (j.logged === false) card.append(h("p", { class: "jc-need", text: "This capture was not certified, so it was not added to the history." }));
    card.append(h("p", { class: "jc-foot", text: "Durability guidance, not a structural verdict. Same joint is assumed; the crack is not re-identified between visits." }));
    card.hidden = false;
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
      const sg = s.gate || {};

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
      obs.append(h("span", { class: "ochip" + (sg.certified ? "" : " fail") }, "gate",
        h("b", { text: isCrc(sg) && num(sg.cracks_total) && sg.cracks_total > 0 ? `${sg.cracks_certified || 0}/${sg.cracks_total} certified` : sg.certified ? "certified" : "not certified" })));
      if (num(s.faces_redacted) && s.faces_redacted > 0) obs.append(h("span", { class: "ochip" }, "faces blurred", h("b", { text: String(s.faces_redacted) })));
      if (s.joint_id) obs.append(h("span", { class: "ochip" }, "joint", h("b", { text: s.joint_id }), s.joint_logged ? h("span", { class: "d good", text: "saved" }) : null));
      if (s.escalation && s.escalation.escalated) obs.append(h("span", { class: "ochip fail" }, "escalated", h("b", { text: "to engineer" })));

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
    try {
      const shot = await captureStill();
      console.info("[prohori] captured", shot.w, "x", shot.h, "via", shot.via);
      showCamInfo(shot);
      await measure(await shrinkIfHuge(shot.blob), "frame.jpg", { live: true, w: shot.w, h: shot.h, via: shot.via });
    } catch (e) { toast(e.message || "Capture failed."); }
  });
  const jointEl = $("joint");
  jointEl.value = pref.get("prohori.joint", "");
  jointEl.addEventListener("input", () => {
    const v = jointEl.value.replace(/\s+/g, "-").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
    if (v !== jointEl.value) jointEl.value = v;
    pref.set("prohori.joint", v);
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
