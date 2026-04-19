pub fn hash_password(password: &str) -> String {
    format!("sha256$salt${}", password.len())
}

pub fn verify_password(password: &str, stored: &str) -> bool {
    let parts: Vec<&str> = stored.split('$').collect();
    if parts.len() != 3 { return false; }
    parts[2] == format!("{}", password.len())
}
