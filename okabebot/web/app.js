let enabled = true,
  lastRequests = "";
let notificationPolicy = {}, policyDirty = false;
function updateSourceRule() {
  const source = document.querySelector('#notification-source').value;
  const rule = notificationPolicy.sources?.[source] || {enabled:true,audio:'default'};
  document.querySelector('#source-enabled').checked = rule.enabled;
  document.querySelector('#source-audio').value = rule.audio;
}
document.querySelector('#notification-source').onchange = updateSourceRule;
document.querySelector('#quiet-hours-form').oninput = () => { policyDirty = true; };
document.querySelector('#quiet-hours-form').onsubmit = async event => {
  event.preventDefault();
  try {
    await api('/notifications/preferences', {quiet_hours:{
      enabled:document.querySelector('#quiet-enabled').checked,
      start:document.querySelector('#quiet-start').value,
      end:document.querySelector('#quiet-end').value,
      timezone:document.querySelector('#quiet-timezone').value.trim()
    }});
    policyDirty=false;
    document.querySelector('#error').textContent='';
  } catch(error) { document.querySelector('#error').textContent=error.message; }
};
document.querySelector('#source-rule-form').onsubmit = async event => {
  event.preventDefault();
  await action('/notifications/preferences', {sources:{
    [document.querySelector('#notification-source').value]:{
      enabled:document.querySelector('#source-enabled').checked,
      audio:document.querySelector('#source-audio').value
    }
  }});
};
document.querySelectorAll('[data-snooze]').forEach(button => {
  button.onclick=()=>action('/notifications/snooze',{minutes:Number(button.dataset.snooze)});
});
function notificationPreferencesUI(state) {
  const previous = JSON.stringify(notificationPolicy.sources);
  notificationPolicy=state.notification_policy || {};
  const quiet=notificationPolicy.quiet_hours;
  if (!quiet) return;
  document.querySelector('#notification-policy-status').textContent = notificationPolicy.snoozed
    ? `Snoozed until ${new Date(notificationPolicy.snoozed_until*1000).toLocaleTimeString()}`
    : notificationPolicy.quiet_active ? 'Quiet hours active · cards only' : 'Notifications active';
  if (!policyDirty) {
    document.querySelector('#quiet-enabled').checked=quiet.enabled;
    document.querySelector('#quiet-start').value=quiet.start;
    document.querySelector('#quiet-end').value=quiet.end;
    document.querySelector('#quiet-timezone').value=quiet.timezone;
  }
  const select=document.querySelector('#notification-source');
  for (const source of new Set([...Object.keys(notificationPolicy.sources || {}),...(state.notifications || []).map(n=>n.source)])) {
    if (![...select.options].some(option=>option.value===source)) {
      const option=document.createElement('option'); option.value=source;option.textContent=source;select.append(option);
    }
  }
  if (previous!==JSON.stringify(notificationPolicy.sources)) updateSourceRule();
}
async function api(path, data) {
  let r = await fetch(path, {
    method: data ? "POST" : "GET",
    headers: { "X-Hardware-Token": location.hash.slice(1), "Content-Type": "application/json" },
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
  action("/speech-engine", { engine: event.target.value });
let volumeSaving = false, lastAudibleVolume = 20;
async function setSpeakerVolume(percent) {
  volumeSaving = true;
  document.querySelector("#speaker-volume").disabled = true;
  document.querySelector("#speaker-mute").disabled = true;
  try {
    const result = await api("/speaker/volume", {percent});
    if (result.percent > 0) lastAudibleVolume = result.percent;
    document.querySelector("#speaker-volume").value = result.percent;
    document.querySelector("#speaker-volume-value").textContent = `${result.percent}%`;
    document.querySelector("#error").textContent = "";
  } catch (error) { document.querySelector("#error").textContent = error.message; }
  finally { volumeSaving = false; }
}
document.querySelector("#speaker-volume").oninput = event => {
  document.querySelector("#speaker-volume-value").textContent = `${event.target.value}%`;
};
document.querySelector("#speaker-volume").onchange = event => setSpeakerVolume(Number(event.target.value));
document.querySelector("#speaker-mute").onclick = () => {
  const current = Number(document.querySelector("#speaker-volume").value);
  setSpeakerVolume(current === 0 ? lastAudibleVolume : 0);
};
document.querySelector("#dev-toggle").onclick = () => {
  const panel = document.querySelector("#developer");
  panel.hidden = !panel.hidden;
  document
    .querySelector("#dev-toggle")
    .setAttribute("aria-pressed", String(!panel.hidden));
};
document.querySelectorAll(".character-card").forEach((button) => {
  button.onclick = () =>
    action("/character", { profile: button.dataset.profile });
});
document.querySelector("#test-notification").onclick = () =>
  action("/notifications", {
    source: "calendar",
    title: "Your next meeting",
    body: "Starts in 10 minutes · A moment to get ready.",
    priority: "normal",
  });
document.querySelector("#spotify-connect").onclick = async () => {
  try {
    const result = await api("/media/connect", {});
    const url = new URL(result.url);
    if (url.protocol !== "https:" || !Array.isArray(result.allowed_hosts) || !result.allowed_hosts.includes(url.hostname))
      throw Error("Unexpected provider authorization URL");
    location.assign(url.href);
  } catch (e) {
    document.querySelector("#error").textContent = e.message;
  }
};
document.querySelector("#music-mic").onclick = async () => {
  const button = document.querySelector("#music-mic");
  try { await api("/music/microphone", {enabled: button.getAttribute("aria-pressed") !== "true"}); }
  catch (error) { alert(error.message); }
};

document.querySelectorAll("[data-focus]").forEach(button => { button.onclick = async () => { try { await api("/focus/start", {minutes: Number(button.dataset.focus)}); } catch (e) { document.querySelector("#error").textContent = e.message; } }; });
document.querySelector("#focus-cancel").onclick = async () => { try { await api("/focus/cancel", {}); } catch (e) { document.querySelector("#error").textContent = e.message; } };

function musicUI(s) {
  const focus = s.focus || {};
  const left = Math.max(0, Math.ceil((focus.ends_at || 0) - Date.now()/1000));
  document.querySelector("#focus-status").textContent = focus.active ? (left ? `${Math.floor(left/60)}:${String(left%60).padStart(2,"0")} left · Keep going` : "Complete · reminder queued") : "Choose a session. I’ll remind you to take a break.";
  document.querySelector("#focus-cancel").hidden = !focus.active;
  const mic = document.querySelector("#music-mic");
  mic.setAttribute("aria-pressed", String(!!s.music_mic));
  mic.textContent = s.music_mic ? "Music mic: on" : "Music mic: off";
  mic.title = s.music_meter?.error || "Local sound energy only; no recording or transcription.";
  const music = s.music || {}, spotify = s.media || s.spotify || {};
  document.querySelector("#spotify-connect").hidden = spotify.can_authenticate === false;
  const playing = !!music.is_playing && !s.active_notification;
  const scene = document.querySelector(".scene");
  scene.classList.toggle("music-playing", playing && !s.busy && !s.recording);
  document.querySelector(".music-notes").hidden = !playing;
  const footer = document.querySelector("#music-footer");
  footer.hidden = !playing;
  const copy = [music.title, music.artist].filter(Boolean).join(" · ");
  if (footer.dataset.copy !== copy) {
    footer.dataset.copy = copy;
    footer.replaceChildren(el("span", copy));
  }
  const text = footer.firstChild;
  if (text) {
    const overflow = Math.max(0, text.scrollWidth - footer.clientWidth + 28);
    text.classList.toggle("scrolling", overflow > 0);
    text.style.setProperty("--travel", `-${overflow}px`);
  }
  document.querySelector("#spotify-status").textContent = spotify.error ||
    (spotify.connected ? (music.is_playing ? "Playing · " + copy : "Connected · Waiting for playback.") :
      spotify.configured ? `Ready to connect ${spotify.label || "your media source"}.` : "Media source setup needed on the server.");
  const button = document.querySelector("#spotify-connect");
  button.disabled = !spotify.configured;
  button.textContent = `${spotify.connected ? "Reconnect" : "Connect"} ${spotify.label || "media source"}`;
}
function notificationUI(s) {
  const active = s.active_notification;
  const presented = document.querySelector("#presented");
  presented.hidden = !active;
  presented.replaceChildren();
  if (active)
    presented.append(
      el("small", active.source),
      el("strong", active.title),
      el("p", active.body),
    );
  const root = document.querySelector("#inbox");
  root.replaceChildren();
  const items = (s.notifications || []).filter(
    (n) => n.id !== s.focus?.id && !["dismissed", "expired", "cancelled"].includes(n.status),
  );
  document.querySelector("#inbox-count").textContent = items.length;
  if (!items.length)
    root.append(el("p", "All quiet. You’re free to focus.", "muted"));
  items.slice(0, 8).forEach((n) => {
    const row = el("div", null, "notification"),
      copy = el("div", null, "copy");
    if (["github", "calendar"].includes(n.source)) {
      const img = el("img");
      img.src = "/" + n.source + ".png";
      img.alt = n.source;
      row.append(img);
    }
    copy.append(el("strong", n.title), el("p", n.body));
    if (n.status === "failed" || n.status === "uncertain")
      copy.append(el("p", n.error || n.status));
    if (n.status === "pending" && n.due_at * 1000 > Date.now())
      copy.append(
        el("p", "Reminder: " + new Date(n.due_at * 1000).toLocaleString()),
      );
    const dismiss = el("button", "Dismiss");
    dismiss.onclick = () => action("/notifications/dismiss", { id: n.id });
    row.append(copy, dismiss);
    root.append(row);
  });
  document.querySelector("#source-errors").textContent = Object.values(
    s.source_errors || {},
  ).join(" · ");
  const deploys = document.querySelector("#deployments");
  deploys.replaceChildren();
  (s.deployments || []).forEach((d) =>
    deploys.append(
      el("div", "Deploying · " + d.repo + " · " + d.name, "deploy"),
    ),
  );
}
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
    notificationUI(s);
    musicUI(s);
    const parsed = s.content_parse || {}, slots = parsed.context || {};
    document.querySelector('#content-parse').textContent = slots.format
      ? `Auto parse: ${slots.format} · ${slots.sport || 'no sport'}${slots.league ? ' · ' + slots.league : ''} · ${(slots.participants || []).map(t => t.name).join(' vs ') || 'teams unset'} (${parsed.source})`
      : 'Auto parse: no confident sports match yet.';
    const profile = ["okabe", "kurisu", "pip", "sonic"].includes(s.style)
      ? s.style
      : "okabe";
    document.querySelector("#companion").src = "/" + profile + ".png";
    document.querySelector("#companion-name").textContent = s.character;
    document.querySelectorAll(".character-card").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.profile === profile));
      b.disabled = s.busy || s.recording;
    });
    const volume = s.speaker_volume || {};
    const slider = document.querySelector("#speaker-volume");
    slider.disabled = volumeSaving || !volume.available;
    const mute = document.querySelector("#speaker-mute");
    mute.disabled = slider.disabled;
    if (!volumeSaving && document.activeElement !== slider) {
      if (volume.available) {
        slider.value = volume.percent;
        if (volume.percent > 0) lastAudibleVolume = volume.percent;
        document.querySelector("#speaker-volume-value").textContent = `${volume.percent}%`;
      } else document.querySelector("#speaker-volume-value").textContent = "Unavailable";
    }
    mute.textContent = volume.percent === 0 ? "Unmute" : "Mute";
    const voiceEngine = document.querySelector("#speech-engine");
    voiceEngine.disabled = s.busy || s.recording;
    voiceEngine.querySelector('[value="openai"]').disabled = !s.cloud_available;
    if (document.activeElement !== voiceEngine)
      voiceEngine.value = ["openai", "local"].includes(s.speech_engine) ? s.speech_engine : "auto";
    const t = s.timings || {},
      a = s.speech_timings || {};
    const parts = [];
    for (const [key, label] of [
      ["release_to_clip_s", "Release → clip*"],
      ["transcription_s", "Transcription"],
      ["first_model_output_s", "Model first message"],
      ["codex_turn_s", "Codex turn (includes tools/audio)"],
    ]) {
      if (Number.isFinite(t[key]))
        parts.push(`${label}: ${t[key].toFixed(2)}s`);
    }
    if (a.started_at >= (t.clip_received_at || 0)) {
      if (Number.isFinite(a.synthesis_s))
        parts.push(`Speech synthesis: ${a.synthesis_s.toFixed(2)}s`);
      if (Number.isFinite(a.first_chunk_s))
        parts.push(`First cloud audio chunk: ${a.first_chunk_s.toFixed(2)}s`);
      if (a.playback_started_at && t.submitted_at)
        parts.push(
          `Submit → playback launch*: ${(a.playback_started_at - t.submitted_at).toFixed(2)}s`,
        );
    }
    document.querySelector("#timings").textContent =
      parts.join(" · ") +
      (parts.length
        ? " · *Device-clock estimate, not an acoustic measurement."
        : "Timings appear after your next message.");
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
    notificationPreferencesUI(s);
    const components = Object.entries(s.device_health || {}).map(([name, health])=>
      `${name === 'voice' ? 'Speaker/button Pi' : 'Display Pi'}: ${health.available ? 'connected' : 'reconnecting'}`);
    if (s.speech_health) components.push(`Voice: ${s.speech_health.available ? 'ready' : s.speech_health.error || 'warming'}`);
    if (s.codex_alive === false) components.push('Codex: reconnecting');
    document.querySelector('#system-health').textContent=components.join(' · ');
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

