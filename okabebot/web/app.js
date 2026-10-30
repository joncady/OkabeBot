let powerInitialized=false;
let connectionError = "";
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
  senderRulesUI(notificationPolicy.senders || []);
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
    headers: { "X-Hardware-Token": dashboardAccess.token(), "Content-Type": "application/json" },
    body: data ? JSON.stringify(data) : undefined,
  });
  let x = await r.json();
  if (!r.ok) { if(r.status===403)dashboardAccess.required(); throw Error(x.error); }
  dashboardAccess.remember();
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
  agendaUI(s);
  document.querySelector('#natural-tool-replies').checked=s.personality?.natural_tool_replies!==false;
  const tone=document.querySelector('#character-tone');if(document.activeElement!==tone)tone.value=s.personality?.tone||'subtle';
  const mac=s.mac_screen||{}, macForm=document.querySelector('#mac-screen-form');
  if(mac.config&&!macForm.contains(document.activeElement)){
    document.querySelector('#mac-screen-enabled').checked=mac.config.enabled;
    document.querySelector('#mac-screen-media').checked=mac.config.respect_media;
    document.querySelector('#mac-screen-hold').checked=mac.config.respect_manual_hold;
    document.querySelector('#mac-screen-cooldown').value=mac.config.cooldown_seconds;
    const select=document.querySelector('#mac-screen-destination');select.replaceChildren();
    for(const place of (s.surfaces?.locations||[]).filter(p=>p.adapter==='mac'&&p.approved)){
      const option=document.createElement('option');option.value=place.id;option.textContent=place.name;select.append(option);
    }select.value=mac.config.destination;
  }
  document.querySelector('#mac-screen-state').textContent=`Mac screen: ${mac.state||'unknown'} · ${mac.reason||'waiting'}`;
  const presence=s.presence || {};
  const following=document.querySelector('#presence-follow');
  following.hidden=!presence.configured;
  following.dataset.enabled=String(Boolean(presence.follow_enabled));
  following.textContent=presence.follow_enabled ? 'Pause Watch following' : 'Enable Watch following';
  document.querySelector('#presence-health').textContent=presence.configured
    ? `Watch: ${presence.presence || 'unknown'} · ${presence.healthy_scanners || 0}/2 scanners · ${presence.follow_reason || 'starting'}` : '';
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
    if (n.sender_id) copy.append(el("small", `${n.source} · Sender ID: ${n.sender_id}`));
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
    const portal = document.querySelector('#home-assistant-portal');
    if (portal) {
      let url;
      try { url = new URL(s.home_assistant_url); } catch (_) {}
      const valid = url && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash;
      portal.hidden = !valid;
      if (valid) portal.href = url.href; else portal.removeAttribute('href');
    }
    if (connectionError && document.querySelector("#error").textContent === connectionError) document.querySelector("#error").textContent = "";
    connectionError = "";
    enabled = s.enabled;
    if(s.screen_power){
      const c=s.screen_power.config;
      if(!powerInitialized){
        document.querySelector('#night-enabled').checked=c.enabled;
        document.querySelector('#night-start').value=c.sleep_start;
        document.querySelector('#night-end').value=c.sleep_end;
        document.querySelector('#night-zone').value=c.timezone;
        document.querySelector('#night-minutes').value=c.wake_minutes;
        document.querySelector('#startup-ac').checked=!!s.runtime_policy?.prevent_sleep_on_ac;
        document.querySelector('#startup-docker').checked=!!s.runtime_policy?.docker_at_login;
        powerInitialized=true;
      }
      document.querySelector('#night-status').textContent=`Display: ${s.screen_power.state}`;
    }

    const history=document.querySelector('#timing-history'); history.replaceChildren();
    for (const t of (s.recent_timings || [])) {
      history.append(el('p',`${new Date(t.clip_received_at*1000).toLocaleTimeString()} · ${t.backend} · STT ${t.transcription_s ?? '?'}s · model ${t.local_generation_s ?? t.first_model_output_s ?? '?'}s · tool ${t.local_tool_s ?? '?'}s · ${t.status}`));
    }
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
    const surface=s.surfaces||{};
    const places=surface.locations||[];
    locationsUI(surface);
    const current=places.find(p=>p.id===surface.current_location);
    const display=places.find(p=>p.adapter==='pi'),cast=places.find(p=>p.adapter==='cast');
    document.querySelector('#surface-status').textContent=surface.error||(current?`At ${current.name}`:`Moving to ${surface.destination_name||'destination'}…`);
    document.querySelector('#surface-tv').textContent=`Move to ${cast?.name||'destination'}`;
    document.querySelector('#surface-tv').dataset.location=cast?.id||'';
    document.querySelector('#surface-home').textContent=`Return to ${display?.name||'display'}`;
    document.querySelector('#surface-home').dataset.location=display?.id||'';
    document.querySelector('#surface-tv').disabled=surface.phase!=='pi';
    document.querySelector('#surface-home').disabled=surface.phase==='pi';
    const components = Object.entries(s.device_health || {}).map(([name, health])=>
      `${name === 'voice' ? 'Speaker/button Pi' : 'Display Pi'}: ${health.available ? 'connected' : 'reconnecting'}`);
    if (s.speech_health) components.push(`Voice: ${s.speech_health.available ? s.speech_health.fallback ? `${s.speech_health.backend} · system fallback (no character reference)` : 'ready' : s.speech_health.error || 'warming'}`);
    if (s.github_queue_health?.configured && !s.github_queue_health.available) components.push(s.github_queue_health.error || 'GitHub relay reconnecting');
    if (!document.querySelector('#amadeus-respect-dnd').disabled) {
      document.querySelector('#amadeus-respect-dnd').checked=s.amadeus_interruptions?.respect_dnd!==false;
    }
    const shadow=s.amadeus_shadow || {};
    if (!document.querySelector('#amadeus-shadow-enabled').disabled) document.querySelector('#amadeus-shadow-enabled').checked=shadow.enabled===true;
    document.querySelector('#amadeus-shadow-status').textContent=shadow.enabled
      ? `Shadow only · ${shadow.status} · ${shadow.candidates || 0} candidates · no delivery`
      : 'Shadow trial disabled';
    const cameraGreeting=s.camera_greeting || {};
    const greetingConfig=cameraGreeting.settings||{};
    for(const [id,key,fallback] of [['greeting-source','source','camera'],['greeting-near','near_mm',800],['greeting-far','far_mm',1100],['greeting-dwell','dwell_seconds',2],['greeting-cooldown','cooldown_seconds',120]]){
      const input=document.getElementById(id);if(!greetingSettingsDirty&&document.activeElement!==input)input.value=greetingConfig[key]??fallback;
    }
    if(!greetingSettingsDirty)document.getElementById('greeting-home').checked=greetingConfig.require_home!==false;
    if(!greetingSettingsDirty)document.getElementById('greeting-media').checked=greetingConfig.allow_during_media===true;
    document.querySelector('#camera-greeting-enabled').checked=cameraGreeting.enabled===true;
    document.querySelector('#camera-greeting-status').textContent=cameraGreeting.status || 'Disabled';
    if (s.codex_alive === false) components.push(s.conversation_backend === 'local' ? 'Local model unavailable; restart controller' : 'Codex: reconnecting');
    document.querySelector('#system-health').textContent=components.join(' · ');
    document.querySelector("#thread").textContent =
      (s.auto_approve_hardware
        ? "Hardware auto-approval ON · "
        : "Manual approvals · ") +
      (s.conversation_backend === "local" ? "Local model · " : "Codex · ") +
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
    connectionError = e.message;
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

 document.querySelector('#agenda-show').onclick=()=>action('/agenda/show',{});
 function agendaUI(s) {
   const agenda=s.agenda || {}, next=agenda.next;
   const minutes=next ? Math.max(0,Math.ceil((next.start-Date.now()/1000)/60)) : 0;
   document.querySelector('#agenda-next').textContent = agenda.stale ? 'Calendar unavailable or updating' : next ? `${next.title} · in ${minutes} min` : 'No upcoming timed events';
   const root=document.querySelector('#agenda-events');root.replaceChildren();
   for (const event of agenda.events || []) root.append(el('p',`${new Date(event.start*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',...(agenda.timezone && agenda.timezone!=='local'?{timeZone:agenda.timezone}:{})})} · ${event.title}`,'muted'));
   document.querySelector('#agenda-show').disabled=Boolean(agenda.stale);
 }


