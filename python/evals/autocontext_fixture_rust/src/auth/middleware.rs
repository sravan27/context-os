use crate::auth::session::SessionManager;
use crate::utils::logging::log_warn;

pub struct Request {
    pub token: String,
}

pub fn auth_middleware(req: &Request, mgr: &SessionManager) -> Option<(String, u16)> {
    if mgr.get(&req.token).is_none() {
        log_warn("unauthenticated request");
        return Some(("unauthorized".into(), 401));
    }
    None
}
