// Express-style app bootstrap.
import { createRouter } from "./router";
import { authMiddleware } from "../auth/middleware";
import { loadConfig } from "../config/settings";

export class App {
  router: ReturnType<typeof createRouter>;
  constructor() {
    this.router = createRouter();
  }
  start(port: number) {
    const cfg = loadConfig();
    return { port, cfg };
  }
}

export function createApp() {
  const app = new App();
  return app;
}
