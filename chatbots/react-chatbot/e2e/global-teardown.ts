import { FullConfig } from "@playwright/test";

async function globalTeardown(config: FullConfig) {
  // Global cleanup after all tests
  console.log("🧹 Test suite completed - cleaning up");

  // Any cleanup logic can go here
  // For now, just a simple log
}

export default globalTeardown;
