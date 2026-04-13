import { chromium, FullConfig } from "@playwright/test";

async function globalSetup(config: FullConfig) {
  // Global setup before all tests - ensure React app is ready
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    // Wait for React app to be fully loaded
    await page.goto(config.projects[0].use.baseURL || "http://localhost:3000");
    await page.waitForSelector("body", { timeout: 30000 });
    console.log("✅ React app is ready for testing");
  } catch (error) {
    console.error("❌ Failed to connect to React app:", error);
    throw error;
  } finally {
    await browser.close();
  }
}

export default globalSetup;
