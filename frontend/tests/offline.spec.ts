import { test, expect } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

async function fieldMission(request: APIRequestContext) {
  const missions = await (await request.get("/api/missions")).json();
  for (const m of missions.filter(
    (m: { code: string; status: string }) =>
      m.code.startsWith("OFF-") && m.status === "in_field",
  )) {
    await request.post("/api/missions/" + m.id + "/complete", {
      data: { version: m.version, note: "End previous isolated test." },
    });
  }
  const seed = await (
    await request.get(
      "/api/missions/" +
        missions.find((m: { code: string }) => m.code === "FM-002").id,
    )
  ).json();
  const plan = {
    code: seed.code,
    name: seed.name,
    destination: seed.destination,
    station: seed.station,
    vehicle_id: seed.vehicle_id,
    personnel_ids: seed.personnel.map((p: { id: string }) => p.id),
    departure: "2000-01-01T08:00:00Z",
    expected_check_in: "2000-01-01T09:00:00Z",
    expected_return: "2000-01-01T10:00:00Z",
  };
  expect(
    (
      await request.put("/api/missions/" + seed.id, {
        data: { ...plan, version: seed.version },
      })
    ).ok(),
  ).toBeTruthy();
  const now = Date.now();
  const result = await request.post("/api/missions", {
    data: {
      ...plan,
      code: "OFF-" + now,
      name: "Offline field test",
      departure: new Date(now).toISOString(),
      expected_check_in: new Date(now + 3600000).toISOString(),
      expected_return: new Date(now + 7200000).toISOString(),
    },
  });
  expect(result.status()).toBe(201);
  const mission = await result.json();
  const departed = await request.post(
    "/api/missions/" + mission.id + "/depart",
    { data: { version: mission.version } },
  );
  expect(departed.ok()).toBeTruthy();
  return departed.json();
}
async function prepare(page: Page, code: string) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Save mission pack", exact: true })
    .click();
  await expect(page.getByText(/Mission pack saved/)).toBeVisible();
  await expect(page.getByText(/App shell cached/)).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => Boolean(navigator.serviceWorker.controller)),
    )
    .toBeTruthy();
  await page.getByRole("button", { name: "View " + code, exact: true }).click();
}
async function checkIn(page: Page, note: string) {
  await page
    .getByRole("button", { name: "Record check-in", exact: true })
    .click();
  await page.getByLabel("Check-in note", { exact: true }).fill(note);
  await page.getByRole("button", { name: "Save record", exact: true }).click();
}
test("offline reload preserves reports, maps and delivery state before safe manual delivery", async ({
  page,
  context,
  request,
}) => {
  const mission = await fieldMission(request);
  await prepare(page, mission.code);
  await context.setOffline(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .getByRole("button", { name: "View " + mission.code, exact: true })
    .click();
  await checkIn(page, "Recorded while disconnected.");
  await expect(page.getByText("1 undelivered", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Record position", exact: true })
    .click();
  await page.getByLabel("Latitude", { exact: true }).fill("-70.78");
  await page.getByLabel("Longitude", { exact: true }).fill("11.76");
  await page.getByRole("button", { name: "Save record", exact: true }).click();
  await expect(page.getByText("2 undelivered", { exact: true })).toBeVisible();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .getByRole("button", { name: "View " + mission.code, exact: true })
    .click();
  await expect(
    page.getByText("Recorded while disconnected.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Position: -70.78°, 11.76°", { exact: true }),
  ).toBeVisible();
  const server = await (
    await request.get("/api/missions/" + mission.id)
  ).json();
  expect(server.check_ins).toHaveLength(0);
  expect(server.last_position).toBeNull();
  // The saved mission with an existing confirmed position also retains its bounded map offline.
  await page.getByRole("button", { name: "Missions", exact: true }).click();
  await page.getByRole("button", { name: "View FM-001", exact: true }).click();
  await expect(page.getByLabel("Offline demo coordinate map")).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".offline-map img")
        .evaluate(
          (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "test-results/phase3-offline.png",
    fullPage: true,
  });
  await context.setOffline(false);
  await page
    .getByRole("button", { name: "Send pending reports", exact: true })
    .click();
  await expect(page.getByText("0 undelivered", { exact: true })).toBeVisible();
  const accepted = await (
    await request.get("/api/missions/" + mission.id)
  ).json();
  expect(accepted.check_ins).toHaveLength(1);
  expect(accepted.last_position.latitude).toBe(-70.78);
  await page.reload();
  await page.getByText("Delivery history (2)", { exact: true }).click();
  await expect(page.locator(".delivery-acknowledged")).toHaveCount(2);
});
test("lost acknowledgement is retried without a duplicate", async ({
  page,
  request,
}) => {
  const mission = await fieldMission(request);
  await prepare(page, mission.code);
  await page.route(
    "**/api/missions/" + mission.id + "/check-ins",
    async (route) => {
      await route.fetch();
      await route.abort("failed");
    },
  );
  await checkIn(page, "Receipt lost after server accepted.");
  await expect(page.getByText("1 undelivered", { exact: true })).toBeVisible();
  await expect
    .poll(
      async () =>
        (await (await request.get("/api/missions/" + mission.id)).json())
          .check_ins.length,
    )
    .toBe(1);
  await page.unroute("**/api/missions/" + mission.id + "/check-ins");
  await page
    .getByRole("button", { name: "Send pending reports", exact: true })
    .click();
  await expect(page.getByText("0 undelivered", { exact: true })).toBeVisible();
  expect(
    (await (await request.get("/api/missions/" + mission.id)).json()).check_ins,
  ).toHaveLength(1);
});
test("storage failure rolls back the report and queue together", async ({
  page,
  request,
}) => {
  const mission = await fieldMission(request);
  await page.addInitScript(() => {
    const add = IDBObjectStore.prototype.add;
    IDBObjectStore.prototype.add = function (...args: Parameters<typeof add>) {
      if (this.name === "outbox")
        throw new DOMException("Simulated storage full", "QuotaExceededError");
      return add.apply(this, args);
    };
  });
  await prepare(page, mission.code);
  await checkIn(page, "Do not lose this draft.");
  await expect(page.getByLabel("Check-in note", { exact: true })).toHaveValue(
    "Do not lose this draft.",
  );
  await expect(page.getByRole("alert").last()).toContainText(
    "Local storage is unavailable",
  );
  const counts = await page.evaluate(
    () =>
      new Promise<number[]>((resolve, reject) => {
        const open = indexedDB.open("polaris-local-v1");
        open.onerror = () => reject(open.error);
        open.onsuccess = () => {
          const tx = open.result.transaction(["reports", "outbox"], "readonly");
          const a = tx.objectStore("reports").count();
          const b = tx.objectStore("outbox").count();
          tx.oncomplete = () => {
            resolve([a.result, b.result]);
            open.result.close();
          };
        };
      }),
  );
  expect(counts).toEqual([0, 0]);
  expect(
    (await (await request.get("/api/missions/" + mission.id)).json()).check_ins,
  ).toHaveLength(0);
});
test("a conflicting queued report remains visible and never silently overwrites the server", async ({
  page,
  context,
  request,
}) => {
  const mission = await fieldMission(request);
  await prepare(page, mission.code);
  await context.setOffline(true);
  await checkIn(page, "Offline report with an older mission version.");
  expect(
    (
      await request.post("/api/missions/" + mission.id + "/check-ins", {
        data: {
          version: mission.version,
          source: "radio",
          observed_at: new Date().toISOString(),
          note: "Other station update",
        },
      })
    ).status(),
  ).toBe(201);
  await context.setOffline(false);
  await page
    .getByRole("button", { name: "Send pending reports", exact: true })
    .click();
  await expect(page.locator(".local-reports .delivery-failed")).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "View " + mission.code, exact: true })
    .click();
  await expect(
    page.getByText("Offline report with an older mission version.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/missions/" + mission.id)).json()).check_ins,
  ).toHaveLength(1);
});
test.afterEach(async ({ request }) => {
  const missions = await (await request.get("/api/missions")).json();
  for (const m of missions.filter(
    (m: { code: string; status: string }) =>
      m.code.startsWith("OFF-") && m.status === "in_field",
  ))
    await request.post("/api/missions/" + m.id + "/complete", {
      data: { version: m.version, note: "Isolated offline test finished." },
    });
});
