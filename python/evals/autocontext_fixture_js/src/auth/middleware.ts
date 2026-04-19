// Auth middleware.
import { SessionManager } from "./session";
import { logger } from "../utils/logging";

const mgr = new SessionManager();

export function authMiddleware(req: any) {
  const token = (req.headers?.authorization || "").replace("Bearer ", "");
  const session = mgr.get(token);
  if (!session) {
    logger.warn("unauthenticated request");
    return [{ error: "unauthorized" }, 401];
  }
  req.session = session;
  return null;
}
