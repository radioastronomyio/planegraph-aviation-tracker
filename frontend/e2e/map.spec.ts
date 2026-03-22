import { test, expect } from "@playwright/test";
import {
  FULL_STATE_FIXTURE,
  DIFFERENTIAL_UPDATE_FIXTURE,
  DIFFERENTIAL_ADD_FIXTURE,
} from "./fixtures";

// WebSocket mock URL — must match what the app connects to
const WS_PATH = "/api/ws/live";

test.describe("Planegraph SPA — Map View", () => {
  test("NavBar renders with correct links", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      // Immediately close without sending data — tests navbar presence only
      ws.close();
    });

    await page.goto("/");
    const nav = page.getByTestId("navbar");
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link", { name: "Map" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Settings" })).toBeVisible();
  });

  test("Map container renders on home route", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      ws.close();
    });

    await page.goto("/");
    const mapView = page.getByTestId("map-view");
    await expect(mapView).toBeVisible();
  });

  test("Aircraft count is 0 before FULL_STATE", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (_ws) => {
      // Do not send anything
    });

    await page.goto("/");
    // Wait briefly for mount
    await page.waitForTimeout(200);
    const countEl = page.getByTestId("aircraft-count");
    await expect(countEl).toContainText("0 aircraft");
  });

  test("Aircraft count updates after FULL_STATE injection", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      ws.send(JSON.stringify(FULL_STATE_FIXTURE));
    });

    await page.goto("/");
    const countEl = page.getByTestId("aircraft-count");
    // FULL_STATE_FIXTURE has 2 aircraft
    await expect(countEl).toContainText("2 aircraft", { timeout: 5000 });
  });

  test("Aircraft count updates after DIFFERENTIAL_UPDATE removes aircraft", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      ws.send(JSON.stringify(FULL_STATE_FIXTURE));
      // After a short delay, send differential update that removes b56789
      setTimeout(() => {
        ws.send(JSON.stringify(DIFFERENTIAL_UPDATE_FIXTURE));
      }, 200);
    });

    await page.goto("/");
    // Should reach 1 aircraft after removal
    const countEl = page.getByTestId("aircraft-count");
    await expect(countEl).toContainText("1 aircraft", { timeout: 5000 });
  });

  test("Aircraft count updates after DIFFERENTIAL_UPDATE adds aircraft", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      ws.send(JSON.stringify(FULL_STATE_FIXTURE));
      setTimeout(() => {
        ws.send(JSON.stringify(DIFFERENTIAL_ADD_FIXTURE));
      }, 200);
    });

    await page.goto("/");
    // FULL_STATE has 2, differential adds 1 → 3
    const countEl = page.getByTestId("aircraft-count");
    await expect(countEl).toContainText("3 aircraft", { timeout: 5000 });
  });

  test("WebSocket connected status shows after FULL_STATE", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      ws.send(JSON.stringify(FULL_STATE_FIXTURE));
    });

    await page.goto("/");
    const statusEl = page.getByTestId("ws-status");
    await expect(statusEl).toHaveAttribute("data-connected", "true", { timeout: 5000 });
  });

  test("Dashboard page renders placeholder", async ({ page }) => {
    await page.goto("/dashboard");
    const dashPage = page.getByTestId("dashboard-page");
    await expect(dashPage).toBeVisible();
    await expect(dashPage.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("Settings page renders placeholder", async ({ page }) => {
    await page.goto("/settings");
    const settingsPage = page.getByTestId("settings-page");
    await expect(settingsPage).toBeVisible();
    await expect(settingsPage.getByRole("heading", { name: "Settings" })).toBeVisible();
  });
});

test.describe("Planegraph SPA — OSM Attribution", () => {
  test("OSM attribution is present in the map", async ({ page }) => {
    await page.routeWebSocket(WS_PATH, (ws) => {
      ws.close();
    });

    await page.goto("/");
    // Static attribution overlay in MapView always renders OpenStreetMap credit
    const attrib = page.getByTestId("osm-attribution");
    await expect(attrib).toBeVisible({ timeout: 5000 });
    await expect(attrib).toContainText("OpenStreetMap");
  });
});
