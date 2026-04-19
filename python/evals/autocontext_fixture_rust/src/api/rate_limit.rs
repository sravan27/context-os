use std::collections::HashMap;

pub struct RateLimitConfig {
    pub default_per_minute: u32,
    pub login_per_minute: u32,
    pub burst: u32,
}

pub const RATE_LIMIT_CONFIG: RateLimitConfig = RateLimitConfig {
    default_per_minute: 60,
    login_per_minute: 5,
    burst: 10,
};

pub struct RateLimiter {
    log: HashMap<String, Vec<u64>>,
    cap: u32,
}

impl RateLimiter {
    pub fn new(cap: u32) -> Self { Self { log: HashMap::new(), cap } }
    pub fn check(&mut self, key: &str, now: u64) -> bool {
        let entry = self.log.entry(key.into()).or_default();
        entry.retain(|t| now - t < 60);
        if entry.len() as u32 >= self.cap { return false; }
        entry.push(now);
        true
    }
}
