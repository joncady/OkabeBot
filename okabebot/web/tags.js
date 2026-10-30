'use strict';
const tagsUI=(()=>{
 const $=id=>document.getElementById(id);let lastLearned='',signature='',destinations=[],unmappedTag='',chores=[],choresSignature='',draftChoreId='',saving=false,knownAreas={},roomSignature='';
 function action(){return $('tag-action').value||'call_companion';}
 function setSaving(value){saving=value;for(const id of ['tag-register','tag-map-last','tag-name','tag-action','tag-room-follow','tag-room-minutes','tag-room-location','tag-location','tag-chore-select','tag-chore-title','tag-chore-delay','tag-chore-unit','tag-chore-repeat','tag-chore-reminders','tag-enabled'])$(id).disabled=value;$('tag-save').disabled=value||!$('tag-id').value;}
 function roomScreens(selected=$('tag-room-location').value){
  const area=knownAreas[$('tag-id').value]?.area_id;const eligible=[...destinations].sort((a,b)=>Number(b.area_id===area)-Number(a.area_id===area));const next=JSON.stringify([area,eligible,selected]);if(next===roomSignature)return;roomSignature=next;$('tag-room-location').replaceChildren();
  const automatic=document.createElement('option');automatic.value='';automatic.textContent='Automatic · only one screen in the room';$('tag-room-location').append(automatic);
  for(const place of eligible){const option=document.createElement('option');option.value=place.id;option.textContent=place.name+' · '+[place.floor_name,place.area_name||'Unassigned'].filter(Boolean).join(' / ')+(area&&place.area_id!==area?' · fallback only':'');$('tag-room-location').append(option);}
  if(selected&&!eligible.some(p=>p.id===selected)){const missing=document.createElement('option');missing.value=selected;missing.textContent='Saved screen unavailable · choose again';$('tag-room-location').append(missing);}
  $('tag-room-location').value=selected;
 }
 function actionFields(){const chore=action()==='chore_reminder',room=action()==='room_checkin';$('tag-destination').hidden=chore||room;$('tag-location').required=!chore&&!room;$('tag-chore-settings').hidden=!chore;$('tag-chore-delay').max=$('tag-chore-unit').value==='weeks'?'52':'365';for(const id of ['tag-chore-delay','tag-chore-repeat'])$(id).required=chore;$('tag-room-settings').hidden=!chore&&!room;$('tag-room-follow-label').hidden=!chore;$('tag-room-minutes').required=room||(chore&&$('tag-room-follow').checked);}

 function newId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');}
 function resetChore(){draftChoreId=''; $('tag-chore-select').value='';$('tag-chore-title').value='';$('tag-chore-delay').value='2';$('tag-chore-unit').value='weeks';$('tag-chore-repeat').value='1';$('tag-chore-reminders').checked=true;$('tag-chore-delay').max='52'; }
 function clear(){$('tag-room-cue').textContent='';$('tag-room-follow').checked=false;$('tag-room-location').value='';knownAreas={};roomSignature='';$('tag-room-location').replaceChildren();destinations=[]; $('nfc-tags').hidden=true;$('tag-mappings').replaceChildren();$('tag-id').value='';$('tag-name').value='';$('tag-location').replaceChildren();$('tag-status').textContent='';$('tag-action').value='call_companion';$('tag-room-follow').checked=false;$('tag-room-minutes').value=10;$('tag-room-location').value='';resetChore();actionFields();lastLearned='';signature='';unmappedTag='';chores=[];choresSignature='';$('tag-chore-select').replaceChildren();$('tag-map-last').hidden=true;$('tag-save').disabled=true; }
 async function request(path,data){
  const token=dashboardAccess.token();if(!token)throw Error('Owner access required');
  const r=await fetch(path,{method:data?'POST':'GET',headers:{'X-Hardware-Token':token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store'});
  if(token!==dashboardAccess.token())throw Error('Access changed');
  const value=await r.json();if(!r.ok)throw Error(value.error||'Tag request failed');return value;
 }
 function choreFields(item){
  if(!item)return;const days=item.interval_days||14,wholeWeeks=days%7===0;
  $('tag-chore-title').value=item.title;$('tag-chore-delay').value=wholeWeeks?days/7:days;$('tag-chore-unit').value=wholeWeeks?'weeks':'days';$('tag-chore-repeat').value=item.repeat_days||1;$('tag-chore-reminders').checked=item.enabled!==false;$('tag-chore-delay').max=wholeWeeks?'52':'365';
 }
 function setChores(items){
  if(typeof choresUI!=='undefined')choresUI.update(items);
  const next=JSON.stringify(items);if(next===choresSignature)return;choresSignature=next;chores=items;
  const selected=$('tag-chore-select').value;$('tag-chore-select').replaceChildren();const fresh=document.createElement('option');fresh.value='';fresh.textContent='Create a chore';$('tag-chore-select').append(fresh);
  for(const item of chores){const option=document.createElement('option');option.value=item.id;option.textContent=item.title+(item.enabled?'':' · Paused');$('tag-chore-select').append(option);}
  if(selected&&chores.some(c=>c.id===selected))$('tag-chore-select').value=selected;
  else if(selected){const missing=document.createElement('option');missing.value=selected;missing.textContent='Chore removed · choose or create another';$('tag-chore-select').append(missing);$('tag-chore-select').value=selected;}
 }
 function edit(mapping){$('tag-room-follow').checked=mapping.room_follow===true;$('tag-room-minutes').value=mapping.room_minutes||10;$('tag-room-location').value=mapping.room_location_id||'';$('tag-save').disabled=false;$('tag-id').value=mapping.tag_id;$('tag-name').value=mapping.name;$('tag-location').value=mapping.location_id||'';$('tag-enabled').checked=mapping.enabled;$('tag-action').value=mapping.action||'call_companion';resetChore();if(mapping.chore_id){$('tag-chore-select').value=mapping.chore_id;choreFields(chores.find(c=>c.id===mapping.chore_id));}roomScreens(mapping.room_location_id||'');actionFields();}
 function paint(value){
  $('nfc-tags').hidden=false;if(Array.isArray(value.chores))setChores(value.chores);
  const portal=$('tag-ha-link');portal.hidden=true;
  try{const url=new URL(value.home_assistant_url);if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password){portal.href=new URL('/config/tags',url).href;portal.hidden=false;}}catch{}
  if(JSON.stringify(value.locations)!==JSON.stringify(destinations)){
   const previous=$('tag-location').value;destinations=value.locations;$('tag-location').replaceChildren();
   for(const place of destinations){const option=document.createElement('option');option.value=place.id;option.textContent=place.name+' · '+[place.floor_name,place.area_name||'Unassigned'].filter(Boolean).join(' / ');$('tag-location').append(option);}
   if(destinations.some(p=>p.id===previous))$('tag-location').value=previous;
  }
  knownAreas=value.tag_areas||{};roomScreens();
  const cue=value.room_cue;$('tag-room-cue').textContent=cue?'Recent NFC room cue · '+[cue.floor,cue.room].filter(Boolean).join(' / ')+' · expires '+new Date(cue.expires_at*1000).toLocaleTimeString()+' · scanner identity unknown':'';
  $('tag-learn-status').textContent=value.learning?(value.learned?'Tag captured. Name it and save its action.':'Waiting for a scan · registration expires after 90 seconds.'): 'Register a tag in the Home Assistant app, then scan it here to map its action.';
  if(value.learning&&value.learned&&value.learned!==lastLearned){lastLearned=value.learned;$('tag-save').disabled=false;$('tag-id').value=value.learned;$('tag-name').value='';$('tag-enabled').checked=true;roomScreens('');}
  const last=value.last_scan;unmappedTag=last&&!value.mappings.some(m=>m.tag_id===last.tag_id)?last.tag_id:'';$('tag-map-last').hidden=!unmappedTag;
  $('tag-last-scan').textContent=last?'Last scan: '+new Date(last.at*1000).toLocaleTimeString()+' · '+last.status.replaceAll('_',' ')+(last.room_status?' · '+last.room_status.replaceAll('_',' '):''):'No scans received yet.';
  const next=JSON.stringify([value.mappings,value.locations,chores]);if(next===signature)return;signature=next;$('tag-mappings').replaceChildren();
  for(const mapping of value.mappings){
   const row=document.createElement('article');row.className='tag-card';
   const title=document.createElement('h3');title.textContent=mapping.name;
   const detail=document.createElement('p');const place=destinations.find(p=>p.id===mapping.location_id),chore=chores.find(c=>c.id===mapping.chore_id),isChore=mapping.action==='chore_reminder',isRoom=mapping.action==='room_checkin';
   detail.textContent=(isRoom?'Room check-in → screen assigned to the HA tag area':isChore?('Chore reminder → '+(chore?.title||'Chore unavailable')+(chore?` · ${chore.interval_days} days after completion`+(chore.enabled?(chore.overdue?' · Due':chore.due_at?' · Due '+new Date(chore.due_at*1000).toLocaleDateString():''):' · Reminders paused'):'')):('Call companion → '+(place?.name||'Destination unavailable')))+(mapping.enabled?'':' · Tag disabled');if(mapping.room_follow||isRoom)detail.textContent+=' · NFC room cue + room follow';row.append(title,detail);
   const room=document.createElement('p');room.textContent=mapping.ha_area?.area_id?'Room · '+[mapping.ha_area.floor,mapping.ha_area.room].filter(Boolean).join(' / ')+' · from Home Assistant':mapping.area_status==='unassigned'?'Room unassigned · set the tag entity’s Area in Home Assistant':mapping.area_status==='missing'?'Tag entity not found in Home Assistant':'HA room metadata unavailable · refresh rooms';row.append(room);
   const actions=[['Edit',async()=>edit(mapping)]];
   if(isChore&&chore)actions.push(['Mark done',async()=>{await request('/chores/complete',{id:mapping.chore_id});await load();if(typeof choresUI!=='undefined')await choresUI.load();$('tag-status').textContent='Chore marked done; next reminder scheduled.';}]);
   else if(!isChore&&!isRoom)actions.push(['Test',async()=>{const r=await request('/tags/test',{tag_id:mapping.tag_id});$('tag-status').textContent=r.status.replaceAll('_',' ');}]);
   actions.push(['Remove tag',async()=>{await request('/tags/remove',{tag_id:mapping.tag_id});await load();$('tag-status').textContent='Tag mapping removed. Any chore remains in Chores.';}]);
   for(const [label,fn] of actions){const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=()=>{if(button.disabled)return;button.disabled=true;return run(async()=>{try{await fn();}finally{button.disabled=false;}});};row.append(button);}
   $('tag-mappings').append(row);
  }
 }
 async function run(fn){try{await fn();}catch(error){$('tag-status').textContent=error.message;}}
 async function load(){try{if(!dashboardAccess.token()){clear();return;}const value=await request('/tags');if(!Array.isArray(value.chores)){try{const result=await request('/chores');setChores(result.items||[]);}catch{setChores([]);}}paint(value);}catch{clear();}}
 $('tag-refresh-areas').onclick=()=>run(async()=>{const value=await request('/tags/refresh-areas',{});paint(value);$('tag-status').textContent=value.area_refresh==='ready'?'HA tag rooms refreshed.':'Unable to refresh tag rooms; check the HA connection.';});
 $('tag-room-follow').onchange=actionFields;
 $('tag-action').onchange=actionFields;$('tag-chore-unit').onchange=actionFields;$('tag-chore-select').onchange=()=>{const item=chores.find(c=>c.id===$('tag-chore-select').value);if(item)choreFields(item);else resetChore();};
 $('tag-register').onclick=()=>run(async()=>{lastLearned='';$('tag-id').value='';$('tag-name').value='';$('tag-save').disabled=true;$('tag-action').value='call_companion';$('tag-room-follow').checked=false;$('tag-room-minutes').value=10;$('tag-room-location').value='';resetChore();actionFields();paint(await request('/tags/learn',{}));});
 $('tag-map-last').onclick=()=>{if(unmappedTag)edit({tag_id:unmappedTag,name:'',location_id:$('tag-location').value,enabled:true});};
 $('tag-form').onsubmit=event=>{event.preventDefault();if(saving)return;setSaving(true);return run(async()=>{try{
  const body={tag_id:$('tag-id').value,name:$('tag-name').value,enabled:$('tag-enabled').checked};
  if(action()==='chore_reminder'){
   const cfg={title:$('tag-chore-title').value.trim()||$('tag-name').value.trim(),interval_days:Number($('tag-chore-delay').value)*($('tag-chore-unit').value==='weeks'?7:1),repeat_days:Number($('tag-chore-repeat').value),enabled:$('tag-chore-reminders').checked};
   cfg.id=$('tag-chore-select').value||draftChoreId||(draftChoreId=newId());
   const saved=await request('/chores/save',cfg),item=saved.item||(saved.items||[]).find(c=>c.id===cfg.id);
   if(!item?.id)throw Error('Chore saved. Refresh chores before binding this tag.');
   setChores(saved.items||[...chores.filter(c=>c.id!==item.id),item]);$('tag-chore-select').value=item.id;draftChoreId=item.id;
   body.action='chore_reminder';body.chore_id=item.id;
  }else if(action()==='room_checkin')body.action='room_checkin';else body.location_id=$('tag-location').value;
  if(action()==='room_checkin'||(action()==='chore_reminder'&&$('tag-room-follow').checked)){body.room_follow=true;body.room_minutes=Number($('tag-room-minutes').value);body.room_location_id=$('tag-room-location').value;}
  paint(await request('/tags/save',body));$('tag-status').textContent=body.action==='room_checkin'?'Room check-in saved. A real scan will use its HA room and request one move.':body.action==='chore_reminder'?'Mapping saved. Each scan marks the chore done and schedules its next reminder.':'Mapping saved. Tap the tag to call the companion.';
  if(typeof choresUI!=='undefined')await choresUI.load();
 }finally{setSaving(false);} });};
 const previousForget=$('dashboard-forget').onclick;$('dashboard-forget').onclick=()=>{previousForget();clear();};
 actionFields();load();setInterval(load,3000);
 return {load,clear};
})();
