'use strict';
// Owner-only, read-only notes. Absence and transport errors never imply an all-clear.
const healthSummaryUI=(()=>{
 const panel=document.getElementById('health-panel'),list=document.getElementById('health-summary');
 if(!panel||!list)return {load:async()=>{},clear:()=>{}};
 let visible=false,inflight=false,generation=0;
 function clear(){generation++;list.replaceChildren();panel.hidden=true;}
 async function load(){
  const token=dashboardAccess.token(),epoch=generation;
  if(!token){clear();return;}
  if(inflight)return;
  inflight=true;
  try{
   const response=await fetch('/amadeus/api/health',{method:'GET',headers:{'X-Hardware-Token':token},cache:'no-store'});
   if(epoch!==generation||token!==dashboardAccess.token())return;
   if(!response.ok){clear();if(response.status===403)dashboardAccess.required();return;}
   const value=await response.json();
   if(epoch!==generation||token!==dashboardAccess.token())return;
   list.replaceChildren();
   const status=document.createElement('p');status.textContent=value.privacy||'Health source not configured';list.append(status);
   const readings=Array.isArray(value.readings)?value.readings:[];
   for(const reading of readings){if(reading.metric==='others')continue;const row=document.createElement('p');row.textContent=reading.metric.replaceAll('_',' ')+': '+reading.value+' '+reading.unit;list.append(row);}
   if(!readings.length){const note=document.createElement('p');note.textContent='No fresh selected health readings';list.append(note);}
   if(value.settings?.daily_steps){const goal=document.createElement('p');goal.textContent=value.others_detected?'Health details hidden while others are detected':'Daily step goal: '+value.settings.daily_steps;list.append(goal);}
   panel.hidden=false;
  }catch(_){if(epoch===generation)clear();}
  finally{inflight=false;}
 }
 const required=dashboardAccess.required;dashboardAccess.required=()=>{clear();return required();};
 const forget=document.getElementById('dashboard-forget');
 if(forget){const previous=forget.onclick;forget.onclick=()=>{previous?.();clear();};}
 for(const link of document.querySelectorAll('nav.dashboard-nav a[href="#daily-tools"]'))link.addEventListener('click',()=>{visible=true;load();});
 const today=document.getElementById('daily-tools');
 if(today&&typeof IntersectionObserver!=='undefined'){
  const observer=new IntersectionObserver(entries=>{visible=entries.some(entry=>entry.isIntersecting);if(visible&&!document.hidden)load();});observer.observe(today);
 }
 window.addEventListener('hashchange',()=>{if(location.hash==='#daily-tools'){visible=true;load();}});
 document.addEventListener('visibilitychange',()=>{if(visible&&!document.hidden)load();});
 setInterval(()=>{if(visible&&!document.hidden)load();},60000);
 if(location.hash==='#daily-tools'){visible=true;load();}
 return {load,clear};
})();
