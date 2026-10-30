'use strict';
const tagsUI=(()=>{
 const $=id=>document.getElementById(id);let lastLearned='',signature='',destinations=[],unmappedTag='';
 function clear(){ $('nfc-tags').hidden=true;$('tag-mappings').replaceChildren();$('tag-id').value='';$('tag-name').value='';$('tag-location').replaceChildren();$('tag-status').textContent='';lastLearned='';signature='';unmappedTag='';$('tag-map-last').hidden=true;$('tag-save').disabled=true; }
 async function request(path,data){
  const token=dashboardAccess.token();if(!token)throw Error('Owner access required');
  const r=await fetch(path,{method:data?'POST':'GET',headers:{'X-Hardware-Token':token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store'});
  if(token!==dashboardAccess.token())throw Error('Access changed');
  const value=await r.json();if(!r.ok)throw Error(value.error||'Tag request failed');return value;
 }
 function edit(mapping){$('tag-save').disabled=false;$('tag-id').value=mapping.tag_id;$('tag-name').value=mapping.name;$('tag-location').value=mapping.location_id;$('tag-enabled').checked=mapping.enabled;}
 function paint(value){
  $('nfc-tags').hidden=false;
  const portal=$('tag-ha-link');portal.hidden=true;
  try{const url=new URL(value.home_assistant_url);if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password){portal.href=new URL('/config/tags',url).href;portal.hidden=false;}}catch{}
  if(JSON.stringify(value.locations)!==JSON.stringify(destinations)){
   const previous=$('tag-location').value;destinations=value.locations;$('tag-location').replaceChildren();
   for(const place of destinations){const option=document.createElement('option');option.value=place.id;option.textContent=place.name;$('tag-location').append(option);}
   if(destinations.some(p=>p.id===previous))$('tag-location').value=previous;
  }
  $('tag-learn-status').textContent=value.learning?(value.learned?'Tag captured. Name it and save its destination.':'Waiting for a scan · registration expires after 90 seconds.'): 'Register a tag in the Home Assistant app, then scan it here to map its action.';
  if(value.learning&&value.learned&&value.learned!==lastLearned){lastLearned=value.learned;$('tag-save').disabled=false;$('tag-id').value=value.learned;$('tag-name').value='';$('tag-enabled').checked=true;}
  const last=value.last_scan;unmappedTag=last&&!value.mappings.some(m=>m.tag_id===last.tag_id)?last.tag_id:'';$('tag-map-last').hidden=!unmappedTag;
  $('tag-last-scan').textContent=last?'Last scan: '+new Date(last.at*1000).toLocaleTimeString()+' · '+last.status.replaceAll('_',' '):'No scans received yet.';
  const next=JSON.stringify([value.mappings,value.locations]);if(next===signature)return;signature=next;$('tag-mappings').replaceChildren();
  for(const mapping of value.mappings){
   const row=document.createElement('article');row.className='tag-card';
   const title=document.createElement('h3');title.textContent=mapping.name;
   const detail=document.createElement('p');const place=destinations.find(p=>p.id===mapping.location_id);
   detail.textContent='Call companion → '+(place?.name||'Destination unavailable')+(mapping.enabled?'':' · Disabled');row.append(title,detail);
   for(const [label,fn] of [['Edit',async()=>edit(mapping)],['Test',async()=>{const r=await request('/tags/test',{tag_id:mapping.tag_id});$('tag-status').textContent=r.status.replaceAll('_',' ');}],['Remove',async()=>{await request('/tags/remove',{tag_id:mapping.tag_id});await load();}]]){
    const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=()=>run(fn);row.append(button);
   }$('tag-mappings').append(row);
  }
 }
 async function run(fn){try{await fn();}catch(error){$('tag-status').textContent=error.message;}}
 async function load(){try{if(!dashboardAccess.token()){clear();return;}paint(await request('/tags'));}catch{clear();}}
 $('tag-register').onclick=()=>run(async()=>{lastLearned='';$('tag-id').value='';$('tag-name').value='';$('tag-save').disabled=true;paint(await request('/tags/learn',{}));});
 $('tag-map-last').onclick=()=>{if(unmappedTag)edit({tag_id:unmappedTag,name:'',location_id:$('tag-location').value,enabled:true});};
 $('tag-form').onsubmit=event=>{event.preventDefault();run(async()=>{paint(await request('/tags/save',{tag_id:$('tag-id').value,name:$('tag-name').value,location_id:$('tag-location').value,enabled:$('tag-enabled').checked}));$('tag-status').textContent='Mapping saved. Tap the tag to call the companion.';});};
 const previousForget=$('dashboard-forget').onclick;$('dashboard-forget').onclick=()=>{previousForget();clear();};
 load();setInterval(load,3000);
 return {load,clear};
})();
