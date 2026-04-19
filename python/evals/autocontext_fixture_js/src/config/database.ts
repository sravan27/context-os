// DB connection stub.
export const DATABASE_URL = process.env.DATABASE_URL || "sqlite:///app.db";

export function getDbConnection() {
  return { url: DATABASE_URL, closed: false };
}

export function closeConnection(conn: { closed: boolean }) {
  conn.closed = true;
}
