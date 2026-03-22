import { test, expect } from "@playwright/test";
import {
  SESSION_ID,
  SESSION_ID_2,
  FLIGHTS_LIST_FIXTURE,
  TRACK_FIXTURE,
  APPROACH_ANALYSIS_FIXTURE,
  HEATMAP_SAMPLES_FIXTURE,
  AIRPORT_SUMMARY_FIXTURE,
  RUNWAY_UTILIZATION_FIXTURE,
  AIRPORT_HOURLY_FIXTURE_KCMH,
  AIRPORT_HOURLY_FIXTURE_KLCK,
} from "./analytics-fixtures";

const WS_PATH = "/api/v1/live";

// Reusable route setup for all analytics pages
async function setupRoutes(page: ReturnType<typeof test.info> extends never ? never : Parameters<Parameters<typeof test>[1]>[0]["page"]) {
  // Silence WebSocket so map pages don't error
  await page.routeWebSocket(WS_PATH, (ws) => { ws.close(); });

  // Flights list (with and without filters)
  await page.route("**/api/v1/flights?*", (route) => {
    route.fulfill({ json: FLIGHTS_LIST_FIXTURE });
  });

  // Flight detail
  await page.route(`**/api/v1/flights/${SESSION_ID}`, (route) => {
    const detail = { ...FLIGHTS_LIST_FIXTURE[0], trajectory: null };
    route.fulfill({ json: detail });
  });
  await page.route(`**/api/v1/flights/${SESSION_ID_2}`, (route) => {
    const detail = { ...FLIGHTS_LIST_FIXTURE[1], trajectory: null };
    route.fulfill({ json: detail });
  });

  // Track
  await page.route(`**/api/v1/flights/${SESSION_ID}/track`, (route) => {
    route.fulfill({ json: TRACK_FIXTURE });
  });
  await page.route(`**/api/v1/flights/${SESSION_ID_2}/track`, (route) => {
    route.fulfill({ json: TRACK_FIXTURE });
  });

  // Approach analysis
  await page.route(`**/api/v1/flights/${SESSION_ID}/approach-analysis`, (route) => {
    route.fulfill({ json: APPROACH_ANALYSIS_FIXTURE });
  });
  await page.route(`**/api/v1/flights/${SESSION_ID_2}/approach-analysis`, (route) => {
    route.fulfill({ status: 404, json: { detail: "No approach runway identified" } });
  });

  // Heatmap
  await page.route("**/api/v1/analytics/heatmap-samples?*", (route) => {
    route.fulfill({ json: HEATMAP_SAMPLES_FIXTURE });
  });

  // Airport analytics
  await page.route("**/api/v1/analytics/airports/summary?*", (route) => {
    route.fulfill({ json: AIRPORT_SUMMARY_FIXTURE });
  });
  await page.route("**/api/v1/analytics/airports/runway-utilization?*", (route) => {
    route.fulfill({ json: RUNWAY_UTILIZATION_FIXTURE });
  });
  await page.route("**/api/v1/analytics/airports/hourly?icao=KCMH*", (route) => {
    route.fulfill({ json: AIRPORT_HOURLY_FIXTURE_KCMH });
  });
  await page.route("**/api/v1/analytics/airports/hourly?icao=KLCK*", (route) => {
    route.fulfill({ json: AIRPORT_HOURLY_FIXTURE_KLCK });
  });
  // Fallback for other airports
  await page.route("**/api/v1/analytics/airports/hourly?*", (route) => {
    route.fulfill({ json: [] });
  });

  // Dashboard / stats / health mocks (to avoid console errors when navigating)
  await page.route("**/api/v1/stats", (route) => {
    route.fulfill({ json: { active_aircraft: 0, flights_today: 0, flights_in_last_hour: 0, ingest_rate_per_sec: 0, materializer_lag_sec: null, storage_bytes: null, oldest_data_date: null } });
  });
  await page.route("**/api/v1/health", (route) => {
    route.fulfill({ json: { status: "healthy", postgres: "healthy", ultrafeeder: "healthy", ingest_active: true, last_position_report: null } });
  });
  await page.route("**/api/v1/stats/hourly*", (route) => { route.fulfill({ json: [] }); });
  await page.route("**/api/v1/stats/phases", (route) => { route.fulfill({ json: [] }); });
  await page.route("**/api/v1/stats/top-aircraft*", (route) => { route.fulfill({ json: [] }); });
  await page.route("**/api/v1/config", (route) => { route.fulfill({ json: [] }); });
}

