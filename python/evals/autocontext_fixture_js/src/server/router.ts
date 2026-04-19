// Router with route table + dispatch.
import { handleLogin } from "../auth/login";
import { authMiddleware } from "../auth/middleware";
import { rateLimit } from "../api/rateLimit";

export type Handler = (req: any) => [any, number];

export function createRouter() {
  const routes: Record<string, Handler> = {};
  return {
    add(path: string, handler: Handler) { routes[path] = handler; },
    dispatch(req: any) {
      const err = authMiddleware(req);
      if (err) return err;
      const h = routes[req.path];
      if (!h) return [{ error: "not found" }, 404];
      return h(req);
    },
    register() {
      this.add("/login", rateLimit(handleLogin, 5));
    },
  };
}
