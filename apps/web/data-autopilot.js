const apiDL={
  get:async(path)=>{const r=await fetch(path,{headers:{Accept:"application/json","X-Nexus-User-ID":localStorage.getItem("nexus-user-id")||"local-user"}});if(!r.ok)throw new Error(await r.text());return r.json()},
  post:async(path,body)=>{const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Nexus-User-ID":localStorage.getItem("nexus-user-id")||"local-user"},body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json()}
};
const dl$=id=>document.getElementById(id);
const dlEsc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const dlState={datasets:[]};
function dlStatus(message,tone="neutral"){const n=dl$("data-lab-status");if(n){n.textContent=message;n.dataset.tone=tone}}
function dlList(id,items,empty="No evidence available."){const h=dl$(id);if(!h)return;if(!items.length){h.innerHTML='<div class="empty">'+dlEsc(empty)+"</div>";return}h.innerHTML=items.map(x=>'<div class="data-lab-item">'+x+"</div>").join("")}
async function dlLoadTargets(datasetId){
  const target=dl$("data-lab-target");if(!target)return;target.innerHTML='<option value="">No supervised target</option>';if(!datasetId)return;
  try{const p=await apiDL.get("/api/v1/datasets/"+encodeURIComponent(datasetId)+"/intelligence/profile");(p.column_profiles||[]).forEach(c=>target.insertAdjacentHTML("beforeend",'<option value="'+dlEsc(c.name)+'">'+dlEsc(c.name)+"</option>"))}
  catch(e){dlStatus("Could not inspect dataset columns: "+e.message,"error")}
}
async function dlLoadDatasets(){
  const select=dl$("data-lab-dataset"),ws=dl$("workspace-select")?.value;if(!select)return;
  select.innerHTML='<option value="">Select a workspace dataset</option>';dlState.datasets=[];
  if(!ws){dlStatus("Create or select a workspace, then upload a CSV, JSON, or Parquet file.","neutral");return}
  try{const files=await apiDL.get("/api/v1/workspaces/"+encodeURIComponent(ws)+"/files");dlState.datasets=files.filter(f=>f.dataset_id);select.innerHTML+='<option value=""></option>'+dlState.datasets.map(f=>'<option value="'+dlEsc(f.dataset_id)+'">'+dlEsc(f.filename)+"</option>").join("");if(dlState.datasets[0]){select.value=dlState.datasets[0].dataset_id;await dlLoadTargets(select.value)}}catch(e){dlStatus("Dataset inventory unavailable: "+e.message,"error")}
}
function dlQuality(p){const rows=Number(p.rows||0),dup=rows?Math.min(25,Number(p.duplicate_rows||0)/rows*100):0,nulls=(p.column_profiles||[]).reduce((s,c)=>s+Math.min(20,Number(c.null_ratio||0)*100),0),constants=(p.quality?.constant_columns||[]).length*8;return Math.max(0,Math.round(100-dup-Math.min(55,nulls)-Math.min(20,constants)))}
function dlRender(profile,analysis,baseline,target){
  const q=profile.quality||{},score=dlQuality(profile),problem=analysis.problem||{};
  dl$("dl-rows").textContent=Number(profile.rows||0).toLocaleString();dl$("dl-columns").textContent=Number(profile.columns||0).toLocaleString();dl$("dl-shape").textContent=profile.rows+" × "+profile.columns;dl$("dl-quality").textContent=score+"/100";dl$("dl-quality-detail").textContent=score>=85?"Strong starting point":score>=65?"Review before modeling":"Cleaning required";dl$("dl-problem").textContent=problem.type||"descriptive";dl$("dl-problem-detail").textContent=target?"Target: "+target+" · confidence "+Number(problem.confidence||0).toFixed(2):"Exploratory / descriptive mode";
  dlList("dl-quality-list",[
    '<b>Missing values <span class="value">'+(q.null_columns?.length||0)+"</span></b><small>Columns with nulls requiring review.</small>",
    '<b>Duplicate rows <span class="value">'+Number(profile.duplicate_rows||0).toLocaleString()+"</span></b><small>Measured before cleaning.</small>",
    '<b>Constant columns <span class="value">'+(q.constant_columns?.length||0)+"</span></b><small>Features with no observed variation.</small>",
    '<b>Proposed cleaning <span class="value">'+(analysis.cleaning_plan?.length||0)+"</span></b><small>Conservative actions; source data is never overwritten.</small>"
  ]);
  const signals=[];(analysis.correlations||[]).slice(0,6).forEach(c=>signals.push('<b>'+dlEsc(c.feature_a)+" ↔ "+dlEsc(c.feature_b)+' <span class="value">'+Number(c.correlation).toFixed(3)+"</span></b><small>Absolute correlation ranked highest first.</small>"));
  Object.entries(analysis.eda?.numeric||{}).slice(0,4).forEach(([n,v])=>signals.push('<b>'+dlEsc(n)+' <span class="value">'+Number(v.outlier_count_iqr||0)+" outliers</span></b><small>Median "+dlEsc(v.median)+" · range "+dlEsc(v.min)+" to "+dlEsc(v.max)+"</small>"));
  dlList("dl-signals",signals,"No strong numeric signals were found.");
  const b=dl$("dl-baseline"),badge=dl$("dl-model-badge");
  if(baseline){badge.textContent="Benchmarked";badge.classList.remove("status-neutral");b.innerHTML=Object.entries(baseline.metrics||{}).map(([k,v])=>'<div class="data-lab-item"><b>'+dlEsc(k.replaceAll("_"," "))+' <span class="value">'+Number(v).toFixed(4)+"</span></b><small>"+dlEsc(baseline.model)+" · "+baseline.train_rows+" train / "+baseline.test_rows+" test rows</small></div>").join("")}
  else{badge.textContent="Not run";badge.classList.add("status-neutral");b.innerHTML='<div class="empty">'+(target?"Baseline could not be trained for this target.":"Choose a target and rerun Autopilot to benchmark a baseline.")+"</div>"}
  const trace=["Loaded the registered dataset without modifying the source artifact.","Profiled rows, columns, nulls, uniqueness, duplicates, and memory footprint.","Applied conservative in-memory cleaning and recorded the proposed changes.","Computed EDA statistics, IQR outliers, and numeric correlations from the cleaned frame.",target?"Inferred the supervised problem type from the selected target.":"Kept the task descriptive because no target was supplied.",baseline?"Trained a transparent baseline on a held-out test split and recorded its metrics.":"Skipped model training because no target was selected."];
  dl$("dl-trace").innerHTML=trace.map(x=>"<li><span>"+dlEsc(x)+"</span></li>").join("");
  const recs=analysis.recommendations||[];dl$("dl-recommendations").innerHTML=recs.length?recs.map((x,i)=>'<div class="recommendation-card"><b>Experiment '+(i+1)+"</b><span>"+dlEsc(x)+"</span></div>").join(""):'<div class="empty">No additional recommendations.</div>';
  dl$("data-lab-results").hidden=false;
}
async function dlRun(){
  const id=dl$("data-lab-dataset")?.value,target=dl$("data-lab-target")?.value||"",btn=dl$("data-autopilot-run");if(!id){dlStatus("Select a dataset first.","error");return}
  btn.disabled=true;btn.textContent="Analyzing evidence…";dlStatus("Running deterministic profiling, cleaning, EDA and signal detection…");
  try{const profile=await apiDL.get("/api/v1/datasets/"+encodeURIComponent(id)+"/intelligence/profile");const analysis=await apiDL.post("/api/v1/datasets/"+encodeURIComponent(id)+"/intelligence/analyze",target?{target}:{});let baseline=null;if(target){dlStatus("Evidence collected. Benchmarking the transparent baseline model…");try{baseline=await apiDL.post("/api/v1/datasets/"+encodeURIComponent(id)+"/intelligence/baseline",{target})}catch(e){dlStatus("Analysis completed; baseline could not be trained: "+e.message,"warning")}}dlRender(profile,analysis.result||analysis,baseline?.result||baseline,target);dlStatus("Data Autopilot complete — every insight above comes from the registered dataset and deterministic analysis services.","ok")}catch(e){dlStatus("Autopilot failed: "+e.message,"error");dl$("data-lab-results").hidden=true}finally{btn.disabled=false;btn.textContent="Run Data Autopilot →"}
}
function dlBind(){dl$("data-autopilot-run")?.addEventListener("click",dlRun);dl$("data-lab-dataset")?.addEventListener("change",e=>dlLoadTargets(e.target.value));dl$("workspace-select")?.addEventListener("change",dlLoadDatasets);document.querySelector('[data-nav="data-lab"]')?.addEventListener("click",()=>setTimeout(dlLoadDatasets,0));dlLoadDatasets()}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",dlBind);else dlBind();