'use strict';
const dashboardAccess=(()=>{
 const key='okabebot-dashboard-access',panel=document.querySelector('#dashboard-auth'),form=document.querySelector('#dashboard-auth-form');
 let token=location.hash.slice(1)||localStorage.getItem(key)||'';
 function remember(){
  if(!token)return;
  localStorage.setItem(key,token);panel.hidden=true;
  if(location.hash)history.replaceState(null,'',location.pathname+location.search);
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
 return {token:()=>token,remember,required};
})();
