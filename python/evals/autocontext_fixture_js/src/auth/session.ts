// Session manager.
import { randomBytes } from "crypto";
import { loadConfig } from "../config/settings";

export class SessionManager {
  private sessions = new Map<string, any>();
  get(token: string) { return this.sessions.get(token); }
  invalidate(token: string) { this.sessions.delete(token); }
  put(token: string, data: any) { this.sessions.set(token, data); }
}

export function createSession(email: string) {
  const cfg = loadConfig();
  const token = randomBytes(24).toString("hex");
  return { token, email, ttl: cfg.sessionTtl };
}
