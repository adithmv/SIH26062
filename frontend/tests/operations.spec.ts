import { test, expect } from "@playwright/test";

test("plans, departs, reports, escalates and returns a field team", async ({
  page,
  request,
}) => {
  // Keep this scenario repeatable without deleting records: move the unused seeded plan into the past.
  const missions = await (await request.get("/api/missions")).json();
  const seed = missions.find((m: { code: string }) => m.code === "FM-002");
  const detail = await (await request.get("/api/missions/" + seed.id)).json();
  const prepared = await request.put("/api/missions/" + seed.id, {
    data: {
      version: detail.version,
      code: detail.code,
      name: detail.name,
      destination: detail.destination,
      station: detail.station,
      vehicle_id: detail.vehicle_id,
      personnel_ids: detail.personnel.map((p: { id: string }) => p.id),
      departure: "2000-01-01T08:00:00Z",
      expected_check_in: "2000-01-01T10:00:00Z",
      expected_return: "2000-01-01T12:00:00Z",
      check_in_interval_minutes: 60,
      overdue_grace_minutes: 15,
    },
  });
  expect(prepared.ok()).toBeTruthy();
  const workerErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && /worker failed/i.test(msg.text()))
      workerErrors.push(msg.text());
  });
  const code = "UI-" + Date.now();
  await page.goto("/");
  await page.getByRole("button", { name: "New mission" }).click();
  await page.getByLabel("Mission code", { exact: true }).fill(code);
  await page
    .getByLabel("Mission name", { exact: true })
    .fill("Browser workflow expedition");
  await page.getByLabel("Destination", { exact: true }).fill("South ridge");
  await page
    .getByLabel("Vehicle", { exact: true })
    .selectOption(detail.vehicle_id);
  await page.getByRole("checkbox", { name: /Mira Shah/ }).check();
  await page.getByRole("checkbox", { name: /Kabir Das/ }).check();
  await page.getByRole("button", { name: "Save mission", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Browser workflow expedition",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit plan", exact: true }).click();
  await page
    .getByLabel("Destination", { exact: true })
    .fill("Revised south ridge");
  await page.getByRole("button", { name: "Save mission", exact: true }).click();
  await expect(
    page.getByText("Destination: Revised south ridge"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Record departure", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Record check-in", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Record check-in", exact: true })
    .click();
  await page
    .getByLabel("Check-in note", { exact: true })
    .fill("All team members accounted for at ridge.");
  await page.getByRole("button", { name: "Save record", exact: true }).click();
  await expect(
    page.getByText("All team members accounted for at ridge.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Record position", exact: true })
    .click();
  await page.getByLabel("Latitude", { exact: true }).fill("-70.78");
  await page.getByLabel("Longitude", { exact: true }).fill("11.76");
  await page.getByRole("button", { name: "Save record", exact: true }).click();
  await expect(page.getByText("-70.7800°, 11.7600°")).toBeVisible();
  await page
    .getByRole("button", { name: "Load online map", exact: true })
    .click();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await expect.poll(() => workerErrors.length).toBe(0);
  await page.screenshot({
    path: "test-results/phase2-mission.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Update escalation", exact: true })
    .click();
  await page
    .getByLabel("Escalation level", { exact: true })
    .selectOption("emergency");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Simulated incident confirmed by operator.");
  await page.getByRole("button", { name: "Save record", exact: true }).click();
  await expect(page.locator(".status.emergency")).toHaveText("emergency");
  await page
    .getByRole("button", { name: "Complete mission", exact: true })
    .click();
  await page
    .getByLabel("Return note", { exact: true })
    .fill("Entire team back at the station.");
  await page
    .getByRole("checkbox", { name: /I confirm all assigned personnel/ })
    .check();
  await page.getByRole("button", { name: "Save record", exact: true }).click();
  await expect(page.locator(".status.completed")).toHaveText("completed");
  await expect(
    page.getByRole("button", { name: "Record check-in", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Personnel", exact: true }).click();
  const person = page.locator("article").filter({
    has: page.getByRole("heading", { name: "Mira Shah", exact: true }),
  });
  await expect(person).toContainText("at station");
});

test("planning form remains usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "New mission" }).click();
  await expect(page.getByLabel("Mission code", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/phase2-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
