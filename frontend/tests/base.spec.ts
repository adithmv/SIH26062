import { test, expect } from "@playwright/test";

test("base login gate, stock workflow and logout do not expose field caches", async ({ page }) => {
  // Browser contract test: server-side authorization is tested against real sessions in pytest.
  let signedIn = false;
  await page.route("**/api/auth/session", route => route.fulfill({ json: { mode: "base", user: signedIn ? { username: "test-operator", role: "operator" } : null } }));
  await page.route("**/api/auth/login", route => { signedIn = true; return route.fulfill({ json: { username: "test-operator", role: "operator" } }); });
  await page.route("**/api/auth/logout", route => { signedIn = false; return route.fulfill({ json: { signed_out: true } }); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Base station sign-in" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toHaveCount(0);
  await page.getByLabel("Username", { exact: true }).fill("test-operator");
  await page.getByLabel("Password", { exact: true }).fill("test-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await page.getByText("Add stock item", { exact: true }).click();
  const code = "TEST-" + Date.now();
  await page.getByLabel("Item code", { exact: true }).fill(code);
  await page.getByLabel("Item name", { exact: true }).fill("Browser test supply");
  await page.getByLabel("Station", { exact: true }).fill("Test station");
  await page.getByLabel("Unit (such as litres)", { exact: true }).fill("units");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: code });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Adjust stock" }).click();
  await page.getByLabel("Quantity change (negative for stock used)").fill("5");
  await page.getByLabel("Reason / action taken").fill("Isolated browser verification");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(row.getByRole("cell", { name: "5", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Base station sign-in" })).toBeVisible();
  await expect(page.getByText(code, { exact: true })).toHaveCount(0);
});

test("base viewer cannot see resource creation controls", async ({ page }) => {
  await page.route("**/api/auth/session", route => route.fulfill({ json: { mode: "base", user: { username: "viewer", role: "viewer" } } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(page.getByText("Add stock item", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Adjust stock" })).toHaveCount(0);
});