// These controls call the same application operations as the MCP tools.
async function refreshReminders() {
  const result = await api('/reminders/list', {});
  const list = document.querySelector('#reminders-list');
  list.replaceChildren();
  for (const reminder of result.reminders) {
    const row = el('p', `${reminder.body} — ${new Date(reminder.due_at * 1000).toLocaleString()}`);
    const cancel = el('button', 'Cancel');
    cancel.onclick = async () => { await action('/reminders/cancel', {id:reminder.id}); await refreshReminders(); };
    row.append(cancel); list.append(row);
  }
  if (!result.reminders.length) list.append(el('p', 'No pending reminders.'));
}
let reminderRequestId = null;
document.querySelector('#reminder-form').onsubmit = async event => {
  event.preventDefault();
  // Keep this ID after an uncertain failure; never duplicate a reminder on retry.
  reminderRequestId ||= 'web-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  try {
    await api('/reminders/create', {text:document.querySelector('#reminder-text').value,
      minutes:Number(document.querySelector('#reminder-minutes').value), request_id:reminderRequestId});
    reminderRequestId = null; await refreshReminders();
    document.querySelector('#error').textContent = '';
  } catch(error) { document.querySelector('#error').textContent = error.message; }
};
document.querySelector('#reminder-form').oninput = () => { reminderRequestId = null; };
document.querySelector('#reminders-refresh').onclick = () => refreshReminders().catch(error => { document.querySelector('#error').textContent = error.message; });
document.querySelector('#spotify-devices').onclick = async () => {
  try {
    const result = await api('/spotify/devices', {});
    document.querySelector('#spotify-device-list').textContent = result.devices.map(d => `${d.name}${d.is_active ? ' (playing)' : ''}`).join(', ') || 'No Spotify Connect devices currently available.';
  } catch(error) { document.querySelector('#error').textContent = error.message; }
};
document.querySelector('#agenda-range-form').onsubmit = event => {
  event.preventDefault();
  action('/agenda/show', {start_date:document.querySelector('#agenda-from').value, end_date:document.querySelector('#agenda-until').value});
};
document.querySelector('#echo-refresh').onclick = async () => {
  try {
    const result = await api('/echo/speakers', {});
    const select = document.querySelector('#echo-speaker'); select.replaceChildren();
    for (const name of result.speakers) { const option = el('option', name); option.value = name; select.append(option); }
  } catch(error) { document.querySelector('#error').textContent = error.message; }
};
document.querySelector('#echo-form').onsubmit = event => {
  event.preventDefault();
  action('/echo/speak', {speaker:document.querySelector('#echo-speaker').value, text:document.querySelector('#echo-text').value});
};


