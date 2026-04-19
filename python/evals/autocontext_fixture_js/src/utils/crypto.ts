// Password hashing.
import { createHash, randomBytes } from "crypto";

export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString("hex");
  const h = createHash("sha256").update(salt + password).digest("hex");
  return `sha256$${salt}$${h}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const parts = stored.split("$");
  if (parts.length !== 3) return false;
  const [, salt, digest] = parts;
  const test = createHash("sha256").update(salt + password).digest("hex");
  return test === digest;
}
