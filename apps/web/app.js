const $=id=>document.getElementById(id);
const api={async get(path,headers={}){const r=await fetch(path,{headers:{Accept:"application/json","X-Nexus-User-ID":LOCAL_USER_ID,...headers}});if(!r.ok)throw new Error(await r.text());return r.json()},async post(path,body,headers={}){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Nexus-User-ID":LOCAL_USER_ID,...headers},body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json()},async put(path,body,headers={}){const r=await fetch(path,{method:"PUT",headers:{"Content-Type":"application/json","X-Nexus-User-ID":LOCAL_USER_ID,...headers},body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json()},async del(path,headers={}){const r=await fetch(path,{method:"DELETE",headers:{"X-Nexus-User-ID":LOCAL_USER_ID,...headers}});if(!r.ok&&r.status!==204)throw new Error(await r.text());return true}};
const LOCAL_USER_ID=localStorage.getItem("nexus-user-id")||("local-"+crypto.randomUUID());localStorage.setItem("nexus-user-id",LOCAL_USER_ID);
const state={runs:[],agents:[],workspace:null,theme:localStorage.getItem("nexus-theme")||"light",runFilter:"",providerConfigured:false};let deferredInstallPrompt=null;
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
function toast(message,type="ok"){const el=document.createElement("div");el.className="toast "+type;el.textContent=message;$("toast-stack").appendChild(el);setTimeout(()=>el.remove(),3200)}
function setTheme(){document.documentElement.classList.toggle("light",state.theme==="light");$("theme-label").textContent=state.theme==="light"?"Light":"Dark";$("theme-btn").setAttribute("aria-label","Switch to "+(state.theme==="light"?"dark":"light")+" appearance");localStorage.setItem("nexus-theme",state.theme)}
async function loadApiSettings(){
  try{
    const data=await api.get("/api/v1/byok/credentials");
    const openai=data.providers?.find(x=>x.provider==="openai");
    state.providerConfigured=Boolean(openai?.configured||openai?.server_configured);
    const title=$("provider-status-title"),detail=$("provider-status-detail"),dot=$("provider-dot"),banner=$("setup-banner");
    if(state.providerConfigured){
      if(title)title.textContent="OpenAI is connected";
      if(detail)detail.textContent="Your local provider key is configured. NEXUS can run jobs.";
      if(dot)dot.classList.add("connected");
      if(banner)banner.hidden=true;
    }else{
      if(title)title.textContent="No AI provider connected";
      if(detail)detail.textContent="Connect an API key to run AI work.";
      if(dot)dot.classList.remove("connected");
      if(banner)banner.hidden=false;
    }
  }catch(e){
    const detail=$("provider-status-detail");if(detail)detail.textContent="Could not read provider status.";
  }
}
async function saveApiKey(){
  const provider=$("provider-select").value,key=$("provider-api-key").value.trim(),msg=$("settings-message");
  if(!key){if(msg)msg.textContent="Paste an API key first.";return}
  const btn=$("save-api-key");btn.disabled=true;
  try{const data=await api.put("/api/v1/byok/credentials/"+encodeURIComponent(provider),{api_key:key});$("provider-api-key").value="";if(msg)msg.textContent=provider.toUpperCase()+" connected as "+data.masked_key;toast("AI provider connected");await loadApiSettings();activateView("overview")}
  catch(e){if(msg)msg.textContent="Could not save the key. "+e.message;toast("Provider setup failed","error")}
  finally{btn.disabled=false}
}
async function removeApiKey(){
  const provider=$("provider-select").value;
  try{await api.del("/api/v1/byok/credentials/"+encodeURIComponent(provider));if($("settings-message"))$("settings-message").textContent=provider.toUpperCase()+" key removed.";toast("Provider disconnected");await loadApiSettings()}
  catch(e){toast("Could not remove provider","error")}
}
function setStatusPill(id,label,tone="ok"){const el=$(id);if(!el)return;el.textContent=label;el.classList.remove("status-warning","status-danger","status-neutral");if(tone==="warning")el.classList.add("status-warning");if(tone==="danger")el.classList.add("status-danger");if(tone==="neutral")el.classList.add("status-neutral")}
function activateView(id){const target=$(id)||$("overview");document.querySelectorAll(".view-section").forEach(x=>x.classList.toggle("active",x===target));document.querySelectorAll("[data-nav]").forEach(x=>x.classList.toggle("active",x.dataset.nav===target.id));$("page-title").textContent=target.id==="control-center"?"Control center":target.id==="agent-workspace"?"Agent workspace":target.id.charAt(0).toUpperCase()+target.id.slice(1);history.replaceState(null,"","#"+target.id);closeMobile();if(target.id==="settings")loadApiSettings()}
function route(){activateView(location.hash.slice(1)||"overview")}
function closeMobile(){$("sidebar").classList.remove("open");$("mobile-scrim").classList.remove("open")}
function openMobile(){$("sidebar").classList.add("open");$("mobile-scrim").classList.add("open")}
async function loadProduct(){try{const [profile,usage,templates]=await Promise.all([api.get("/api/v1/product/profile"),api.get("/api/v1/product/usage"),api.get("/api/v1/product/templates")]);$("template-grid").innerHTML=templates.map(t=>'<div class="template-card"><h4>'+esc(t.name)+'</h4><p>'+esc(t.description)+'</p><button data-template="'+esc(t.template_id)+'">Use workflow</button></div>').join("");document.querySelectorAll("[data-template]").forEach(b=>b.onclick=async()=>{const t=await api.get("/api/v1/product/templates/"+encodeURIComponent(b.dataset.template));$("task-input").value=t.objective;activateView("overview");$("task-input").focus()})}catch(e){$("template-grid").innerHTML='<div class="empty">Workflow catalog unavailable.</div>'}}
async function loadIntelligence(){try{const [models,caps]=await Promise.all([api.get("/api/v1/models"),api.get("/api/v1/tools/capabilities")]);$("model-grid").innerHTML=models.map(m=>'<div class="model-card"><strong>'+esc(m.model_id)+'</strong><small>'+esc(m.provider)+' · '+esc(m.tier)+' · '+(m.health.available?"ready":"degraded")+'</small></div>').join("");$("capability-list").innerHTML=caps.capabilities.map(c=>'<span class="capability">'+esc(c)+'</span>').join("");$("model-count").textContent=models.filter(m=>m.health.available).length+" / "+models.length}catch(e){$("model-grid").innerHTML='<div class="empty">Model catalog unavailable.</div>'}}
async function loadAgents(){try{const data=await api.get("/api/v1/agents");state.agents=data.agents||data.items||[];$("agent-count-badge").textContent=state.agents.length+" AGENTS";$("agent-grid").innerHTML=state.agents.map(a=>'<article class="agent-card"><div class="agent-top"><b>'+esc(a.role||a.agent_id||"Agent")+'</b><i class="agent-dot"></i></div><p>'+esc(a.description||a.capabilities?.join(" · ")||"Specialist agent available to the collaboration runtime.")+'</p></article>').join("")||'<div class="empty">No agents exposed.</div>'}catch(e){$("agent-grid").innerHTML='<div class="empty">Agent catalog unavailable.</div>'}}
async function loadWorkspaces(){try{const ws=await api.get("/api/v1/workspaces"),select=$("workspace-select"),current=select.value;select.innerHTML='<option value="">No workspace selected</option>'+ws.map(w=>'<option value="'+esc(w.workspace_id)+'">'+esc(w.name)+'</option>').join("");select.value=ws.some(w=>w.workspace_id===current)?current:(ws[0]?.workspace_id||"");state.workspace=select.value||null;await loadWorkspaceData()}catch(e){$("workspace-status").textContent="Workspace service unavailable."}}
async function createWorkspace(){const name=prompt("Workspace name","My NEXUS workspace");if(!name?.trim())return;try{await api.post("/api/v1/workspaces",{name:name.trim()});await loadWorkspaces();toast("Workspace created")}catch(e){toast("Could not create workspace","error")}}
async function loadFiles(){const id=state.workspace;if(!id){$("file-list").innerHTML='<div class="empty">Create or select a workspace first.</div>';return}try{const files=await api.get("/api/v1/workspaces/"+id+"/files");$("file-list").innerHTML=files.length?files.map(f=>'<div class="file-item"><span>'+esc(f.filename)+'</span><span class="file-size">'+f.size_bytes+' bytes</span></div>').join(""):'<div class="empty">No files in this workspace.</div>';$("workspace-status").textContent=files.length+" file(s) available as context."}catch(e){$("workspace-status").textContent="Could not load files."}}
async function loadMemories(){const id=state.workspace;if(!id){$("memory-list").innerHTML='<div class="empty">Select a workspace to view memory.</div>';return}try{const memories=await api.get("/api/v1/workspaces/"+id+"/memories");$("memory-list").innerHTML=memories.slice().reverse().slice(0,10).map(m=>'<div class="memory-item">'+esc(m.content)+'<small>'+esc(m.memory_kind)+' · importance '+m.importance+'</small></div>').join("")||'<div class="empty">No memories yet.</div>'}catch(e){$("memory-list").innerHTML='<div class="empty">Memory unavailable.</div>'}}
async function loadWorkspaceData(){await Promise.all([loadFiles(),loadMemories()]);const id=state.workspace;$("knowledge-summary").textContent=id?"Workspace "+id.slice(0,12)+" · live context":"No workspace selected";$("knowledge-detail").innerHTML=id?'<div class="file-item"><span>Active workspace</span><span class="file-size">'+esc(id)+'</span></div>':'<div class="empty">Select a workspace to inspect its context.</div>'}
async function saveMemory(){const id=state.workspace,c=$("memory-input").value.trim();if(!id||!c){toast("Select a workspace and enter a memory","error");return}try{await api.post("/api/v1/memories",{workspace_id:id,content:c,memory_kind:"fact",source:"frontend"});$("memory-input").value="";await loadMemories();toast("Memory saved")}catch(e){toast("Could not save memory","error")}}
async function recallMemory(){const id=state.workspace,q=$("memory-query").value.trim();if(!id||!q){toast("Select a workspace and enter a query","error");return}try{const r=await api.post("/api/v1/workspaces/"+id+"/memories/recall",{query:q,top_k:5});$("memory-list").innerHTML=r.matches.map(m=>'<div class="memory-item">'+esc(m.content)+'<small>relevance '+Number(m.relevance).toFixed(3)+' · confidence '+Number(m.confidence).toFixed(3)+'</small></div>').join("")||'<div class="empty">No matching memory.</div>'}catch(e){toast("Recall failed","error")}}
async function uploadFile(){const id=state.workspace,file=$("file-input").files[0];if(!id||!file)return;$("workspace-status").textContent="Uploading "+file.name+"…";const data=new FormData();data.append("file",file);try{const r=await fetch("/api/v1/workspaces/"+id+"/files",{method:"POST",body:data});if(!r.ok)throw new Error(await r.text());$("file-input").value="";await loadFiles();toast("File uploaded")}catch(e){$("workspace-status").textContent="Upload failed.";toast("Upload failed","error")}}


async function workflowCommand(id,action,stepId=null){
 try{
  const payload={action,idempotency_key:crypto.randomUUID()};
  if(stepId)payload.step_id=stepId;
  await api.post("/api/v1/workflows/"+encodeURIComponent(id)+"/commands",payload);
  await loadWorkflows();
  toast("Workflow "+action.replace("_"," ")+" applied");
 }catch(e){toast("Workflow command failed","error")}
}
async function loadWorkflows(){
 try{
  const [items,templates,metrics]=await Promise.all([api.get("/api/v1/workflows"),api.get("/api/v1/workflows/templates"),api.get("/api/v1/workflows/metrics")]);
  $("workflow-summary").textContent=items.length+" workflow(s)";
  $("workflow-metric-total").textContent=metrics.workflow_count;
  $("workflow-metric-active").textContent=metrics.active_workflow_count+" active";
  $("workflow-metric-completed").textContent=metrics.status_counts.completed;
  $("workflow-metric-completion-rate").textContent=(Number(metrics.completion_rate)*100).toFixed(1)+"% terminal completion";
  $("workflow-metric-failed").textContent=metrics.status_counts.failed;
  $("workflow-metric-failure-rate").textContent=(Number(metrics.failure_rate)*100).toFixed(1)+"% terminal failure";
  $("workflow-metric-running").textContent=metrics.step_status_counts.running;
  $("workflow-metric-retry").textContent=metrics.retryable_failed_steps+" failed steps";
  $("workflow-templates").innerHTML=templates.map(t=>'<div class="template-card"><h4>'+esc(t.name)+'</h4><p>'+esc(t.description)+'</p><button data-wft="'+esc(t.template_id)+'">Use template</button></div>').join("");
  $("workflow-list").innerHTML=items.length?items.map(w=>{
   const terminal=["completed","failed","cancelled"].includes(w.status);
   const actions=w.status==="draft"||w.status==="scheduled"?'<button class="ghost" data-wfc="start">Start</button>':w.status==="running"?'<button class="ghost" data-wfc="pause">Pause</button><button class="ghost" data-wfc="cancel">Cancel</button>':w.status==="paused"?'<button class="ghost" data-wfc="resume">Resume</button>':w.status==="failed"?'<button class="ghost" data-wfc="retry">Retry</button>':'';
   return '<article class="job-row"><div class="job-main"><div class="job-title"><span class="job-dot '+esc(w.status)+'"></span><b>'+esc(w.name)+'</b></div><small>'+esc(w.status)+' · '+w.steps.filter(s=>s.status==="completed").length+'/'+w.steps.length+' steps · '+w.event_count+' events</small></div><div class="job-actions">'+actions+'<button class="ghost" data-wf-open="'+esc(w.workflow_id)+'">Inspect</button></div></article>';
  }).join(""):'<div class="empty">No workflows yet.</div>';
  document.querySelectorAll("[data-wf-open]").forEach(b=>b.onclick=async()=>{const w=await api.get("/api/v1/workflows/"+b.dataset.wfOpen);const h=await api.get("/api/v1/workflows/"+b.dataset.wfOpen+"/health");toast(w.name+" · "+h.status+(h.needs_operator?" · operator attention":""));});
  document.querySelectorAll("[data-wfc]").forEach(b=>b.onclick=()=>workflowCommand(b.closest(".job-row").querySelector("[data-wf-open]").dataset.wfOpen,b.dataset.wfc));
  document.querySelectorAll("[data-wft]").forEach(b=>b.onclick=async()=>{const t=templates.find(x=>x.template_id===b.dataset.wft);if(!t)return;const payload={name:t.name,objective:t.description,steps:t.steps.map(s=>({step_id:s.step_id,objective:s.objective,depends_on:s.depends_on||[],risk_level:"low"}))};await api.post("/api/v1/workflows",payload);await loadWorkflows();toast("Workflow created");});
 }catch(e){$("workflow-summary").textContent="Unavailable";$("workflow-list").innerHTML='<div class="empty">Workflow service unavailable.</div>'}
}

async function loadJobs(){
  try{
    const [jobs,summary]=await Promise.all([api.get("/api/v1/jobs?limit=50"),api.get("/api/v1/jobs/summary")]);
    renderJobs(jobs);
    $("job-summary").textContent=summary.total+" total · "+summary.running+" running · "+summary.queued+" queued · "+summary.failed+" failed";
  }catch(e){$("job-summary").textContent="Durable queue unavailable";$("job-list").innerHTML='<div class="empty">Could not load durable jobs.</div>'}
}
function jobTone(status){return status==="failed"||status==="cancelled"?"danger":status==="completed"?"ok":status==="retrying"||status==="paused"?"warning":"neutral"}
function renderJobs(jobs){
  const host=$("job-list");if(!host)return;
  host.innerHTML=jobs.length?jobs.map(j=>{
    const err=j.error?'<small class="job-error">'+esc(j.error)+'</small>':"";
    const retry=j.status==="failed"&&j.retries<j.max_retries?'<button class="ghost" data-job-retry="'+esc(j.job_id)+'">Retry</button>':"";
    return '<article class="job-row"><div class="job-main"><div class="job-title"><span class="job-dot '+esc(j.status)+'"></span><b>'+esc(j.objective)+'</b></div><small>'+esc(j.status)+' · '+j.retries+'/'+j.max_retries+' retries · '+(j.run_id?esc(j.run_id.slice(0,12)):"waiting for run")+'</small>'+err+'</div><div class="job-actions"><span class="status-pill '+(jobTone(j.status)==="danger"?"status-danger":jobTone(j.status)==="warning"?"status-warning":"")+'">'+esc(j.status)+'</span>'+retry+'<button class="ghost" data-job-open="'+esc(j.job_id)+'">Open</button></div></article>';
  }).join(""):'<div class="empty">No durable jobs yet. Start a goal from Home.</div>';
  host.querySelectorAll("[data-job-open]").forEach(b=>b.onclick=()=>inspectJob(b.dataset.jobOpen));
  host.querySelectorAll("[data-job-retry]").forEach(b=>b.onclick=()=>retryJob(b.dataset.jobRetry));
}
async function inspectJob(jobId){
  try{
    const j=await api.get("/api/v1/jobs/"+encodeURIComponent(jobId));
    renderJobDetail(j);
    if(j.status==="queued"||j.status==="running"||j.status==="retrying"){
      if(collabState.jobSource)collabState.jobSource.close();
      const source=new EventSource("/api/v1/jobs/"+encodeURIComponent(jobId)+"/stream");
      collabState.jobSource=source;
      source.addEventListener("job",e=>{try{const next=JSON.parse(e.data);renderJobDetail(next);if(["completed","failed","cancelled"].includes(next.status)){source.close();collabState.jobSource=null;loadJobs();loadHealth();}}catch(err){console.error(err)}});
      source.addEventListener("error",()=>{source.close();collabState.jobSource=null;setTimeout(()=>inspectJob(jobId),3000)});
    }
  }catch(e){toast("Could not inspect job","error")}
}
function renderJobDetail(j){
  const status=j.status||"unknown";
  $("job-summary").textContent=status+" · "+(j.retries||0)+"/"+(j.max_retries||0)+" retries";
  if(status==="completed"&&j.result?.output){renderRunResult(j.result);$("result-meta").textContent="Job "+j.job_id.slice(0,12)+" · Run "+(j.run_id||"—")+" · "+(j.result.tool_calls||0)+" tools";toast("Durable job completed","ok")}
}
async function cancelJob(jobId){try{await api.post("/api/v1/jobs/"+encodeURIComponent(jobId)+"/cancel",{});await loadJobs();toast("Job cancelled")}catch(e){toast("Could not cancel job","error")}}
async function retryJob(jobId){try{await api.post("/api/v1/jobs/"+encodeURIComponent(jobId)+"/retry",{});await loadJobs();toast("Job queued for retry")}catch(e){toast("Retry unavailable","error")}}
function renderRuns(runs){state.runs=runs||[];const list=$("runs-list");const filtered=state.runs.filter(r=>(r.objective||"").toLowerCase().includes(state.runFilter.toLowerCase())||(r.status||"").toLowerCase().includes(state.runFilter.toLowerCase()));if(!filtered.length){list.innerHTML=state.runs.length?'<div class="empty">No executions match that filter.</div>':'<div class="empty">No executions yet. Give NEXUS its first goal.</div>';return}list.innerHTML=filtered.slice().reverse().slice(0,12).map(r=>'<div class="run-row"><div class="run-objective">'+esc(r.objective||"Untitled task")+'</div><div class="run-state">'+esc(r.status)+'</div><div class="run-id">'+esc((r.run_id||"").slice(0,10))+'</div></div>').join("")}
async function loadHealth(){try{const [health,models,runs]=await Promise.all([api.get("/api/v1/production/health"),api.get("/api/v1/models"),api.get("/api/v1/runs")]);$("connection-status").textContent="Operational";$("sidebar-health").textContent="Operational";$("sidebar-health-dot").style.background="var(--accent-2)";$("active-runs").textContent=health.runs.active;$("completed-runs").textContent=health.runs.completed;$("failed-runs").textContent=health.runs.failed;$("capacity").textContent=health.runtime.capacity_available+" capacity available";$("model-count").textContent=models.filter(m=>m.health.available).length+" / "+models.length;$("last-sync").textContent="Updated "+new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});renderRuns(runs)}catch(e){$("connection-status").textContent="Offline";$("sidebar-health").textContent="Offline";$("sidebar-health-dot").style.background="var(--danger)";setStatusPill("control-status","Unavailable","danger");$("last-sync").textContent="Runtime unavailable"}}
async function loadControlCenter(){try{const d=await api.get("/api/v1/control-center/summary"),healthy=d.overall_status==="healthy";setStatusPill("control-status",healthy?"Healthy":"Degraded",healthy?"ok":"warning");$("control-headline").textContent=healthy?"NEXUS systems nominal":"Attention required";$("control-summary").textContent=healthy?"All exposed operational surfaces are reporting within the production contract.":"One or more operational surfaces need review.";$("control-run-count").textContent=d.runs.active;$("control-run-detail").textContent=d.runs.total+" total · "+d.runs.failed+" failed";$("control-agent-count").textContent=d.agents.count;$("control-agent-detail").textContent=d.agents.items.map(a=>a.role).join(" · ")||"No agents";$("control-model-count").textContent=d.models.available+" / "+d.models.count;$("control-model-detail").textContent="available";$("control-tool-count").textContent=d.tools.count;$("control-tool-detail").textContent=d.tools.items.filter(t=>t.health.healthy).length+" healthy";$("control-deployment").innerHTML="<strong>"+esc(d.deployment.mode.toUpperCase())+"</strong><span>"+esc(d.deployment.region||"local")+" · "+esc(d.deployment.instance_id||"single-instance")+"</span><small>"+(d.deployment.ready?"Scale contract ready":"Scale contract blocked")+"</small>";$("control-audit").innerHTML="<strong>"+(d.audit.valid?"Verified":"Integrity issue")+"</strong><span>"+d.audit.event_count+" events · head "+d.audit.head_sequence+"</span><small>"+esc(d.audit.error||"Hash chain valid")+"</small>";$("control-timeline").innerHTML=d.runs.recent.length?d.runs.recent.slice(0,8).map(r=>'<div class="timeline-row"><span class="timeline-dot"></span><div><strong>'+esc(r.objective||r.run_id)+'</strong><small>'+esc(r.status)+' · '+(r.steps_completed||0)+' steps · '+(r.tool_calls||0)+' tools</small></div></div>').join(""):'<div class="empty">No execution history yet.</div>';$("control-sync").textContent=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"})}catch(e){setStatusPill("control-status","Unavailable","danger");$("control-summary").textContent="Control center could not be reached."}}
async function execute(){const objective=$("task-input").value.trim();if(!objective){$("task-error").textContent="Tell NEXUS what outcome you want.";return}if(!state.providerConfigured){$("task-error").textContent="Connect an AI provider first. Open Settings → AI provider.";activateView("settings");return}const btn=$("execute-btn");btn.disabled=true;$("task-error").textContent="";btn.querySelector("span").textContent="Queueing…";try{const job=await api.post("/api/v1/jobs",{objective,context:$("context-input").value.trim()||null,risk_level:$("risk-input").value,workspace_id:state.workspace});activateView("jobs");await loadJobs();inspectJob(job.job_id);toast("Durable job queued","ok")}catch(e){$("task-error").textContent="Could not queue job. "+e.message;toast("Job submission failed","error")}finally{btn.disabled=false;btn.querySelector("span").textContent="Run with NEXUS"}}
const commands=[["Home","overview"],["Workspace","workspace"],["Knowledge","knowledge"],["Agents","agents"],["Orchestration","agent-orchestration"],["Workflows","workflows"],["Jobs","jobs"],["Executions","runs"],["Agent workspace","agent-workspace"],["Workers","workers"],["Control center","control-center"],["Evaluation","evaluation"],["Governance","governance"],["Settings","settings"]];
function openCommand(){const modal=$("command-modal");modal.hidden=false;$("command-input").value="";renderCommands("");$("command-input").focus()}
function closeCommand(){ $("command-modal").hidden=true}
function renderCommands(q){const needle=q.toLowerCase();const items=commands.filter(x=>x[0].toLowerCase().includes(needle));$("command-results").innerHTML=items.map((x,i)=>'<div class="command-option '+(i===0?"selected":"")+'" data-command="'+x[1]+'"><span>'+x[0]+'</span><small>Go to surface</small></div>').join("")||'<div class="empty">No matching surface.</div>';document.querySelectorAll("[data-command]").forEach(x=>x.onclick=()=>{activateView(x.dataset.command);closeCommand()})}
$("theme-btn").onclick=()=>{state.theme=state.theme==="dark"?"light":"dark";setTheme()};$("command-btn").onclick=openCommand;$("command-top-btn").onclick=openCommand;$("command-modal").onclick=e=>{if(e.target.id==="command-modal")closeCommand()};$("command-close").onclick=closeCommand;$("command-input").onkeydown=e=>{if(e.key==="Escape"){e.preventDefault();closeCommand()}};$("command-input").oninput=e=>renderCommands(e.target.value);$("mobile-menu").onclick=openMobile;$("mobile-close").onclick=closeMobile;$("mobile-scrim").onclick=closeMobile;$("new-workspace-btn").onclick=createWorkspace;$("setup-provider-btn").onclick=()=>activateView("settings");$("save-api-key").onclick=saveApiKey;$("remove-api-key").onclick=removeApiKey;$("toggle-api-key").onclick=()=>{const input=$("provider-api-key");input.type=input.type==="password"?"text":"password"};$("settings-theme-btn").onclick=()=>{state.theme=state.theme==="light"?"dark":"light";setTheme()};$("workspace-select").onchange=async e=>{state.workspace=e.target.value||null;await loadWorkspaceData()};$("file-input").onchange=uploadFile;$("save-memory-btn").onclick=saveMemory;$("recall-btn").onclick=recallMemory;$("execute-btn").onclick=execute;$("refresh-btn").onclick=async()=>{await Promise.all([loadHealth(),loadControlCenter(),loadAgents()]);toast("Telemetry refreshed")};$("runs-refresh").onclick=loadHealth;$("jobs-refresh").onclick=loadJobs;$("run-filter").oninput=e=>{state.runFilter=e.target.value.trim();renderRuns(state.runs)};$("download-artifact-btn").onclick=()=>toast("Artifact download started");$("copy-result-btn").onclick=async()=>{const value=$("result-output").textContent.trim();if(!value)return;try{await navigator.clipboard.writeText(value);toast("Result copied")}catch(e){toast("Copy unavailable — select the result manually","error")}};$("install-btn").onclick=async()=>{if(!deferredInstallPrompt)return;deferredInstallPrompt.prompt();await deferredInstallPrompt.userChoice;deferredInstallPrompt=null;$("install-btn").hidden=true};window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();deferredInstallPrompt=e;$("install-btn").hidden=false});$("task-input").onkeydown=e=>{if((e.ctrlKey||e.metaKey)&&e.key==="Enter")execute()};document.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();openCommand()}if(e.key==="Escape")closeCommand();if($("command-modal")&&!$("command-modal").hidden&&["ArrowDown","ArrowUp"].includes(e.key)){e.preventDefault();const options=[...document.querySelectorAll(".command-option")];if(!options.length)return;let i=options.findIndex(x=>x.classList.contains("selected"));i=e.key==="ArrowDown"?Math.min(options.length-1,i+1):Math.max(0,i-1);options.forEach((x,n)=>x.classList.toggle("selected",n===i));options[i].scrollIntoView({block:"nearest"})}if($("command-modal")&&!$("command-modal").hidden&&e.key==="Enter"){const selected=document.querySelector(".command-option.selected");if(selected)selected.click()}});window.addEventListener("hashchange",route);window.addEventListener("error",e=>{toast("NEXUS encountered a frontend error. Refresh to recover.","error");console.error(e.error||e.message)});window.addEventListener("unhandledrejection",e=>{toast("NEXUS encountered an unexpected frontend error.","error");console.error(e.reason)});if("serviceWorker" in navigator){window.addEventListener("load",()=>navigator.serviceWorker.register("/web/sw.js").catch(()=>{}))}
setTheme();route();Promise.allSettled([loadApiSettings(),loadHealth(),loadControlCenter(),loadAgents(),loadWorkspaces(),loadIntelligence(),loadProduct(),loadJobs()]).finally(()=>{const boot=$("boot-screen");if(boot)boot.classList.add("is-ready")});setInterval(loadHealth,15000);setInterval(loadControlCenter,10000);setInterval(loadJobs,5000);
const collabState={requests:[],selectedRun:null,refreshTimer:null,eventSource:null,jobSource:null};
const agentOptions=[["research","Researcher"],["analysis","Analyst"],["coding","Developer"],["writing","Writer"],["verification","Verifier"]];
function renderCollabRequests(){const host=$("collab-request-list");if(!host)return;host.innerHTML=collabState.requests.map((r,i)=>'<div class="collab-request"><input value="'+esc(r.objective)+'" data-collab-objective="'+i+'" placeholder="Specialist objective"><select data-collab-capability="'+i+'">'+agentOptions.map(o=>'<option value="'+o[0]+'" '+(o[0]===r.required_capability?"selected":"")+'>'+o[1]+'</option>').join("")+'</select><button class="icon-button" data-collab-remove="'+i+'" aria-label="Remove specialist">×</button></div>').join("");host.querySelectorAll("[data-collab-objective]").forEach(x=>x.oninput=e=>collabState.requests[Number(x.dataset.collabObjective)].objective=e.target.value);host.querySelectorAll("[data-collab-capability]").forEach(x=>x.onchange=e=>collabState.requests[Number(x.dataset.collabCapability)].required_capability=e.target.value);host.querySelectorAll("[data-collab-remove]").forEach(x=>x.onclick=()=>{collabState.requests.splice(Number(x.dataset.collabRemove),1);renderCollabRequests()})}
function addCollabRequest(){if(collabState.requests.length>=8){toast("Maximum of 8 workstreams","error");return}collabState.requests.push({objective:"",required_capability:"research"});renderCollabRequests()}
async function buildCollabPlan(){const objective=$("collab-objective").value.trim(),requests=collabState.requests.filter(x=>x.objective.trim()).map(x=>({...x,requester:"supervisor"}));if(!objective||!requests.length){toast("Add a goal and at least one specialist objective","error");return}const btn=$("build-collab-btn");btn.disabled=true;try{const d=await api.post("/api/v1/agents/collaborate",{objective,requests});$("collab-result").innerHTML='<div class="plan-banner"><b>Plan ready for approval</b><span>'+esc(d.workstreams.length)+' bounded workstream(s) · approval '+(d.approval_required?"required":"not required")+'</span></div>'+d.workstreams.map((w,i)=>'<div class="plan-row"><span class="plan-index">'+String(i+1).padStart(2,"0")+'</span><div><b>'+esc(w.agent_id)+'</b><small>'+esc(w.objective)+'</small></div><span class="status-pill">'+esc(w.status||"pending")+'</span></div>').join("");toast("Collaboration plan built")}catch(e){toast("Could not build collaboration plan","error");$("collab-result").innerHTML='<div class="empty">The collaboration request was rejected safely.</div>'}finally{btn.disabled=false}}
function renderArtifactDelivery(artifactId){const download=$("download-artifact-btn"),open=$("open-artifact-btn"),status=$("artifact-status");if(!download)return;if(!artifactId){download.hidden=true;open.hidden=true;status.textContent="No downloadable artifact was produced.";return}const url="/api/v1/artifacts/"+encodeURIComponent(artifactId)+"/download";download.hidden=false;open.hidden=false;download.href=url;download.setAttribute("download","nexus-result.txt");open.onclick=()=>window.open(url,"_blank","noopener");status.textContent="Durable execution artifact · "+artifactId.slice(0,12)+"…"}
function renderRunResult(result){
  const data=result?.result||result;
  $("result-panel").hidden=false;if(!data||!data.output)return false;
  $("result-panel").hidden=false;
  $("result-output").textContent=data.output;
  $("verification-pill").textContent=data.verification_passed?"✓ Verified":"Needs review";
  $("result-meta").textContent="Run "+(result.run_id||"—")+" · "+(data.model||"runtime")+" · "+(data.tool_calls||0)+" tool calls · grounding "+(data.grounding_score??"—");renderArtifactDelivery(data.artifact_id);
  return true;
}
function renderRunSnapshot(r){
  const status=r.status||"unknown",active=["created","running"].includes(status);
  $("live-run-title").textContent=r.metadata?.objective?String(r.metadata.objective).slice(0,72):"Run "+r.run_id.slice(0,12);
  $("live-run-subtitle").textContent=active?"Live execution · connected to runtime stream":"Execution finished";
  setStatusPill("live-run-status",status,status==="failed"||status==="cancelled"?"danger":active?"ok":status==="completed"?"ok":"neutral");
  $("cancel-run-btn").disabled=!active;$("open-run-result").disabled=!r.metadata?.result;
  const steps=Number(r.steps_completed||0),calls=Number(r.tool_calls||0),retries=Number(r.retries||0);
  const progress=active?Math.min(92,Math.max(8,steps*12)):status==="completed"||status==="failed"||status==="cancelled"?100:20;
  $("run-progress-bar").style.width=progress+"%";$("run-progress-phase").textContent=active?(steps?"Executing":"Preparing"):status;
  $("run-progress-count").textContent=steps+" steps · "+calls+" tools · "+retries+" retries";
  $("run-detail-grid").innerHTML='<div><small>Status</small><b>'+esc(status)+'</b></div><div><small>Run ID</small><b>'+esc(r.run_id)+'</b></div><div><small>Workspace</small><b>'+esc(r.metadata?.workspace_id||"—")+'</b></div><div><small>Started</small><b>'+esc(r.started_at||"—")+'</b></div><div><small>Finished</small><b>'+esc(r.finished_at||"—")+'</b></div><div><small>Duration</small><b>'+esc(r.duration_ms==null?"—":r.duration_ms+" ms")+'</b></div>';
  $("run-inspector-output").textContent=r.error?"Error: "+r.error:JSON.stringify(r.metadata?.result||r.metadata||{},null,2);
  const events=Array.isArray(r.metadata?.result?.events)?r.metadata.result.events:(Array.isArray(r.metadata?.events)?r.metadata.events:[]);
  $("run-timeline").innerHTML=(events.length?events:steps?Array.from({length:Math.min(steps,8)},(_,i)=>"step_"+(i+1)):[status]).map((e,i)=>'<div class="run-event '+(i<steps?"done":"")+'"><span></span><div><b>'+esc(String(e).replaceAll("_"," "))+'</b><small>'+((i<steps)?"Completed":active?"Current state":"Runtime state")+'</small></div></div>').join("");
  if(r.metadata?.result)renderRunResult(r.metadata.result);
}
async function inspectRun(runId){
  if(!runId)return;
  collabState.selectedRun=runId;
  if(collabState.eventSource){collabState.eventSource.close();collabState.eventSource=null}
  try{
    const r=await api.get("/api/v1/runs/"+encodeURIComponent(runId));
    renderRunSnapshot(r);
    if(["created","running"].includes(r.status)){
      const source=new EventSource("/api/v1/runs/"+encodeURIComponent(runId)+"/stream");
      collabState.eventSource=source;
      source.addEventListener("run",e=>{try{const next=JSON.parse(e.data);renderRunSnapshot(next);if(!["created","running"].includes(next.status)){source.close();collabState.eventSource=null;loadHealth()}}catch(err){console.error(err)}});
      source.addEventListener("error",()=>{source.close();collabState.eventSource=null;clearTimeout(collabState.refreshTimer);collabState.refreshTimer=setTimeout(()=>inspectRun(runId),3000)});
    }
  }catch(e){toast("Could not inspect run","error")}
}
function renderWorkspaceRuns(){const host=$("workspace-run-list");if(!host)return;const runs=state.runs.slice().reverse().slice(0,12);host.innerHTML=runs.length?runs.map(r=>'<button class="workspace-run-row '+(r.run_id===collabState.selectedRun?"selected":"")+'" data-inspect-run="'+esc(r.run_id)+'"><span class="run-state-dot '+esc(r.status)+'"></span><div><b>'+esc(r.objective||"Execution")+'</b><small>'+esc(r.status)+' · '+esc(r.run_id.slice(0,10))+'</small></div><span>→</span></button>').join(""):'<div class="empty">No executions yet.</div>';host.querySelectorAll("[data-inspect-run]").forEach(x=>x.onclick=()=>inspectRun(x.dataset.inspectRun))}
async function cancelSelectedRun(){if(!collabState.selectedRun)return;if(!confirm("Cancel this active NEXUS run?"))return;try{await api.post("/api/v1/runs/"+encodeURIComponent(collabState.selectedRun)+"/cancel",{});toast("Run cancellation requested");await inspectRun(collabState.selectedRun);await loadHealth()}catch(e){toast("Could not cancel run","error")}}
function initAgentWorkspace(){if(!$("agent-workspace"))return;$("add-collab-request").onclick=addCollabRequest;$("build-collab-btn").onclick=buildCollabPlan;$("cancel-run-btn").onclick=cancelSelectedRun;$("workspace-refresh").onclick=async()=>{await loadHealth();renderWorkspaceRuns();toast("Workspace refreshed")};$("open-run-result").onclick=()=>{activateView("runs");if(collabState.selectedRun)inspectRun(collabState.selectedRun)};if(!collabState.requests.length){collabState.requests=[{objective:"Gather relevant evidence",required_capability:"research"},{objective:"Verify the final result",required_capability:"verification"}];renderCollabRequests()}}
const originalRenderRuns=renderRuns;renderRuns=function(runs){originalRenderRuns(runs);renderWorkspaceRuns()};
initAgentWorkspace();

if($("workflow-refresh")) $("workflow-refresh").onclick=loadWorkflows;
loadWorkflows();
