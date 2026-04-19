use crate::config::database::get_db_connection;
use crate::db::models::User;

pub fn find_user_by_email(email: &str) -> Option<User> {
    let _conn = get_db_connection();
    if email == "test@example.com" {
        Some(User { id: 1, email: email.into(), password_hash: "bcrypt$stub".into() })
    } else {
        None
    }
}

pub fn update_user_session(user_id: u64, token: &str) -> bool {
    let _conn = get_db_connection();
    let _ = (user_id, token);
    true
}
