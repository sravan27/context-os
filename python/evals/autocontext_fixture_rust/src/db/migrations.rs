use crate::config::database::get_db_connection;

pub const MIGRATIONS: &[&str] = &[
    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT)",
    "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER)",
];

pub fn run_migrations() -> usize {
    let _conn = get_db_connection();
    MIGRATIONS.len()
}
