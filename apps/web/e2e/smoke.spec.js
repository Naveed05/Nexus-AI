import { test, expect } from "@playwright/test";

test("NEXUS browser smoke: workspace, chat, and Data Autopilot", async ({ page }) => {
  const userId = "e2e-" + Date.now();
  await page.addInitScript((id) => localStorage.setItem("nexus-user-id", id), userId);

  await page.route("**/api/v1/byok/credentials", async route => {
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({preferred:"groq",providers:[{provider:"groq",configured:true,masked_key:"gsk-****"}]})});
  });
  await page.route("**/api/v1/jobs", async route => {
    if(route.request().method()!=="POST") return route.continue();
    await route.fulfill({status:202,contentType:"application/json",body:JSON.stringify({job_id:"00000000-0000-0000-0000-000000000001",status:"queued",objective:"E2E chat smoke",retries:0,max_retries:3})});
  });
  await page.route("**/api/v1/jobs/00000000-0000-0000-0000-000000000001", async route => {
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({job_id:"00000000-0000-0000-0000-000000000001",status:"queued",retries:0,max_retries:3})});
  });
  await page.route("**/api/v1/jobs/00000000-0000-0000-0000-000000000001/stream", async route => {
    await route.fulfill({status:200,headers:{"Content-Type":"text/event-stream","Cache-Control":"no-cache"},body:"event: job\ndata: "+JSON.stringify({job_id:"00000000-0000-0000-0000-000000000001",status:"completed",retries:0,max_retries:3,result:{output:"E2E response delivered successfully.",model:"groq/test-model",verification_passed:true,tool_calls:0,grounding_score:1}})+"\n\n"});
  });

  await page.route("**/api/v1/models/arena", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        models: [
          {key:"groq-gpt-oss-120b",model_id:"openai/gpt-oss-120b",provider:"groq",description:"E2E model",context_window:131072,supports_tools:true,configured:true,available:true,latency_ms:12,cost_score:4,latency_score:2},
          {key:"nemotron-3-super-120b-a12b",model_id:"nvidia/nemotron-3-super-120b-a12b",provider:"nemotron",description:"E2E Nemotron",context_window:1000000,supports_tools:true,configured:true,available:true,latency_ms:18,cost_score:1,latency_score:3}
        ]
      })
    });
  });
  await page.route("**/api/v1/models/arena/run", async route => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        prompt:"E2E arena benchmark",
        results:[{model:"nemotron-3-super-120b-a12b",model_id:"nvidia/nemotron-3-super-120b-a12b",provider:"nemotron",status:"completed",latency_ms:25,output:"Evidence-backed benchmark response",output_chars:34,assertion_score:1,matched_assertions:["evidence"]}],
        completed:1,failed:0,skipped:0
      })
    });
  });

  await page.goto("/");
  await expect(page.locator("#connection-status")).toHaveText("Operational",{timeout:15000});
  await expect(page.locator("#chat-provider-pill")).toHaveText("Provider: GROQ");

  page.once("dialog",async d=>await d.accept("E2E Workspace"));
  await page.locator("#new-workspace-btn").click();
  await expect(page.locator("#workspace-select option")).toHaveCount(2,{timeout:10000});
  await page.locator("#workspace-select").selectOption({index:1});
  await page.locator("#chat-attach-btn").click();
  await expect(page).toHaveURL(/#workspace/);
  await page.locator("[data-nav='overview']").click();

  await page.locator("#task-input").fill("E2E chat smoke");
  await page.locator("#execute-btn").click();
  await expect(page.locator(".chat-message.assistant")).toContainText("E2E response delivered successfully.",{timeout:10000});
  await expect(page.locator(".chat-message.assistant")).toContainText("Verified");

  await page.route("**/api/v1/workspaces/*/files", async route => {
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify([{filename:"e2e-dataset.csv",dataset_id:"11111111-1111-1111-1111-111111111111",size_bytes:1234}])});
  });
  await page.route("**/api/v1/datasets/11111111-1111-1111-1111-111111111111/intelligence/profile", async route => {
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({rows:11,columns:3,duplicate_rows:0,memory_estimate_bytes:512,column_profiles:[{name:"age",dtype:"Int64",null_count:0,null_ratio:0,unique_count:11},{name:"income",dtype:"Int64",null_count:0,null_ratio:0,unique_count:11},{name:"churn",dtype:"Int64",null_count:0,null_ratio:0,unique_count:2}],quality:{null_columns:[],constant_columns:[],quality_flags:{}}})});
  });
  await page.route("**/api/v1/datasets/11111111-1111-1111-1111-111111111111/intelligence/analyze", async route => {
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({result:{problem:{type:"classification",confidence:0.8},cleaning_plan:[],recommendations:["Establish a baseline model for target 'churn'."],correlations:[{feature_a:"age",feature_b:"income",correlation:1}],eda:{numeric:{age:{median:24,outlier_count_iqr:0,min:20,max:29}}}}})});
  });
  await page.route("**/api/v1/datasets/11111111-1111-1111-1111-111111111111/intelligence/baseline", async route => {
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({result:{model:"logistic_regression",train_rows:8,test_rows:3,metrics:{accuracy:0.667}}})});
  });

  await page.locator("[data-nav='data-lab']").click();
  await expect(page).toHaveURL(/#data-lab/);
  await expect(page.locator("#data-lab-dataset")).toHaveValue("11111111-1111-1111-1111-111111111111");
  await page.locator("#data-lab-target").selectOption("churn");
  await page.locator("#data-autopilot-run").click();
  await expect(page.locator("#dl-quality")).toHaveText("100/100");
  await expect(page.locator("#dl-problem")).toHaveText("classification");
  await expect(page.locator("#dl-model-badge")).toHaveText("Benchmarked");
  await expect(page.locator("#dl-trace li")).toHaveCount(6);
  await expect(page.locator("#data-lab-status")).toContainText("Data Autopilot complete");

  await page.locator("[data-nav='evaluation']").click();
  await expect(page).toHaveURL(/#evaluation/);
  await expect(page.locator("#model-arena-list")).toContainText("NVIDIA/NEMOTRON");
  await page.locator("#model-arena-prompt").fill("E2E arena benchmark");
  await page.locator("#model-arena-expected").fill("evidence");
  await page.locator(".model-arena-check[value="nemotron-3-super-120b-a12b"]").check();
  await page.locator("#model-arena-run").click();
  await expect(page.locator("#model-arena-results")).toContainText("Evidence-backed benchmark response");
  await expect(page.locator("#model-arena-run-status")).toContainText("1 completed");
});