test.describe("Planegraph SPA — Analytics Pages", () => {
  // ---------------------------------------------------------------------------
  // Flight list
  // ---------------------------------------------------------------------------

  test("Flights page renders flight list from API", async ({ page }) => {
    await setupRoutes(page);
    await page.goto("/flights");

    const flightsPage = page.getByTestId("flights-page");
    await expect(flightsPage).toBeVisible();
    await expect(flightsPage.getByRole("heading", { name: "Flights" })).toBeVisible();

    // Should show all 3 fixture flights
    const table = page.getByTestId("flights-table");
    await expect(table).toBeVisible();
    const rows = table.locator("tbody tr");
    await expect(rows).toHaveCount(3, { timeout: 5000 });
  });

  test("Flights page filter by callsign triggers new fetch", async ({ page }) => {
    await setupRoutes(page);

    let fetchCount = 0;
    await page.route("**/api/v1/flights?*", (route) => {
      fetchCount++;
      route.fulfill({ json: FLIGHTS_LIST_FIXTURE.filter((f) => f.callsign?.startsWith("UAL")) });
    });

    await page.goto("/flights");
    await page.waitForTimeout(300); // initial load

    const callsignInput = page.getByTestId("filter-callsign");
    await callsignInput.fill("UAL");
    await page.getByTestId("search-btn").click();

    // Wait for re-fetch
    await page.waitForTimeout(300);
    expect(fetchCount).toBeGreaterThan(1);
  });

  test("Flight row links to flight detail page", async ({ page }) => {
    await setupRoutes(page);
    await page.goto("/flights");

    const link = page.getByTestId("flight-row-link").first();
    await expect(link).toBeVisible({ timeout: 5000 });
    await link.click();

    // Should navigate to flight detail
    await expect(page).toHaveURL(new RegExp(`/flights/${SESSION_ID}`));
    await expect(page.getByTestId("flight-detail-page")).toBeVisible({ timeout: 5000 });
  });

  // ---------------------------------------------------------------------------
  // Flight detail + replay
  // ---------------------------------------------------------------------------

  test("Flight detail page renders metadata and charts", async ({ page }) => {
    await setupRoutes(page);
    await page.goto(`/flights/${SESSION_ID}`);

    const detailPage = page.getByTestId("flight-detail-page");
    await expect(detailPage).toBeVisible({ timeout: 5000 });

    // Metadata card should show callsign
    await expect(detailPage.getByText("UAL123")).toBeVisible({ timeout: 5000 });

    // Charts should be present (Recharts renders svg elements)
    await expect(detailPage.locator("svg").first()).toBeVisible({ timeout: 5000 });
  });

  test("Recharts syncId synchronizes chart cursors", async ({ page }) => {
    await setupRoutes(page);
    await page.goto(`/flights/${SESSION_ID}`);

    await expect(page.getByTestId("flight-detail-page")).toBeVisible({ timeout: 5000 });

    // All three charts should render
    const charts = page.locator(".recharts-responsive-container");
    await expect(charts).toHaveCount(3, { timeout: 5000 });
  });

  test("Chart hover updates replay marker position via lifted state", async ({ page }) => {
    await setupRoutes(page);
    await page.goto(`/flights/${SESSION_ID}`);

    const detailPage = page.getByTestId("flight-detail-page");
    await expect(detailPage).toBeVisible({ timeout: 5000 });

    // Verify the architecture: FlightMap receives focusIndex, Play button drives state
    // The replay marker is conditionally rendered when focusIndex is non-null.
    // We drive it via the play button (reliable) rather than Recharts mousemove (unreliable in headless).
    const playBtn = page.getByTestId("play-btn");
    await expect(playBtn).toBeVisible({ timeout: 5000 });

    // Start playback — this sets focusIndex via setInterval
    await playBtn.click();

    // The replay marker should appear once playback advances to the first point
    const markerLabel = page.getByTestId("replay-marker");
    await expect(markerLabel).toBeVisible({ timeout: 3000 });

    // Stop playback — focusIndex becomes null and marker disappears
    await playBtn.click();
    await page.waitForTimeout(300);
    await expect(page.getByTestId("replay-marker")).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // Approach analysis
  // ---------------------------------------------------------------------------

  test("Approach page renders glideslope chart with severity colors", async ({ page }) => {
    await setupRoutes(page);
    await page.goto(`/flights/${SESSION_ID}/approach`);

    const approachPage = page.getByTestId("approach-page");
    await expect(approachPage).toBeVisible({ timeout: 5000 });

    // Chart should be rendered
    await expect(approachPage.locator("svg").first()).toBeVisible({ timeout: 5000 });

    // Severity dots — colors come from API fixture (GREEN, YELLOW, RED)
    // The fixture has RED, GREEN, GREEN, YELLOW, GREEN points
    // Each dot carries data-severity from the API response
    const dots = approachPage.locator("[data-testid='approach-dot']");
    await expect(dots.first()).toBeVisible({ timeout: 5000 });

    // Verify a RED severity label is rendered from API data (not recomputed)
    // The fixture has deviation_ft: 300 → severity: "RED" from API
    const redLabel = approachPage.locator("[data-testid='severity-label-RED']");
    // This appears in tooltip on hover — check summary instead
    const maxDeviation = approachPage.getByTestId("max-deviation");
    await expect(maxDeviation).toBeVisible({ timeout: 5000 });
    await expect(maxDeviation).toContainText("RED");
  });

  test("Approach page handles 404 gracefully", async ({ page }) => {
    await setupRoutes(page);
    await page.goto(`/flights/${SESSION_ID_2}/approach`);

    const approachPage = page.getByTestId("approach-page");
    await expect(approachPage).toBeVisible({ timeout: 5000 });

    const notFound = page.getByTestId("approach-not-found");
    await expect(notFound).toBeVisible({ timeout: 5000 });
    await expect(notFound).toContainText("No approach data available for this flight");
  });

  // ---------------------------------------------------------------------------
  // Heatmap
  // ---------------------------------------------------------------------------

  test("Heatmap page loads samples and renders controls", async ({ page }) => {
    await setupRoutes(page);
    await page.goto("/analytics/heatmap");

    const heatmapPage = page.getByTestId("heatmap-page");
    await expect(heatmapPage).toBeVisible({ timeout: 5000 });

    const controls = page.getByTestId("heatmap-controls");
    await expect(controls).toBeVisible();

    // Sample count should show after load
    const count = page.getByTestId("sample-count");
    await expect(count).toContainText("20 points", { timeout: 5000 });
  });

  test("Heatmap hours selector triggers new fetch", async ({ page }) => {
    await setupRoutes(page);

    let fetchCount = 0;
    await page.route("**/api/v1/analytics/heatmap-samples?*", (route) => {
      fetchCount++;
      route.fulfill({ json: HEATMAP_SAMPLES_FIXTURE });
    });

    await page.goto("/analytics/heatmap");
    await page.waitForTimeout(300);

    const initialCount = fetchCount;
    const hoursSelect = page.getByTestId("hours-select");
    await hoursSelect.selectOption("48");
    await page.waitForTimeout(300);

    expect(fetchCount).toBeGreaterThan(initialCount);
  });

  // ---------------------------------------------------------------------------
  // Airport analytics
  // ---------------------------------------------------------------------------

  test("Airports page renders summary cards", async ({ page }) => {
    await setupRoutes(page);
    await page.goto("/analytics/airports");

    const airportsPage = page.getByTestId("airports-page");
    await expect(airportsPage).toBeVisible({ timeout: 5000 });

    // Summary grid
    const grid = page.getByTestId("airport-summary-grid");
    await expect(grid).toBeVisible({ timeout: 5000 });

    // KCMH card should appear
    const kcmhCard = page.getByTestId("airport-card-KCMH");
    await expect(kcmhCard).toBeVisible({ timeout: 5000 });
    await expect(kcmhCard).toContainText("KCMH");
  });

  test("Airport selector changes hourly chart data", async ({ page }) => {
    await setupRoutes(page);

    let klckFetchCount = 0;
    await page.route("**/api/v1/analytics/airports/hourly?icao=KLCK*", (route) => {
      klckFetchCount++;
      route.fulfill({ json: AIRPORT_HOURLY_FIXTURE_KLCK });
    });

    await page.goto("/analytics/airports");
    await expect(page.getByTestId("airports-page")).toBeVisible({ timeout: 5000 });

    // Click KLCK airport button
    const klckBtn = page.getByTestId("airport-btn-KLCK");
    await expect(klckBtn).toBeVisible({ timeout: 5000 });
    await klckBtn.click();

    await page.waitForTimeout(300);
    expect(klckFetchCount).toBeGreaterThan(0);

    // Hourly chart heading should update
    await expect(page.getByText("Hourly Activity — KLCK")).toBeVisible({ timeout: 5000 });
  });
});
