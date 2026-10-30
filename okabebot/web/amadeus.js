'use strict';
const amadeusUI = (() => {
  const $ = id => document.getElementById(id);
  let current = null;
  let haInventory = [];
  let homePreview = null;
  let editing = false;
  let accessEpoch = 0;
  function clearPrivate() {
    accessEpoch++;
    current=null;haInventory=[];homePreview=null;
    editing=false;$('amadeus-review').hidden=true;
    for(const id of ['amadeus-setup','amadeus-controls','amadeus-memory','amadeus-morning','amadeus-habits','amadeus-feeds']) $(id).hidden=true;
    $('conversation-form').reset();$('conversation-destination').replaceChildren();
    $('amadeus-form').reset();$('memory-form').reset();
    $('sources').replaceChildren();$('topics').replaceChildren();$('memory-list').replaceChildren();
    $('morning-voice-form').reset();$('morning-person').textContent='';$('morning-show-status').textContent='';$('morning-test-status').textContent='';$('morning-test-tv').disabled=true;$('morning-preview').textContent='';$('morning-status').textContent='';$('morning-form').reset();$('morning-destination').replaceChildren();
    $('habits-preview').textContent='';$('habits-routines').replaceChildren();$('habits-state').textContent='';$('habits-enabled').checked=false;
    $('feed-list').replaceChildren();$('feed-context').textContent='';
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
  function feedConnection(connection) {
    const form=document.createElement('form');form.className='feed-connection';
    const grid=document.createElement('div');grid.className='amadeus-grid';
    const field=document.createElement('input');field.value=connection.transport==='ha'?connection.url:connection.client_id;
    field.autocomplete='off';field.required=true;
    const label=document.createElement('label');label.append(document.createTextNode(connection.transport==='ha'?'Home Assistant URL':'Trakt client ID'),field);
    const secret=document.createElement('input');secret.type='password';secret.autocomplete='off';
    secret.placeholder=connection.has_token?'Saved · leave blank to keep':'Paste access token';secret.required=!connection.has_token;
    const tokenLabel=document.createElement('label');tokenLabel.append(document.createTextNode('Access token'),secret);
    grid.append(label,tokenLabel);form.append(grid);
    if(connection.transport==='trakt'&&connection.has_token){const saved=document.createElement('p');saved.className='feed-help';saved.textContent='Authorization saved. Collection is controlled separately by Allow this feed’s metadata below.';form.append(saved);}
    const actions=document.createElement('div');actions.className='feed-actions';
    const save=document.createElement('button');save.textContent='Save connection';actions.append(save);
    const disconnect=document.createElement('button');disconnect.type='button';disconnect.textContent='Disconnect';
    disconnect.onclick=()=>run(async()=>{await api('feed-connection',{transport:connection.transport,disconnect:true});if(connection.transport==='ha'){haInventory=[];homePreview=null;}await load();});actions.append(disconnect);form.append(actions);
    form.onsubmit=event=>{event.preventDefault();run(async()=>{
      const data={transport:connection.transport,token:secret.value};data[connection.transport==='ha'?'url':'client_id']=field.value.trim();
      await api('feed-connection',data);secret.value='';if(connection.transport==='ha'){haInventory=[];homePreview=null;}await feeds();message('Connection saved. Enable the feeds you want to use.');
    });};
    if(connection.transport==='trakt'){
      const clientSecret=document.createElement('input');clientSecret.type='password';clientSecret.autocomplete='off';clientSecret.placeholder='Legacy client secret · leave blank for new apps';
      const start=document.createElement('button');start.type='button';start.textContent='Sign in with Trakt';
      const status=document.createElement('p');
      const check=document.createElement('button');check.type='button';check.textContent='Check approval';check.hidden=true;
      start.onclick=()=>run(async()=>{const value=await api('trakt-auth',{action:'start',client_id:field.value.trim(),client_secret:clientSecret.value.trim()});clientSecret.value='';status.textContent='Open https://trakt.tv/activate and enter '+value.user_code;check.hidden=false;});
      check.onclick=()=>run(async()=>{const value=await api('trakt-auth',{action:'check'});status.textContent=value.state.replaceAll('_',' ');if(value.state.startsWith('authorized'))await feeds();});
      form.append(clientSecret,start,status,check);
    }
    return form;
  }
  function feedSelection(field, values, feedId) {
    const box=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=field.label;box.append(legend);
    if(field.domain==='line'||field.key==='routes') {
      const choices={'1':'1 Line','2':'2 Line','T':'T Line','N':'N Line · Sounder','S':'S Line · Sounder'};
      const checks=[];
      for(const [id,name] of Object.entries(choices)) {
        const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=id;input.checked=values.includes(id);checks.push(input);
        label.className='amadeus-option';label.append(input,document.createTextNode(name));box.append(label);
      }
      const hint=document.createElement('p');hint.className='feed-help';hint.textContent='No lines selected means all rail lines.';box.append(hint);
      return {element:box,read:()=>checks.filter(i=>i.checked).map(i=>i.value)};
    }
    const rows=document.createElement('div');rows.className='feed-entities';let entries=values.length?[...values]:[''];
    const hint=document.createElement('p');hint.className='feed-help';hint.textContent=haInventory.length?'Search discovered entities by name or room. Saving a feed is a separate observation choice.':'Use Refresh rooms and entities to discover choices, or enter an entity ID.';
    let inputs=[];
    const draw=()=>{
      rows.replaceChildren();inputs=[];
      entries.forEach((value,index)=>{
        const row=document.createElement('div');row.className='feed-entity-row';
        const input=document.createElement('input');input.value=value;input.maxLength=100;input.autocomplete='off';input.spellcheck=false;
        const list=document.createElement('datalist');list.id='ha-choice-'+feedId+'-'+field.key+'-'+index;
        for(const entity of haInventory.filter(e=>e.id.startsWith((field.domain||'entity')+'.'))){
          const option=document.createElement('option');option.value=entity.id;option.label=[entity.name,entity.room,entity.provider,entity.available?'':'unavailable'].filter(Boolean).join(' · ');list.append(option);
        }
        input.setAttribute('list',list.id);
        input.placeholder=(field.domain||'entity')+'.example';input.setAttribute('aria-label',field.label+' '+(index+1));inputs.push(input);
        const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.setAttribute('aria-label','Remove '+field.label+' '+(index+1));
        remove.onclick=()=>{entries=inputs.map(i=>i.value);entries.splice(index,1);draw();};row.append(input,remove,list);rows.append(row);
      });
    };
    draw();const add=document.createElement('button');add.type='button';add.textContent='＋ Add entity';
    add.onclick=()=>{entries=inputs.map(i=>i.value);if(entries.length<12){entries.push('');draw();}};
    box.append(hint,rows,add);
    return {element:box,read:()=>[...new Set(inputs.map(i=>i.value.trim()).filter(Boolean))]};
  }
  async function feeds() {
    const value=await api('feeds');$('amadeus-feeds').hidden=false;$('feed-list').replaceChildren();
    const connections=Object.fromEntries((value.connections||[]).map(c=>[c.transport,c]));
    if(connections.ha) {
      const shared=document.createElement('section');shared.className='feed-card';
      const heading=document.createElement('h3');heading.textContent='Home Assistant · shared connection';
      const help=document.createElement('p');help.className='feed-help';help.textContent='Used by Tasks, Device activity, Appliances and Meals. Connect the providers in Home Assistant first.';
      const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Refresh rooms and entities';
      refresh.onclick=()=>run(async()=>{const inventory=await api('ha-inventory');haInventory=inventory.entities||[];homePreview=inventory;await feeds();message('Read-only preview refreshed. Discovered devices have not been enabled for observation.');});
      const rooms=document.createElement('p');rooms.className='feed-help';rooms.textContent=[...new Set(haInventory.map(e=>e.room).filter(Boolean))].join(' · ');
      shared.append(heading,help,feedConnection(connections.ha),refresh,rooms);
      for(const place of homePreview?.locations||[]){
        const row=document.createElement('label');row.className='feed-entity-row';row.append(document.createTextNode(place.name+(place.needs_review?' · room removed; review':'')));
        const select=document.createElement('select');
        const unassigned=document.createElement('option');unassigned.value='';unassigned.textContent='Unassigned';select.append(unassigned);
        for(const room of homePreview.rooms||[]){const option=document.createElement('option');option.value=room.id;option.textContent=room.name;select.append(option);}
        select.value=place.area_id||'';select.onchange=()=>run(async()=>{homePreview=await api('ha-inventory',{location_id:place.id,area_id:select.value||null});message('Room binding saved. Display orientation and movement are unchanged.');});
        row.append(select);shared.append(row);
      }$('feed-list').append(shared);
    }
    for(const feed of (value.feeds||[])) {
      const card=document.createElement('section');card.className='feed-card';
      const header=document.createElement('div');header.className='feed-heading';
      const heading=document.createElement('h3');heading.textContent=feed.label;
      const health=document.createElement('span');health.className='feed-status';health.textContent=feed.status.replaceAll('_',' ');header.append(heading,health);
      const help=document.createElement('p');help.className='feed-help';help.textContent=feed.instructions;
      card.append(header,help);
      if(connections[feed.transport]&&feed.transport!=='ha')card.append(feedConnection(connections[feed.transport]));
      const form=document.createElement('form'),label=document.createElement('label'),enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=feed.config.enabled;
      label.className='amadeus-option';label.append(enabled,document.createTextNode('Allow this feed’s metadata'));form.append(label);
      const inputs={};for(const field of feed.fields){inputs[field.key]=feedSelection(field,feed.config[field.key],feed.id);form.append(inputs[field.key].element);}
      const save=document.createElement('button');save.textContent='Save feed';form.append(save);
      const check=document.createElement('button');check.type='button';check.textContent='Check selected feed';check.disabled=!feed.config.enabled;
      check.onclick=()=>run(async()=>{await api('feed-check',{id:feed.id});await feeds();message('Selected feed checked. See its status and retained context below.');});form.append(check);
      form.onsubmit=event=>{event.preventDefault();run(async()=>{
        const config={enabled:enabled.checked};for(const [key,input] of Object.entries(inputs))config[key]=input.read();
        await api('feeds',{id:feed.id,config});await load();message('Feed saved. Pause and guest mode remain unchanged.');
      });};card.append(form);$('feed-list').append(card);
    }
    $('feed-context').textContent=JSON.stringify(value.context||[],null,2);
  }
  async function memory() {
    const value = await api('memory'); $('memory-list').replaceChildren();
    for (const item of value.preferences.filter(p => p.key.startsWith('user.') || p.key==='context.preferences')) {
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
    const voice=value.voice||{};$('morning-person').textContent=voice.resolved_name?`Greeting name: ${voice.resolved_name} · ${voice.name_source==='home_assistant'?'Home Assistant person':'spoken override'}`:'Link a Home Assistant person or set a spoken override.';$('morning-spoken').checked=!!voice.enabled;$('morning-name').value=voice.name||'';
    $('morning-coaching').checked=!!voice.coaching;$('morning-quiet-override').checked=!!voice.quiet_override;
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
  async function conversation() {
    const value=await api('conversation');
    const config=value.config||{};
    $('conversation-destination').replaceChildren();
    for(const place of (value.destinations||[])){
      const option=document.createElement('option');option.value=place.id;option.textContent=place.name;
      $('conversation-destination').append(option);
    }
    if(config.destination)$('conversation-destination').value=config.destination;
    $('conversation-enabled').checked=config.enabled===true;
    $('conversation-resume').disabled=config.enabled!==true;
  }
  async function habits() {
    const value=await api('habits');if(!value.config)return;
    $('amadeus-habits').hidden=false;$('habits-enabled').checked=value.config.enabled;
    $('habits-routines').replaceChildren();
    for(const routine of value.preview.routines){
      const li=document.createElement('li');const hour=String(Math.floor(routine.minute/60)).padStart(2,'0'),minute=String(routine.minute%60).padStart(2,'0');
      li.textContent=`${routine.kind} · ${hour}:${minute} · ${routine.matching_days}/${routine.observed_days} observed ${routine.day_type} days · ${routine.scope}`;
      $('habits-routines').append(li);
    }
    $('habits-state').textContent=value.preview.state==='disabled'?'Preview off or collection paused.':value.preview.routines.length?'Shadow only · no notifications or actions.':'Not enough consistent observed days yet.';
    $('habits-preview').textContent=JSON.stringify(value.preview.proposals,null,2);
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
      $('amadeus-guest').setAttribute('aria-pressed',String(current.guest)); await memory(); await morning(); await habits(); await conversation(); await feeds();
    }
    if(!current){$('amadeus-habits').hidden=true;$('habits-preview').textContent='';$('habits-routines').replaceChildren();}
    message(value.collection_active ? 'Metadata collection enabled · routine predictions stay in shadow; morning speech and conversations have separate controls.' : 'Metadata collection paused · proactive conversations are paused too.');
  }
  async function run(action) { try { await action(); } catch(error) { message(error.message); } }
  $('feeds-refresh').onclick=()=>run(feeds);
  $('conversation-resume').onclick=()=>run(async()=>{await api('conversation-resume',{});message('Reply resumed. Use the usual push-to-talk button; the invitation was not replayed.');});
  $('conversation-form').onsubmit=event=>{event.preventDefault();run(async()=>{await api('conversation',{enabled:$('conversation-enabled').checked,destination:$('conversation-destination').value});await conversation();message('Conversation choice saved.');});};
  $('habits-refresh').onclick=()=>run(habits);
  $('habits-enabled').onchange=()=>run(async()=>{await api('habits',{enabled:$('habits-enabled').checked});await habits();});
  $('morning-test-tv').onclick=()=>run(async()=>{
    $('morning-test-status').textContent='Preparing TV… this may turn it on and change input.';
    const result=await api('tv-prepare',{});
    $('morning-test-status').textContent=result.ready?(result.input_verified?'TV ready · Chromecast input confirmed.':'TV preparation complete · input status unavailable; configured fallback used.'):'TV not confirmed ready · character stays on its current screen.';
  });
  $('morning-voice-form').onsubmit=event=>{event.preventDefault();run(async()=>{
    await api('morning-voice',{enabled:$('morning-spoken').checked,name:$('morning-name').value,coaching:$('morning-coaching').checked,quiet_override:$('morning-quiet-override').checked});await morning();message('Morning voice choices saved.');
  });};
  $('morning-show').onclick=()=>run(async()=>{
    const result=await api('morning-present',{});$('morning-show-status').textContent=result.accepted?'Preparing today’s briefing. Speech respects quiet hours and the daily limit.':'Briefing is already preparing or unavailable.';
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
