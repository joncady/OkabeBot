'use strict';
const choresUI=(()=>{
 const $=id=>document.getElementById(id);let state={items:[]},saving=false,signature='';
 async function request(path,data){
  const token=dashboardAccess.token();if(!token)throw Error('Owner access required');
  const response=await fetch(path,{method:data?'POST':'GET',headers:{'X-Hardware-Token':token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store'});
  const value=await response.json();if(token!==dashboardAccess.token())throw Error('Access changed');if(!response.ok)throw Error(value.error||'Chore request failed');return value;
 }
 function newId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');}
 function setSaving(value){saving=value;for(const id of ['chore-save','chore-new','chore-title','chore-delay','chore-unit','chore-repeat','chore-enabled'])$(id).disabled=value;}
 function interval(days){return days%7===0?{value:days/7,unit:'weeks'}:{value:days,unit:'days'};}
 function edit(item={}){
  $('chore-id').value=item.id||'';$('chore-title').value=item.title||'';
  const delay=interval(item.interval_days||14);$('chore-delay').value=delay.value;$('chore-unit').value=delay.unit;$('chore-delay').max=delay.unit==='weeks'?'52':'365';
  $('chore-repeat').value=item.repeat_days||1;$('chore-enabled').checked=item.enabled!==false;
  const form=$('chore-form');if(form.parentElement?.tagName==='DETAILS')form.parentElement.open=true;
 }
 function describe(item){
  if(!item.enabled)return 'Reminders paused';
  if(!item.due_at)return 'Waiting for its next due date';
  if(item.snoozed_until>Date.now()/1000)return 'Snoozed until · '+new Date(item.snoozed_until*1000).toLocaleDateString();
  return (item.overdue?'Due · ':'Next due · ')+new Date(item.due_at*1000).toLocaleDateString();
 }
 function paint(value,force=false){
  state={...value,items:value.items||[]};
  if(value.setup_required)$('chores-status').textContent='Finish private Amadeus setup before adding chores.';
  else if(value.paused||value.guest)$('chores-status').textContent='Chores stay saved; Amadeus reminders are quiet while paused or in guest mode.';
  const next=JSON.stringify([state.items,state.setup_required]);
  if(next===signature||(!force&&$('chores-list').contains?.(document.activeElement)&&['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)))return;
  signature=next;$('chores-list').replaceChildren();
  if(!state.items.length){const empty=document.createElement('p');empty.textContent='No chores yet. Add one here or choose Chore reminder when mapping a tag.';$('chores-list').append(empty);}
  for(const item of state.items){
   const row=document.createElement('article');row.className='tag-card chore-card';const title=document.createElement('h3');title.textContent=item.title;
   const detail=document.createElement('p');detail.textContent=describe(item)+` · every ${item.interval_days} days`+(item.rooms?.length?' · Room: '+item.rooms.map(r=>[r.floor,r.room].filter(Boolean).join(' / ')).join(', '):'');row.append(title,detail);
   function button(label,fn){const node=document.createElement('button');node.type='button';node.textContent=label;node.onclick=()=>{if(node.disabled)return;node.disabled=true;return run(async()=>{try{await fn();}finally{node.disabled=false;}});};row.append(node);}
   button('Mark done',()=>mutate('/chores/complete',{id:item.id}));button('Edit',async()=>edit(item));
   button(item.enabled?'Pause reminders':'Resume reminders',()=>mutate('/chores/save',{id:item.id,title:item.title,interval_days:item.interval_days,repeat_days:item.repeat_days,enabled:!item.enabled}));
   const snoozeLabel=document.createElement('label'),days=document.createElement('input');days.type='number';days.min='1';days.max='30';days.value='1';snoozeLabel.append(document.createTextNode('Snooze days'),days);row.append(snoozeLabel);
   button('Snooze',()=>mutate('/chores/snooze',{id:item.id,days:Number(days.value)}));
   button('Delete chore',async()=>{if(typeof window!=='undefined'&&window.confirm('Delete this chore and its local completion state? Its tag mapping will no longer complete it.'))await mutate('/chores/remove',{id:item.id});});
   $('chores-list').append(row);
  }
 }
 async function load(){
  if(!dashboardAccess.token()){clear();return;}
  paint(await request('/chores'));
 }
 async function mutate(path,data){const value=await request(path,data);if(value.items)paint(value,true);else await load();return value;}
 async function run(fn){try{$('chores-status').textContent='';await fn();}catch(error){$('chores-status').textContent=error.message;}}
 function clear(){state={items:[]};signature='';$('chores-list').replaceChildren();$('chores-status').textContent='';$('chore-id').value='';$('chore-title').value='';$('chore-delay').value='2';$('chore-unit').value='weeks';$('chore-delay').max='52';$('chore-repeat').value='1';$('chore-enabled').checked=true;}
 $('chore-form').onsubmit=event=>{event.preventDefault();if(saving)return;setSaving(true);return run(async()=>{try{if(!$('chore-id').value)$('chore-id').value=newId();const body={title:$('chore-title').value,interval_days:Number($('chore-delay').value)*($('chore-unit').value==='weeks'?7:1),repeat_days:Number($('chore-repeat').value),enabled:$('chore-enabled').checked};if($('chore-id').value)body.id=$('chore-id').value;await mutate('/chores/save',body);edit();$('chores-status').textContent='Chore saved.';}finally{setSaving(false);}});};
 $('chore-unit').onchange=()=>{$('chore-delay').max=$('chore-unit').value==='weeks'?'52':'365';};
 $('chore-new').onclick=()=>edit();$('chores-refresh').onclick=()=>run(load);
 $('chores-panel').addEventListener('toggle',event=>{if(event.target.open)run(load);});
 const previous=$('dashboard-forget').onclick;$('dashboard-forget').onclick=()=>{previous();clear();};
 return {load:()=>run(load),update:items=>paint({...state,items}),request,interval,describe,items:()=>state.items};
})();
