pub struct User {
    pub id: u64,
    pub email: String,
    pub password_hash: String,
}

pub struct SessionRow {
    pub token: String,
    pub user_id: u64,
    pub expires_at: u64,
}

pub struct Token {
    pub value: String,
    pub purpose: String,
    pub user_id: u64,
}
