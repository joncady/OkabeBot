'use strict';
const dashboardAccess=(()=>{
 const key='okabebot-dashboard-access',panel=document.querySelector('#dashboard-auth'),form=document.querySelector('#dashboard-auth-form');
 const fragment=location.hash.slice(1),section=new Set(['companion-dashboard','locations-dashboard','daily-tools','notification-settings','amadeus-controls','amadeus-feeds','amadeus-morning','amadeus-habits','amadeus-memory']).has(fragment);
 const invalidFragment=Boolean(fragment)&&!section&&!/^[A-Za-z0-9_-]{32,128}$/.test(fragment);
 let token=invalidFragment?'':fragment&&!section?fragment:localStorage.getItem(key)||'';
 function remember(){
  if(!token)return;
  localStorage.setItem(key,token);panel.hidden=true;
  if(location.hash.slice(1)===token)history.replaceState(null,'',location.pathname+location.search);
 }
 function required(){panel.hidden=false;}
 form.onsubmit=async e=>{
  e.preventDefault();const input=document.querySelector('#dashboard-access');
  let candidate=input.value.trim();
  try{if(candidate.includes('://'))candidate=new URL(candidate).hash.slice(1);}catch{candidate='';}
  if(!/^[A-Za-z0-9_-]{32,128}$/.test(candidate)){document.querySelector('#dashboard-auth-error').textContent='Paste the authorized setup link or access key.';return;}
  try{const response=await fetch('/state',{headers:{'X-Hardware-Token':candidate},cache:'no-store'});if(!response.ok)throw Error();token=candidate;input.value='';document.querySelector('#dashboard-auth-error').textContent='';remember();location.reload();}
  catch{document.querySelector('#dashboard-auth-error').textContent='Access was not accepted. Check the setup link and connection.';}
 };
 document.querySelector('#dashboard-forget').onclick=()=>{localStorage.removeItem(key);token='';required();};
 if(!token)required();
 if(invalidFragment)document.querySelector('#dashboard-auth-error').textContent='Invalid setup key or unknown dashboard section. Check the link.';
 return {token:()=>token,remember,required};
})();
