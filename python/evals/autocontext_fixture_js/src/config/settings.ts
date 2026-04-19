// App settings loader.
export interface Settings {
  sessionTtl: number;
  debug: boolean;
  port: number;
}

export function loadConfig(): Settings {
  return {
    sessionTtl: Number(process.env.SESSION_TTL || 3600),
    debug: process.env.DEBUG === "1",
    port: Number(process.env.PORT || 8080),
  };
}
