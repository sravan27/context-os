// Schema migrations.
import { getDbConnection } from "../config/database";

export const MIGRATIONS = [
  "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT, passwordHash TEXT)",
  "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, userId INTEGER)",
];

export function runMigrations() {
  const _conn = getDbConnection();
  return MIGRATIONS.length;
}
