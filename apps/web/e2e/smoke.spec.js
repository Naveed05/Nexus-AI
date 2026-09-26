import { test, expect } from "@playwright/test";

test("NEXUS browser smoke: load, workspace, upload, and chat delivery", async ({ page }) => {
  const userId = "e2e-" + Date.now();
  await page.addInitScript((id) => localStorage.setItem("nexus-user-id", id), userId);

  await page.route("**/api/v1/byok/credentials", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        preferred: "groq",
        providers: [{ provider: "groq", configured: true, masked_key: "gsk-****" }]
      })
    });
  });

  let uploaded = false;
  await page.route("**/api/v1/workspaces/*/files", async (route) => {
    if (route.request().method() === "POST") {
      uploaded = true;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          file_id: "00000000-0000-0000-0000-000000000002",
          filename: "e2e-context.txt",
          size_bytes: 28,
          dataset_id: null,
          dataset_ready: false
        })
      });
      return;
    }
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(uploaded ? [{
          file_id: "00000000-0000-0000-0000-000000000002",
          filename: "e2e-context.txt",
          size_bytes: 28,
          dataset_id: null
        }] : [])
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/v1/jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "00000000-0000-0000-0000-000000000001",
        status: "queued",
        objective: "E2E chat smoke",
        retries: 0,
        max_retries: 3
      })
    });
  });

  await page.route("**/api/v1/jobs/00000000-0000-0000-0000-000000000001", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "00000000-0000-0000-0000-000000000001",
        status: "queued",
        retries: 0,
        max_retries: 3
      })
    });
  });

  await page.route("**/api/v1/jobs/00000000-0000-0000-0000-000000000001/stream", async (route) => {
    const completed = {
      job_id: "00000000-0000-0000-0000-000000000001",
      status: "completed",
      retries: 0,
      max_retries: 3,
      result: {
        output: "E2E response delivered successfully.",
        model: "groq/test-model",
        verification_passed: true,
        tool_calls: 0,
        grounding_score: 1
      }
    };
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: "event: job\ndata: " + JSON.stringify(completed) + "\n\n"
    });
  });

  await page.goto("/");
  await expect(page.locator("#connection-status")).toHaveText("Operational", { timeout: 15000 });
  await expect(page.locator("#chat-provider-pill")).toHaveText("Provider: GROQ");

  page.once("dialog", async (dialog) => await dialog.accept("E2E Workspace"));
  await page.locator("#new-workspace-btn").click();
  await expect(page.locator("#workspace-select option")).toHaveCount(2, { timeout: 10000 });

  await page.locator("#workspace-select").selectOption({ index: 1 });
  await page.locator("#file-input").setInputFiles({
    name: "e2e-context.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("NEXUS E2E context document.")
  });
  await expect(page.locator("#file-list")).toContainText("e2e-context.txt", { timeout: 10000 });

  await page.locator("#task-input").fill("E2E chat smoke");
  await page.locator("#execute-btn").click();
  await expect(page.locator(".chat-message.assistant")).toContainText(
    "E2E response delivered successfully.",
    { timeout: 10000 }
  );
  await expect(page.locator(".chat-message.assistant")).toContainText("Verified");
});
