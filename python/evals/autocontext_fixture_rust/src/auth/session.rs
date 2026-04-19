use crate::config::settings::load_config;

pub struct Session {
    pub token: String,
    pub email: String,
    pub ttl: u64,
}

pub struct SessionManager {
    sessions: std::collections::HashMap<String, Session>,
}

impl SessionManager {
    pub fn new() -> Self { Self { sessions: Default::default() } }
    pub fn get(&self, token: &str) -> Option<&Session> { self.sessions.get(token) }
    pub fn invalidate(&mut self, token: &str) { self.sessions.remove(token); }
}

pub fn create_session(email: &str) -> Session {
    let cfg = load_config();
    Session {
        token: format!("tok-{}", email.len()),
        email: email.into(),
        ttl: cfg.session_ttl,
    }
}
