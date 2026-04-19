// Simple logger.
export const logger = {
  info: (msg: string) => console.error(`INFO ${msg}`),
  warn: (msg: string) => console.error(`WARN ${msg}`),
  error: (msg: string) => console.error(`ERROR ${msg}`),
};
