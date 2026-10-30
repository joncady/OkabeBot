'use strict';
(() => {
 const root=document.getElementById('private-storage-controls');if(!root)return;
 const form=document.createElement('form'),enabled=document.createElement('input');enabled.type='checkbox';
 const label=document.createElement('label');label.append(enabled,document.createTextNode(' Automatically delete old local recordings and trim diagnostic logs'));form.append(label);
 const controls={};
 for(const [key,title,max] of [['recordings_days','Recording retention (days)',365],['recordings_mb','Recording budget (MB)',4096],['logs_days','Log retention (days)',365],['logs_mb','Log budget (MB)',4096]]){
  const row=document.createElement('label'),input=document.createElement('input');input.type='number';input.min='1';input.max=String(max);input.required=true;row.append(document.createTextNode(title),input);form.append(row);controls[key]=input;
 }
 const save=document.createElement('button');save.textContent='Save storage policy';form.append(save);
 const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Refresh usage';
 const status=document.createElement('p');status.setAttribute('role','status');
 const scope=document.createElement('p');scope.className='hint';scope.textContent='Opt-in deletion of old local recordings and trimming of diagnostic logs. Excludes databases, models, voice references, exports, backups and Pi storage. Saving limits never starts recording.';
 root.append(scope,form,refresh,status);
 async function request(path,body){
  const token=dashboardAccess.token();if(!token)throw Error('Connect this browser first');
  const response=await fetch(path,{method:'POST',headers:{'X-Hardware-Token':token,'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
  const value=await response.json();if(token!==dashboardAccess.token())throw Error('Access changed');if(!response.ok)throw Error(value.error||'Storage request failed');return value;
 }
 function paint(value){
  enabled.checked=value.policy.enabled;for(const [key,input] of Object.entries(controls))input.value=value.policy[key];
  status.textContent=Object.entries(value.usage).map(([kind,v])=>`${kind}: ${v.files} files · ${(v.bytes/1048576).toFixed(1)} MB`).join(' · ')+(value.usage_complete?'':' · partial scan')+(value.policy.enabled?(value.last_cleanup?.state==='unavailable'?' · cleanup unavailable':' · automatic cleanup enabled'):' · automatic cleanup off');
 }
 async function load(){try{paint(await request('/storage/usage',{}));}catch(e){status.textContent=e.message;}}
 form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{const policy={enabled:enabled.checked};for(const [key,input]of Object.entries(controls))policy[key]=Number(input.value);paint(await request('/storage/policy',policy));}catch(e){status.textContent=e.message;}finally{save.disabled=false;}};
 refresh.onclick=load;
 document.getElementById('private-storage-panel')?.addEventListener('toggle',event=>{if(event.target.open)load();});
 const previous=document.getElementById('dashboard-forget').onclick;
 document.getElementById('dashboard-forget').onclick=()=>{previous();enabled.checked=false;for(const input of Object.values(controls))input.value='';status.textContent='Connect this browser first';};
})();