(async function contentPresets() {
  try {
    const [presets, crests] = await Promise.all([api('/content/presets'), api('/content/crests')]);
    const select = document.querySelector('#content-preset');
    for (const p of presets) {
      const option = document.createElement('option');
      option.value = p.id; option.textContent = `${p.kind}: ${p.label}`;
      select.append(option);
    }
    for (const id of ['preview-left','preview-right']) {
      const teamSelect = document.querySelector('#' + id);
      for (const crest of crests) {
        const option = document.createElement('option');
        option.value = crest.key; option.textContent = crest.name;
        teamSelect.append(option);
      }
    }
    const preview = async () => {
      if (!select.value) return;
      const [kind, key] = select.value.split('.');
      const context = {kind, genres: kind === 'movie' ? [key] : [],
        format: kind === 'video' ? key : '', confidence: 1};
      if (key.startsWith('sports_')) {
        context.sport = document.querySelector('#preview-sport').value;
        context.participants = ['preview-left','preview-right'].map(id =>
          crests.find(c => c.key === document.querySelector('#' + id).value))
          .filter(Boolean).map(c => ({name: c.name, crest: c.key}));
      }
      await action('/content/preview', context);
    };
    select.onchange = preview;
    for (const id of ['preview-sport','preview-left','preview-right'])
      document.querySelector('#' + id).onchange = preview;
    document.querySelector('#stop-content-preview').onclick = () => action('/content/preview/stop', {});
  } catch (e) { /* Server may still be starting; existing controls remain usable. */ }
})();
