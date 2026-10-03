import { test, expect } from "@playwright/test";

// Runs against the disposable browser-test backend, never the user's live database.
test("store, classify, encrypt and restore a file", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Data Management", exact: true }).click();
  await expect(page.getByRole("region", { name: "This device", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Other device / Base", exact: true })).toContainText("Not connected");
  const name = `file-test-${Date.now()}.txt`;
  await expect(page.getByLabel("Add a file")).toBeEnabled();
  await page.getByLabel("Add a file").setInputFiles({ name, mimeType: "text/plain", buffer: Buffer.from("disposable roundtrip check") });
  await expect(page.getByText("File stored locally. Its location is shown below.")).toBeVisible();
  await page.getByRole("row").filter({ hasText: name }).getByRole("button", { name: "Edit data level" }).click();
  await page.getByRole("combobox", { name: "Importance", exact: true }).selectOption("critical");
  await page.getByRole("combobox", { name: "Confidentiality", exact: true }).selectOption("confidential");
  await page.getByRole("button", { name: "Save data level", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Data level saved" })).toBeVisible();
  await page.getByRole("button", { name: "Use this file" }).click();
  await page.getByRole("combobox", { name: "Encrypt this file?", exact: true }).selectOption("yes");
  await page.getByLabel("Encryption password", { exact: true }).fill("temporary test password");
  await page.getByLabel("Confirm password", { exact: true }).fill("temporary test password");
  await page.getByRole("button", { name: "Create prepared copy" }).click();
  await expect(page.getByText("Prepared copy saved locally. The original is unchanged. Nothing was sent to base.")).toBeVisible();
  await page.getByLabel("Password to restore an encrypted copy").fill("temporary test password");
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Restore and download" }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe(name);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString()).toBe("disposable roundtrip check");
  await page.getByRole("button", { name: "Prepared copies", exact: true }).click();
  await expect(page.getByRole("region", { name: "This device", exact: true })).toContainText(`${name}.gz.pemenc`);
});