let lastSenderRules = '';
function senderRulesUI(rules) {
  const signature=JSON.stringify(rules);
  if (signature===lastSenderRules) return;
  lastSenderRules=signature;
  const root=document.querySelector('#sender-rules'); root.replaceChildren();
  if (!rules.length) root.append(el('p','No sender-specific rules.'));
  for (const rule of rules) {
    const row=el('p',`${rule.source} / ${rule.sender_id}: ${rule.enabled ? rule.audio : 'disabled'} · ${rule.priority}`);
    const edit=el('button','Edit'); edit.onclick=()=>{
      document.querySelector('#sender-source').value=rule.source;
      document.querySelector('#sender-id').value=rule.sender_id;
      document.querySelector('#sender-enabled').checked=rule.enabled;
      document.querySelector('#sender-audio').value=rule.audio;
      document.querySelector('#sender-priority').value=rule.priority;
    };
    const remove=el('button','Remove'); remove.onclick=()=>action('/notifications/senders',{action:'delete',source:rule.source,sender_id:rule.sender_id});
    row.append(edit,remove); root.append(row);
  }
}
document.querySelector('#sender-rule-form').onsubmit=event=>{
  event.preventDefault();
  action('/notifications/senders',{
    source:document.querySelector('#sender-source').value.trim(),
    sender_id:document.querySelector('#sender-id').value.trim(),
    enabled:document.querySelector('#sender-enabled').checked,
    audio:document.querySelector('#sender-audio').value,
    priority:document.querySelector('#sender-priority').value
  });
};

