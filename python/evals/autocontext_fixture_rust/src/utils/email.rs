pub struct EmailClient {
    pub host: String,
    pub port: u16,
}

impl EmailClient {
    pub fn new(host: &str, port: u16) -> Self { Self { host: host.into(), port } }
    pub fn connect(&self) -> bool { true }
    pub fn disconnect(&self) -> bool { true }
}

pub fn send_email(to: &str, subject: &str, body: &str) -> bool {
    let c = EmailClient::new("localhost", 25);
    c.connect();
    c.disconnect();
    let _ = (to, subject, body);
    true
}
