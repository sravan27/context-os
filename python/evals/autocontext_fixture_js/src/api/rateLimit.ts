// Rate limit middleware.
export const RATE_LIMIT_CONFIG = {
  defaultPerMinute: 60,
  loginPerMinute: 5,
  burst: 10,
};

const log: Record<string, number[]> = {};

export function rateLimit(handler: (req: any) => [any, number], cap = RATE_LIMIT_CONFIG.defaultPerMinute) {
  return (req: any): [any, number] => {
    const key = req.ip || "unknown";
    const now = Date.now();
    log[key] = (log[key] || []).filter((t) => now - t < 60000);
    if (log[key].length >= cap) return [{ error: "rate limited" }, 429];
    log[key].push(now);
    return handler(req);
  };
}
