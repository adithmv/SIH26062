import { test, expect } from "@playwright/test";
test("loads seeded missions and navigates related records", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Expedition overview" }),
  ).toBeVisible();
  await expect(page.getByText("Ice survey / sector 07")).toBeVisible();
  await page.screenshot({ path: "test-results/overview.png", fullPage: true });
  await page.getByRole("button", { name: "View FM-001" }).click();
  await expect(
    page.getByRole("heading", { name: "Mission briefing" }),
  ).toBeVisible();
  await expect(page.getByText("Asha Rao")).toBeVisible();
  await expect(page.getByText("simulated_gnss")).toBeVisible();
  await page.getByRole("button", { name: "Personnel", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Expedition personnel" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Mira Shah" })).toBeVisible();
  await page.getByRole("button", { name: "Vehicles", exact: true }).click();
  await expect(page.getByRole("heading", { name: "PB-01" })).toBeVisible();
});
test("shows an actionable error instead of invented data", async ({ page }) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 503, body: "{}" }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Unable to load data");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});
test("mobile navigation stays usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Missions", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "View FM-001" }),
  ).toBeAttached();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
