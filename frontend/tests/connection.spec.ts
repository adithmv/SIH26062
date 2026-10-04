import { test, expect } from "@playwright/test";

test("check a backend, edit settings and disconnect without auto reconnect on reload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Data Management", exact: true }).click();
  const panel = page.getByRole("region", { name: "Device connection" });
  await panel.getByLabel("Other device address").fill(process.env.CONNECTION_TEST_ADDRESS || "http://127.0.0.1:8000");
  await panel.getByRole("combobox", { name: "Automatic checks" }).selectOption("0");
  await panel.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("Reachable");
  await expect(panel).toContainText("Response time:");
  await expect(page.getByRole("region", { name: "Other device / Base", exact: true })).toContainText("Backend reachable");
  await panel.getByLabel("Other device address").fill("http://127.0.0.1:1");
  await expect(panel).toContainText("Address or interval changed");
  await panel.getByRole("button", { name: "Apply and reconnect" }).click();
  await expect(panel.getByRole("status")).toHaveText("Unreachable", { timeout: 15000 });
  await panel.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("Not connected");
  await page.reload();
  await page.getByRole("button", { name: "Data Management", exact: true }).click();
  await expect(panel.getByLabel("Other device address")).toHaveValue("http://127.0.0.1:1");
  await expect(panel.getByRole("status")).toHaveText("Not connected");
});

test("disconnect during a check cannot show an old successful result", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/connection/check", async route => {
    await gate;
    await route.fulfill({ json: { address: "http://localhost:8000", reachable: true, message: "Health check passed", checked_at: new Date().toISOString(), response_ms: 5, version: "0.3.0" } }).catch(() => {});
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Data Management", exact: true }).click();
  const panel = page.getByRole("region", { name: "Device connection" });
  await panel.getByLabel("Other device address").fill("http://localhost:8000");
  const sent = page.waitForRequest("**/api/connection/check");
  await panel.getByRole("button", { name: "Connect", exact: true }).click();
  await sent;
  await panel.getByRole("button", { name: "Disconnect", exact: true }).click();
  release();
  await expect(panel.getByRole("status")).toHaveText("Not connected");
  await expect(panel.getByRole("button", { name: "Check now" })).toBeDisabled();
});

test("automatic checks update the status when the other device stops responding", async ({ page }) => {
  await page.clock.install();
  let checks = 0;
  await page.route("**/api/connection/check", route => {
    checks++;
    return route.fulfill({ json: { address: "http://localhost:8000", reachable: checks === 1, message: checks === 1 ? "Health check passed" : "Cannot reach the other backend.", checked_at: new Date().toISOString(), response_ms: checks === 1 ? 5 : null, version: checks === 1 ? "0.3.0" : null } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Data Management", exact: true }).click();
  const panel = page.getByRole("region", { name: "Device connection" });
  await panel.getByLabel("Other device address").fill("http://localhost:8000");
  await panel.getByRole("combobox", { name: "Automatic checks" }).selectOption("15");
  await panel.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("Reachable");
  await page.clock.runFor(16000);
  await expect(panel.getByRole("status")).toHaveText("Unreachable");
  expect(checks).toBe(2);
  await panel.getByRole("button", { name: "Disconnect", exact: true }).click();
  await page.clock.runFor(31000);
  expect(checks).toBe(2);
});
