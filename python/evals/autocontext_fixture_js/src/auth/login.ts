// Login flow.
import { findUserByEmail } from "../db/users";
import { verifyPassword } from "../utils/crypto";
import { createSession } from "./session";

export function validateCredentials(email: string, password: string): boolean {
  const user = findUserByEmail(email);
  if (!user) return false;
  return verifyPassword(password, user.passwordHash);
}

export function handleLogin(req: any): [any, number] {
  const { email, password } = req.body || {};
  if (!validateCredentials(email, password)) {
    return [{ error: "invalid credentials" }, 401];
  }
  const session = createSession(email);
  return [{ token: session.token }, 200];
}
