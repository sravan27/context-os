pub struct Settings {
    pub session_ttl: u64,
    pub debug: bool,
    pub port: u16,
}

pub fn load_config() -> Settings {
    Settings {
        session_ttl: 3600,
        debug: false,
        port: 8080,
    }
}
