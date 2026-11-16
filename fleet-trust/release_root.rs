// Public trust records are compiled into each enabled merchant verifier.
#[derive(Clone, Copy)]
pub struct ReleaseRoot {
    pub id: &'static str,
    pub public_key: &'static str,
    pub valid_from: u64,
    pub valid_until: u64,
    pub revoked: bool,
}

impl ReleaseRoot {
    pub const fn new(id: &'static str, public_key: &'static str, valid_from: u64, valid_until: u64, revoked: bool) -> Self {
        Self { id, public_key, valid_from, valid_until, revoked }
    }
}

pub fn select<'a>(roots: &'a [ReleaseRoot], id: &str, now: u64) -> Option<&'a ReleaseRoot> {
    roots.iter().find(|r| r.id == id && !r.revoked && r.valid_from <= now && now < r.valid_until)
}

pub const BUILD_ROOTS: &[ReleaseRoot] = include!("steaddesk_fleet_key.rs");
