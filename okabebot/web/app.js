const token = location.hash.slice(1);
let enabled = true,
  lastRequests = "";
async function api(path, data) {
  let r = await fetch(path, {
    method: data ? "POST" : "GET",
    headers: { "X-Hardware-Token": token, "Content-Type": "application/json" },
    body: data ? JSON.stringify(data) : undefined,
  });
  let x = await r.json();
  if (!r.ok) throw Error(x.error);
  return x;
}
function el(tag, text, cls) {
  let e = document.createElement(tag);
  if (text) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
async function action(path, data) {
  try {
    await api(path, data);
    document.querySelector("#error").textContent = "";
  } catch (e) {
    document.querySelector("#error").textContent = e.message;
  }
}
document.querySelector("#toggle").onclick = () =>
  action("/enabled", { enabled: !enabled });
document.querySelector("#stop").onclick = () => action("/interrupt", {});
document.querySelector("#character").onchange = (event) =>
  action("/character", { profile: event.target.value });
document.querySelector("#speech-engine").onchange = (event) =>
  action("/speech-engine", {engine: event.target.value});
function requests(items) {
  const key = JSON.stringify(items);
  if (key === lastRequests) return;
  lastRequests = key;
  const root = document.querySelector("#approvals");
  root.replaceChildren();
  for (const req of items) {
    const box = el("div", null, "panel");
    box.append(el("h2", "Codex needs your input"));
    box.append(el("pre", JSON.stringify(req.params, null, 2)));
    if (
      [
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
      ].includes(req.method)
    ) {
      for (const [title, decision] of [
        ["Approve once", "accept"],
        ["Decline", "decline"],
        ["Cancel turn", "cancel"],
      ]) {
        const b = el("button", title);
        b.onclick = () => action("/answer", { id: req.id, decision });
        box.append(b);
      }
    } else if (
      req.method === "mcpServer/elicitation/request" &&
      req.params.mode === "form" &&
      req.params._meta?.codex_approval_kind === "mcp_tool_call" &&
      !Object.keys(req.params.requestedSchema?.properties || {}).length &&
      !(req.params.requestedSchema?.required || []).length
    ) {
      box.append(el("p", req.params.message));
      const choices = [["Approve once", "accept", null]];
      if ((req.params._meta.persist || []).includes("session")) {
        box.append(
          el(
            "p",
            "Allow for this session approves this call and lets Codex remember permission for this tool during the session.",
          ),
        );
        choices.push(["Allow for this session", "accept", "session"]);
      }
      choices.push(["Decline", "decline", null], ["Cancel", "cancel", null]);
      for (const [title, decision, persist] of choices) {
        let b = el("button", title);
        b.onclick = () => action("/answer", { id: req.id, decision, persist });
        box.append(b);
      }
    } else if (req.method === "item/tool/requestUserInput") {
      let fields = {};
      for (const q of req.params.questions) {
        box.append(el("p", q.question));
        let input = el("textarea");
        fields[q.id] = input;
        box.append(input);
      }
      let b = el("button", "Send answers");
      b.onclick = () =>
        action("/answer", {
          id: req.id,
          answers: Object.fromEntries(
            Object.entries(fields).map(([id, e]) => [id, e.value]),
          ),
        });
      box.append(b);
    } else {
      box.append(
        el(
          "p",
          "This request type is not supported here. Stop the turn; no approval has been granted.",
        ),
      );
    }
    root.append(box);
  }
}
async function refresh() {
  try {
    const s = await api("/state");
    enabled = s.enabled;
    const voiceEngine = document.querySelector("#speech-engine");
    voiceEngine.disabled = s.busy || s.recording;
    voiceEngine.querySelector('[value="openai"]').disabled = !s.cloud_available;
    if (document.activeElement !== voiceEngine) voiceEngine.value = s.speech_engine === "openai" ? "openai" : "auto";
    const t = s.timings || {}, a = s.speech_timings || {};
    const parts = [];
    for (const [key,label] of [["release_to_clip_s","Release → clip*"],["transcription_s","Transcription"],["first_model_output_s","Model first message"],["codex_turn_s","Codex turn (includes tools/audio)"]]) {
      if (Number.isFinite(t[key])) parts.push(`${label}: ${t[key].toFixed(2)}s`);
    }
    if (a.started_at >= (t.clip_received_at || 0)) {
      if (Number.isFinite(a.synthesis_s)) parts.push(`Speech synthesis: ${a.synthesis_s.toFixed(2)}s`);
      if (Number.isFinite(a.first_chunk_s)) parts.push(`First cloud audio chunk: ${a.first_chunk_s.toFixed(2)}s`);
      if (a.playback_started_at && t.submitted_at) parts.push(`Submit → playback launch*: ${(a.playback_started_at-t.submitted_at).toFixed(2)}s`);
    }
    document.querySelector("#timings").textContent = parts.join(" · ") + (parts.length ? " · *Device-clock estimate, not an acoustic measurement." : "Timings appear after your next message.");
    const selector = document.querySelector("#character");
    selector.disabled = s.busy || s.recording;
    if (document.activeElement !== selector) selector.value = s.profile;
    document.querySelector("#status").textContent = s.approvals.length
      ? "Waiting for your approval or answer"
      : s.status;
    document.querySelector("#toggle").textContent = enabled
      ? "Pause microphone button"
      : "Enable microphone button";
    document.title = s.character + " · OkabeBot";
    document.querySelector("#thread").textContent =
      (s.auto_approve_hardware
        ? "Hardware auto-approval ON · "
        : "Manual approvals · ") +
      (s.thread_id ? "Chat: " + s.thread_id : "Transcription only");
    requests(s.approvals);
    const root = document.querySelector("#messages");
    root.replaceChildren();
    for (const m of s.messages.filter((x) =>
      ["user", "assistant", "notice", "error", "auto_approval"].includes(
        x.kind,
      ),
    )) {
      let entry = el("div", null, "entry");
      entry.append(
        el(
          "div",
          m.kind === "user" ? "You" : m.kind === "assistant" ? "Codex" : m.kind,
          "who",
        ),
      );
      entry.append(
        el("div", m.data.text || m.data.message || JSON.stringify(m.data)),
      );
      root.append(entry);
    }
  } catch (e) {
    document.querySelector("#error").textContent = e.message;
  }
  setTimeout(refresh, 1000);
}
refresh();
