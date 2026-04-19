use crate::db::queries::find_user_by_email;
use crate::utils::crypto::verify_password;
use crate::auth::session::create_session;

pub fn validate_credentials(email: &str, password: &str) -> bool {
    match find_user_by_email(email) {
        Some(user) => verify_password(password, &user.password_hash),
        None => false,
    }
}

pub fn handle_login(email: &str, password: &str) -> (String, u16) {
    if !validate_credentials(email, password) {
        return ("invalid credentials".into(), 401);
    }
    let session = create_session(email);
    (session.token, 200)
}
