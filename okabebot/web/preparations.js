/* Owner-only local drafts. No provider actions or automatic retries; logout clears content. */
(function(){
'use strict';
const panel=document.querySelector('#preparation-panel');if(!panel)return;
const list=document.querySelector('#preparation-list'),status=document.querySelector('#preparation-status');
let dirty=false,loading=false,epoch=0;
function clearPrivate(){epoch++;list.replaceChildren();document.querySelector('#preparation-items').value='';status.textContent='';}
async function request(path,data){
 const generation=epoch,token=dashboardAccess.token();
 if(!token){clearPrivate();throw Error('Owner dashboard access required');}
 const response=await fetch(path,{method:data?'POST':'GET',cache:'no-store',headers:{'X-Hardware-Token':token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});
 if(response.status===403){clearPrivate();dashboardAccess.required();throw Error('Owner dashboard access required');}
 const result=await response.json();
 if(generation!==epoch||token!==dashboardAccess.token())throw Error('Dashboard access changed');
 if(!response.ok)throw Error(result.error||'Preparation unavailable');
 dashboardAccess.remember();return result;
}
document.querySelector('#dashboard-forget').addEventListener('click',clearPrivate);
const tell=message=>{status.textContent=message;};
function render(result){
 list.replaceChildren();
 tell(result.state?'Enable private Amadeus setup to prepare drafts.':'Local drafts only. No retailer account is changed and nothing is ordered. Drafts expire after one day.');
 for(const job of result.jobs||[]){
  const card=document.createElement('section'),heading=document.createElement('h3'),state=document.createElement('p');
  heading.textContent=job.title;state.textContent=job.status.replaceAll('_',' ');card.append(heading,state);
  const items=document.createElement('ul');for(const item of job.items||[]){const row=document.createElement('li');row.textContent=item;items.append(row);}card.append(items);
  for(const[action,label]of(job.status==='awaiting_review'?[['save','Keep draft'],['dismiss','Dismiss']]:['running','blocked'].includes(job.status)?[['cancel','Cancel']]:[])){
   const button=document.createElement('button');button.type='button';button.textContent=label;
   button.onclick=async()=>{button.disabled=true;try{await request('/preparations/update',{action,id:job.id,revision:job.revision});await load();}catch(e){tell(e.message+' Refresh drafts before another decision.');}};card.append(button);
  }list.append(card);
 }
}
async function load(){
 if(loading)return;loading=true;
 try{const[drafts,motion]=await Promise.all([request('/preparations'),request('/presentation/motion')]);render(drafts);
  if(!dirty){document.querySelector('#motion-enabled').checked=motion.enabled;document.querySelector('#motion-reduced').checked=motion.reduced_motion;}
 }catch(e){tell(e.message);}finally{loading=false;}
}
panel.addEventListener('toggle',()=>{if(panel.open)load();});
document.querySelector('#preparation-refresh').onclick=load;
document.querySelector('#preparation-form').onsubmit=async e=>{e.preventDefault();const button=e.currentTarget.querySelector('button');button.disabled=true;
 try{await request('/preparations/update',{action:'draft_list',items:document.querySelector('#preparation-items').value.split('\n').map(s=>s.trim()).filter(Boolean)});await load();}
 catch(error){tell(error.message+' Refresh before retrying; no request is replayed automatically.');}finally{button.disabled=false;}
};
document.querySelector('#motion-form').onchange=()=>{dirty=true;};
document.querySelector('#motion-form').onsubmit=async e=>{e.preventDefault();try{await request('/presentation/motion',{enabled:document.querySelector('#motion-enabled').checked,reduced_motion:document.querySelector('#motion-reduced').checked});dirty=false;tell('Animation settings saved.');}catch(error){tell(error.message);}};
setInterval(()=>{if(panel.open)load();},5000);
})();
