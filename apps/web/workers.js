const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function renderWorkers(){
 try{
  const [workers,m]=await Promise.all([fetch("/api/v1/workers").then(r=>r.json()),fetch("/api/v1/workers/metrics").then(r=>r.json())]);
  document.getElementById("worker-summary").textContent=m.worker_count+" registered worker(s)";
  document.getElementById("worker-total").textContent=m.worker_count;
  document.getElementById("worker-online").textContent=m.online_count;
  document.getElementById("worker-busy").textContent=m.busy_count;
  document.getElementById("worker-idle").textContent=m.idle_count;
  document.getElementById("worker-list").innerHTML=workers.length?workers.map(w=>'<article class="job-row"><div class="job-main"><div class="job-title"><span class="job-dot '+esc(w.status)+'"></span><b>'+esc(w.name)+'</b></div><small>'+esc(w.status)+' · '+esc(w.capabilities.join(", ")||"general")+' · '+(w.current_job_id?"busy":"idle")+'</small></div><div class="job-actions">'+(w.status==="online"?'<button class="ghost" data-worker-drain="'+w.worker_id+'">Drain</button>':"")+'</div></article>').join(""):'<div class="empty">No workers registered.</div>';
  document.querySelectorAll("[data-worker-drain]").forEach(b=>b.onclick=async()=>{await fetch("/api/v1/workers/"+b.dataset.workerDrain+"/drain",{method:"POST"});renderWorkers()});
 }catch(e){const x=document.getElementById("worker-summary");if(x)x.textContent="Worker service unavailable"}
}
document.addEventListener("DOMContentLoaded",()=>{document.getElementById("worker-refresh")?.addEventListener("click",renderWorkers);renderWorkers();setInterval(renderWorkers,5000)});
