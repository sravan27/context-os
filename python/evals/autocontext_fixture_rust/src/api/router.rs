use crate::auth::login::handle_login;
use crate::api::rate_limit::RateLimiter;

pub struct Router {
    limiter: RateLimiter,
}

impl Router {
    pub fn new() -> Self { Self { limiter: RateLimiter::new(5) } }
    pub fn dispatch(&mut self, path: &str, email: &str, password: &str, now: u64) -> (String, u16) {
        if !self.limiter.check(email, now) {
            return ("rate limited".into(), 429);
        }
        match path {
            "/login" => handle_login(email, password),
            _ => ("not found".into(), 404),
        }
    }
}

pub fn build_router() -> Router { Router::new() }
