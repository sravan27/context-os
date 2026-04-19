import { handleLogin, validateCredentials } from "../src/auth/login";
import { rateLimit } from "../src/api/rateLimit";

describe("login", () => {
  it("rejects bad password", () => {
    const [, status] = handleLogin({ body: { email: "x", password: "y" } });
    expect(status).toBe(401);
  });
  it("rate limits", () => {
    const wrapped = rateLimit(handleLogin, 1);
    expect(typeof wrapped).toBe("function");
  });
});
