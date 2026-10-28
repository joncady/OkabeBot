'use strict';
const amadeusUI = (() => {
  const $ = id => document.getElementById(id);
  let current = null;
  let editing = false;
  let accessEpoch = 0;
  function clearPrivate() {
    accessEpoch++;
    current=null;
    editing=false;$('amadeus-review').hidden=true;
    for(const id of ['amadeus-setup','amadeus-controls','amadeus-memory','amadeus-morning']) $(id).hidden=true;
    $('amadeus-form').reset();$('memory-form').reset();
    $('sources').replaceChildren();$('topics').replaceChildren();$('memory-list').replaceChildren();
    $('morning-test-status').textContent='';$('morning-test-tv').disabled=true;$('morning-preview').textContent='';$('morning-status').textContent='';$('morning-form').reset();$('morning-destination').replaceChildren();
    $('event-list').textContent='';$('household-list').textContent='';$('coaching-state').textContent='';
  }
  async function api(path, data) {
    const epoch=accessEpoch, token=dashboardAccess.token();
    const response = await fetch('/amadeus/api/' + path, {
      method: data === undefined ? 'GET' : 'POST', cache: 'no-store',
      headers: {'X-Hardware-Token': token, 'Content-Type': 'application/json'},
      body: data === undefined ? undefined : JSON.stringify(data)
    });
    if (response.status === 403) {clearPrivate(); dashboardAccess.required();}
    if (!response.ok) throw Error('Could not save or load private choices. Check access and input.');
    const result=await response.json();
    if(epoch!==accessEpoch || token!==dashboardAccess.token())throw Error('Private access changed; reconnect to continue.');
    dashboardAccess.remember();
    return result;
  }
  function message(text) { $('amadeus-status').textContent = text; }
  function options(container, entries, selected) {
    container.replaceChildren();
    for (const [key, text] of Object.entries(entries)) {
      const label = document.createElement('label'); label.className = 'amadeus-option';
      const input = document.createElement('input'); input.type = 'checkbox'; input.value = key;
      input.checked = selected.includes(key); label.append(input, document.createTextNode(text));
      container.append(label);
    }
  }
  function selected(id) { return [...$(id).querySelectorAll('input:checked')].map(i => i.value); }
  function coachingChoice() { return document.querySelector('input[name="coaching"]:checked').value; }
  function toggleTopics() { $('coaching-options').hidden = coachingChoice() !== 'choose_topics'; }
  async function memory() {
    const value = await api('memory'); $('memory-list').replaceChildren();
    for (const item of value.preferences.filter(p => p.key.startsWith('user.'))) {
      const li = document.createElement('li');
      const text = document.createElement('span'); text.textContent = item.key + ': ' + JSON.stringify(item.value);
      const remove = document.createElement('button'); remove.textContent = 'Forget';
      remove.onclick = () => run(async () => { await api('forget', {key:item.key}); await memory(); });
      li.append(text, remove); $('memory-list').append(li);
    }
    $('event-list').textContent = JSON.stringify(value.events, null, 2);
    $('household-list').textContent = JSON.stringify(value.household_events || [], null, 2);
    const coaching = value.preferences.find(p => p.key === 'health.coaching');
    const chosen=Boolean(coaching?.value?.topics?.length && coaching.value.choice==='choose_topics');
    for(const id of ['coaching-later','coaching-stop','coaching-resume']) $(id).disabled=!chosen;
    $('coaching-state').textContent = !coaching || !coaching.value.enabled ? 'Coaching is off.' :
      coaching.value.paused_until * 1000 > Date.now() ? 'Coaching is snoozed.' : 'Topics saved; nudges remain off.';
  }
  async function morning() {
    const value=await api('morning');if(!value.config)return;
    const c=value.config;$('amadeus-morning').hidden=false;
    $('morning-test-tv').disabled=!value.tv_preparation_configured;
    $('morning-start').value=c.start_hour;$('morning-end').value=c.end_hour;$('morning-unit').value=c.temperature_unit;
    $('morning-enabled').checked=c.enabled;$('morning-present').checked=c.present_on_wake;
    for(const [id,key] of [['before','before_minutes'],['after','after_minutes'],['rotation','rotation_seconds'],['duration','display_minutes']])$('morning-'+id).value=c[key];
    $('morning-destination').replaceChildren();
    for(const p of [{id:'',name:'Prepare only · no TV selected'},...value.destinations]){
      const option=document.createElement('option');option.value=p.id;option.textContent=p.name;$('morning-destination').append(option);
    }
    $('morning-destination').value=c.destination;
    $('morning-preview').textContent=value.summary?value.summary.cards.map(c=>c.title+' · '+c.body).join('\n\n'):'';
    $('morning-status').textContent=c.enabled?(c.present_on_wake&&!value.destination_ready?'TV needs a unique scene assignment in Locations before automatic presentation can work.':'Morning preparation configured; phone/weather permissions and active collection are also required.'):'Morning preparation off.';
  }
  async function load() {
    const value = await api('settings'); current = value.settings;
    $('amadeus-setup').hidden = Boolean(current) && !editing;
    $('amadeus-review').hidden = !current || editing;
    options($('sources'), value.sources, current?.sources || value.draft?.sources || []);
    options($('topics'), value.coaching_topics, current?.coaching_topics || []);
    if (current) {
      $('profile').value=current.profile; $('profile').readOnly=true;
      $('timezone').value=current.timezone; $('retention').value=current.retention_days;
      $('quiet-start').value=current.quiet_start; $('quiet-end').value=current.quiet_end;
      document.querySelector('input[name="coaching"][value="'+current.coaching_choice+'"]').checked=true;
      $('coaching-mode').value=current.coaching_mode;
    } else {
      $('profile').value=value.draft?.profile || 'primary'; $('profile').readOnly=false;
      $('timezone').value=Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      $('retention').value=30; $('quiet-start').value='22:00'; $('quiet-end').value='08:00';
      document.querySelector('input[name="coaching"][value="not_now"]').checked=true;
    }
    toggleTopics();
    $('amadeus-controls').hidden=!current; $('amadeus-memory').hidden=!current;
    if (current) {
      $('amadeus-pause').textContent=current.paused?'Shadow collection paused':'Pause shadow collection';
      $('amadeus-pause').setAttribute('aria-pressed',String(current.paused));
      $('amadeus-guest').textContent=current.guest?'Guest mode on':'Guest mode off';
      $('amadeus-guest').setAttribute('aria-pressed',String(current.guest)); await memory(); await morning();
    }
    message(value.collection_active ? 'Shadow metadata collection enabled · predictions and nudges off.' : 'Shadow metadata collection paused · predictions and nudges off.');
  }
  async function run(action) { try { await action(); } catch(error) { message(error.message); } }
  $('morning-test-tv').onclick=()=>run(async()=>{
    $('morning-test-status').textContent='Preparing TV… this may turn it on and change input.';
    const result=await api('tv-prepare',{});
    $('morning-test-status').textContent=result.ready?(result.input_verified?'TV ready · Chromecast input confirmed.':'TV preparation complete · input status unavailable; configured fallback used.'):'TV not confirmed ready · character stays on its current screen.';
  });
  $('morning-form').onsubmit=event=>{event.preventDefault();run(async()=>{
    await api('morning',{start_hour:Number($('morning-start').value),end_hour:Number($('morning-end').value),temperature_unit:$('morning-unit').value,enabled:$('morning-enabled').checked,destination:$('morning-destination').value,
      present_on_wake:$('morning-present').checked,before_minutes:Number($('morning-before').value),
      after_minutes:Number($('morning-after').value),rotation_seconds:Number($('morning-rotation').value),
      display_minutes:Number($('morning-duration').value)});await morning();
  });};
  $('amadeus-form').onsubmit = event => {
    event.preventDefault(); run(async () => {
      const choice=coachingChoice();
      await api('settings', {profile:$('profile').value, sources:selected('sources'),
        retention_days:Number($('retention').value), timezone:$('timezone').value,
        quiet_start:$('quiet-start').value, quiet_end:$('quiet-end').value,
        coaching_choice:choice, coaching_topics:choice==='choose_topics'?selected('topics'):[],
        coaching_mode:$('coaching-mode').value}); editing=false; await load();
    });
  };
  for(const radio of document.querySelectorAll('input[name="coaching"]')) radio.onchange=toggleTopics;
  $('amadeus-review').onclick=()=>{editing=true;run(load);};
  $('memory-form').onsubmit = event => { event.preventDefault(); run(async () => {
    await api('preference',{key:$('memory-key').value,value:$('memory-value').value});
    $('memory-value').value=''; await memory();
  }); };
  $('amadeus-pause').onclick=()=>run(async()=>{await api('control',{paused:!current.paused});await load();});
  $('amadeus-guest').onclick=()=>run(async()=>{await api('control',{guest:!current.guest});await load();});
  for(const [id,outcome] of [['coaching-later','later'],['coaching-stop','stop'],['coaching-resume','resume']]) {
    $(id).onclick=()=>run(async()=>{await api('feedback',{outcome});await memory();});
  }
  $('amadeus-export').onclick=()=>run(async()=>{
    const data=await api('export'); const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='amadeus-private-export.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('amadeus-forget').onclick=()=>run(async()=>{
    if(!$('forget-confirm').checked)throw Error('Confirm that you want to forget Amadeus data.');
    await api('forget',{confirm:'forget_amadeus'}); $('forget-confirm').checked=false;
    $('memory-list').replaceChildren();$('event-list').textContent=''; await load();
  });
  const forgetAccess=$('dashboard-forget').onclick;
  $('dashboard-forget').onclick=()=>{forgetAccess();clearPrivate();message('Private access forgotten.');};
  run(load);
  return {load};
})();
