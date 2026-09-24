const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const get=async(path)=>{const r=await fetch(path);if(!r.ok)throw new Error(await r.text());return r.json()};
const post=async(path,body={})=>{const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json()};
const render=async()=>{
 try{
  const [items,m]=await Promise.all([get("/api/v1/agent-workflows"),get("/api/v1/agent-workflows/metrics")]);
  const $=id=>document.getElementById(id);
  $("agent-wf-summary").textContent=items.length+" durable workflow(s)";
  $("agent-wf-total").textContent=m.workflow_count;
  $("agent-wf-active").textContent=m.active_workflow_count;
  $("agent-wf-completed").textContent=m.status_counts.completed;
  $("agent-wf-failed").textContent=m.status_counts.failed;
  $("agent-wf-list").innerHTML=items.length?items.map(w=>{
   const terminal=["completed","cancelled"].includes(w.status);
   const controls=w.status==="ready"||w.status==="draft"?'<button class="ghost" data-aw="dispatch">Dispatch</button>':w.status==="running"?'<button class="ghost" data-aw="pause">Pause</button><button class="ghost" data-aw="cancel">Cancel</button>':w.status==="paused"?'<button class="ghost" data-aw="resume">Resume</button>':w.status==="failed"?'<button class="ghost" data-aw="retry">Retry failed</button>':'';
   return '<article class="job-row"><div class="job-main"><div class="job-title"><span class="job-dot '+esc(w.status)+'"></span><b>'+esc(w.objective)+'</b></div><small>'+esc(w.status)+' · '+w.items.filter(i=>i.status==="completed").length+'/'+w.items.length+' workstreams · parallel '+w.max_parallel+'</small></div><div class="job-actions">'+controls+'</div></article>'
  }).join(""):'<div class="empty">No agent workflows yet. The API is ready for durable orchestration plans.</div>';
  document.querySelectorAll("[data-aw]").forEach(b=>b.onclick=async()=>{
   const row=b.closest(".job-row"), index=[...document.querySelectorAll(".job-row")].indexOf(row), w=items[index]; if(!w)return;
   try{
    if(b.dataset.aw==="dispatch")await post("/api/v1/agent-workflows/"+w.workflow_id+"/dispatch");
    else if(b.dataset.aw==="pause")await post("/api/v1/agent-workflows/"+w.workflow_id+"/pause");
    else if(b.dataset.aw==="resume")await post("/api/v1/agent-workflows/"+w.workflow_id+"/resume");
    else if(b.dataset.aw==="cancel")await post("/api/v1/agent-workflows/"+w.workflow_id+"/cancel");
    else if(b.dataset.aw==="retry"){const failed=w.items.find(i=>i.status==="failed");if(failed)await post("/api/v1/agent-workflows/"+w.workflow_id+"/items/"+failed.item_id+"/retry")}
    await render();
   }catch(e){console.error(e)}
  });
 }catch(e){const el=document.getElementById("agent-wf-summary");if(el)el.textContent="Orchestration service unavailable"}};
document.addEventListener("DOMContentLoaded",()=>{document.getElementById("agent-wf-refresh")?.addEventListener("click",render);render();setInterval(render,5000)});