document.querySelector('#surface-tv').onclick=event=>action('/surfaces/move',{location_id:event.currentTarget.dataset.location});
document.querySelector('#surface-home').onclick=event=>action('/surfaces/move',{location_id:event.currentTarget.dataset.location});
document.querySelector('#surface-preview').onclick=async()=>{
  const preview=window.open('about:blank','okabebot-tv-preview');
  try{const result=await api('/surfaces/preview',{});if(preview)preview.location=result.url;const link=document.querySelector('#surface-preview-link');link.href=result.url;link.hidden=false;}
  catch(e){if(preview)preview.close();document.querySelector('#error').textContent=e.message;}
};


document.querySelector('#presence-follow').onclick = async () => {
  try {
    const button = document.querySelector('#presence-follow');
    await api('/presence/follow', {enabled:button.dataset.enabled !== 'true'});
  } catch (e) { document.querySelector('#error').textContent=e.message; }
};

let greetingSettingsDirty=false;
for(const id of ['greeting-source','greeting-near','greeting-far','greeting-dwell','greeting-cooldown','greeting-media','greeting-home'])document.getElementById(id).oninput=()=>{greetingSettingsDirty=true;};
const cameraGreetingToggle=document.querySelector('#camera-greeting-enabled');
cameraGreetingToggle.onchange=async()=>{
  cameraGreetingToggle.disabled=true;
  try { await api('/camera/greeting',{enabled:cameraGreetingToggle.checked}); }
  catch(error){document.querySelector('#error').textContent=error.message;}
  finally{cameraGreetingToggle.disabled=false;}
};

document.querySelector('#amadeus-respect-dnd').onchange=async event=>{
  const toggle=event.target;
  toggle.disabled=true;
  try { const result=await api('/amadeus/interruptions',{respect_dnd:toggle.checked});toggle.checked=result.respect_dnd; }
  catch(error){toggle.checked=!toggle.checked;document.querySelector('#error').textContent=error.message;}
  finally{toggle.disabled=false;}
};

document.querySelector('#amadeus-shadow-enabled').onchange=async event=>{
 const toggle=event.target;toggle.disabled=true;
 try{await api('/amadeus/shadow',{enabled:toggle.checked});}
 catch(error){toggle.checked=!toggle.checked;document.querySelector('#error').textContent=error.message;}
 finally{toggle.disabled=false;}
};

document.querySelector('#mac-screen-form').onsubmit=async event=>{event.preventDefault();try{
 await api('/mac/screen',{enabled:document.querySelector('#mac-screen-enabled').checked,destination:document.querySelector('#mac-screen-destination').value,
 respect_media:document.querySelector('#mac-screen-media').checked,respect_manual_hold:document.querySelector('#mac-screen-hold').checked,
 cooldown_seconds:Number(document.querySelector('#mac-screen-cooldown').value)});
}catch(e){document.querySelector('#error').textContent=e.message;}};

document.querySelector("#character-tone").onchange=event=>action("/character/tone",{tone:event.target.value});

document.querySelector("#natural-tool-replies").onchange=event=>action("/character/tone",{natural_tool_replies:event.target.checked});

document.querySelector('#greeting-save').onclick=async()=>{
 try{await api('/camera/greeting',{require_home:document.querySelector('#greeting-home').checked,allow_during_media:document.querySelector('#greeting-media').checked,source:document.querySelector('#greeting-source').value,
 near_mm:Number(document.querySelector('#greeting-near').value),far_mm:Number(document.querySelector('#greeting-far').value),
 dwell_seconds:Number(document.querySelector('#greeting-dwell').value),cooldown_seconds:Number(document.querySelector('#greeting-cooldown').value)});greetingSettingsDirty=false;}
 catch(error){document.querySelector('#error').textContent=error.message;}
};

document.querySelector('#night-save').onclick=async()=>{try{await api('/screen/power',{enabled:document.querySelector('#night-enabled').checked,sleep_start:document.querySelector('#night-start').value,sleep_end:document.querySelector('#night-end').value,timezone:document.querySelector('#night-zone').value,wake_minutes:Number(document.querySelector('#night-minutes').value)});}catch(e){document.querySelector('#error').textContent=e.message;}};
document.querySelector('#night-wake').onclick=async()=>{try{await api('/screen/power',{action:'wake'});}catch(e){document.querySelector('#error').textContent=e.message;}};
document.querySelector('#startup-save').onclick=async()=>{try{await api('/runtime/policy',{prevent_sleep_on_ac:document.querySelector('#startup-ac').checked,docker_at_login:document.querySelector('#startup-docker').checked});}catch(e){document.querySelector('#error').textContent=e.message;}};
