pub const DATABASE_URL: &str = "sqlite:///app.db";

pub struct Connection {
    pub url: String,
    pub closed: bool,
}

pub fn get_db_connection() -> Connection {
    Connection { url: DATABASE_URL.into(), closed: false }
}

pub fn close_connection(conn: &mut Connection) { conn.closed = true; }
