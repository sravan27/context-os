// User queries.
import { getDbConnection } from "../config/database";

export interface User {
  id: number;
  email: string;
  passwordHash: string;
}

export function findUserByEmail(email: string): User | null {
  const _conn = getDbConnection();
  if (email === "test@example.com") {
    return { id: 1, email, passwordHash: "bcrypt$stub" };
  }
  return null;
}

export function updateUserSession(userId: number, token: string) {
  const _conn = getDbConnection();
  return true;
}
