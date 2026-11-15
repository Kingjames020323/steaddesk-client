use super::candidate::*;
use hbb_common::{
    base64::{engine::general_purpose::STANDARD, Engine},
    sodiumoxide::{self, crypto::sign},
};
use serde_json::{json, Value};

struct Mock {
    at: u64,
    boot: u64,
    assignment: Value,
    code: u32,
    healthy: bool,
    local_error: Option<&'static str>,
    prepare_error: Option<&'static str>,
    stop: bool,
    lose_grant: bool,
    lose_launch: bool,
    granted: bool,
    launches: usize,
    preparations: usize,
    requests: Vec<Operation>,
    reports: Vec<Value>,
    snapshots: Vec<State>,
    events: Vec<(String, String)>,
}
impl Host for Mock {
    type Installer = ();
    fn now(&mut self) -> Result<u64> {
        Ok(self.at)
    }
    fn boot_id(&mut self) -> Result<u64> {
        Ok(self.boot)
    }
    fn local_gates(&mut self) -> Result<()> {
        self.local_error.map_or(Ok(()), |e| Err(Error(e)))
    }
    fn installed(&mut self) -> Result<Installed> {
        Ok(Installed {
            build: 69,
            os: 10,
            pid: 42,
            created: 1000,
            binary_sha256: [9; 32],
        })
    }
    fn request(&mut self, op: Operation, body: &Value, _version: u64) -> Result<Value> {
        self.requests.push(op);
        match op {
            Operation::Identity => Ok(json!({"key_version":1})),
            Operation::Assignment => {
                if self.granted {
                    Ok(
                        json!({"assignment":null,"reconcile_only":{"assignment":"fixture_assignment","attempt":"fixture_attempt","seq":self.reports.len(),"state":"observing"}}),
                    )
                } else {
                    Ok(self.assignment.clone())
                }
            }
            Operation::Safety => Ok(
                json!({"enabled":!self.stop,"generation":2,"issued_at":self.at,"expires_at":self.at+15,"nonce":body["nonce"],"purpose":"install","permit":"fixture_permit"}),
            ),
            Operation::Attempts => {
                self.granted = true;
                if self.lose_grant {
                    Err(Error("no_safety"))
                } else {
                    Ok(
                        json!({"install_authorized":true,"attempt":"fixture_attempt","generation":2}),
                    )
                }
            }
            Operation::Reports => {
                self.reports.push(body.clone());
                Ok(json!({"state":body["state"],"duplicate":false}))
            }
        }
    }
    fn prepare(&mut self, _m: &Manifest) -> Result<((), [u8; 32])> {
        self.preparations += 1;
        self.prepare_error
            .map_or(Ok(((), [7; 32])), |e| Err(Error(e)))
    }
    fn launch(&mut self, _i: &mut ()) -> Result<u32> {
        self.launches += 1;
        if self.lose_launch {
            Err(Error("no_safety"))
        } else {
            Ok(self.code)
        }
    }
    fn readback(&mut self, _t: &Transaction) -> Result<bool> {
        self.events
            .push(("readback".into(), "native_identity_query".into()));
        Ok(self.healthy)
    }
    fn persist(&mut self, s: &State) -> Result<()> {
        self.snapshots.push(s.clone());
        Ok(())
    }
    fn log(&mut self, event: &str, reason: &str) -> Result<()> {
        self.events.push((event.into(), reason.into()));
        Ok(())
    }
}
fn setup(version: u64) -> (Mock, State, BuildConfig) {
    sodiumoxide::init().unwrap();
    let at = 1799901000;
    let (pk, sk) = sign::gen_keypair();
    let cfg = BuildConfig {
        key_id: "test-windows-fixture",
        public_key: Box::leak(STANDARD.encode(pk.0).into_boxed_str()),
        valid_from: at - 1000,
        valid_until: at + 86400,
        current_build: 69,
        silent_profile: "fixture_firmware",
    };
    let m = json!({"schema":1,"release_id":"fixture_release","sequence":1,"key_id":cfg.key_id,"issued_at":at-100,"expires_at":at+3600,"ring":0,"batch":0,"bucket_end":100,"platform":"windows","package":"SteadDesk","channel":"merchant","architecture":"x64","versionCode":version,"display_version":"1.5.0-sd.2","min_os":10,"size_bytes":100,"artifact_path":"fixed/fixture.exe","sha256":"11".repeat(32),"signer_cert_sha256":"22".repeat(32),"previous_release_id":null,"health_policy_id":"c4-v1"});
    let raw = serde_json::to_vec(&m).unwrap();
    let signature = sign::sign_detached(&raw, &sk);
    let day = chrono::DateTime::<chrono::Utc>::from_timestamp(at as i64, 0)
        .unwrap()
        .date_naive()
        .to_string();
    let assignment = json!({"assignment":"fixture_assignment","ring":0,"manifest":STANDARD.encode(&raw),"signature":STANDARD.encode(signature.to_bytes()),"key_id":cfg.key_id,"expires_at":at+300,"silent_profile":cfg.silent_profile,"window":{"zone":"UTC","start_min":0,"end_min":1439,"business_day":day}});
    (
        Mock {
            at,
            boot: 100,
            assignment,
            code: 0,
            healthy: false,
            local_error: None,
            prepare_error: None,
            stop: false,
            lose_grant: false,
            lose_launch: false,
            granted: false,
            launches: 0,
            preparations: 0,
            requests: vec![],
            reports: vec![],
            snapshots: vec![],
            events: vec![],
        },
        State::default(),
        cfg,
    )
}
fn no_health(h: &Mock) {
    assert!(
        h.reports.iter().all(|r| r.get("heartbeat_at").is_none()
            && r.get("service_verified").is_none()
            && r.get("identity_verified").is_none()),
        "OS acceptance must not become health: {:?}",
        h.reports
    );
}
#[test]
fn exit_zero_only_os_acceptance_until_native_readback() {
    let (mut h, mut s, cfg) = setup(70);
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(s.transaction.as_ref().unwrap().installer_code, Some(0));
    assert!(h
        .reports
        .iter()
        .any(|r| r["state"] == "observing" && r["installer_code"] == 0));
    no_health(&h);
    h.healthy = true;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert!(h.reports.iter().any(|r| r["service_verified"] == true
        && r["identity_verified"] == true
        && r.get("heartbeat_at").is_some()));
}
#[test]
fn code3010_requires_changed_boot_and_native_readback() {
    let (mut h, mut s, cfg) = setup(70);
    h.code = 3010;
    h.healthy = true;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(s.transaction.as_ref().unwrap().stage, "pending_reboot");
    no_health(&h);
    tick(&mut h, &mut s, &cfg).unwrap();
    no_health(&h);
    assert_eq!(h.launches, 1);
    h.boot = 101;
    h.healthy = false;
    tick(&mut h, &mut s, &cfg).unwrap();
    no_health(&h);
    h.healthy = true;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(s.transaction.as_ref().unwrap().stage, "observing");
    assert!(h.reports.iter().any(|r| r["service_verified"] == true));
}
#[test]
fn installer_failure_freezes_without_retry_or_health() {
    let (mut h, mut s, cfg) = setup(70);
    h.code = 1603;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(s.transaction.as_ref().unwrap().stage, "failed");
    assert!(h
        .reports
        .iter()
        .any(|r| r["state"] == "failed" && r["installer_code"] == 1603));
    h.healthy = true;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    no_health(&h);
}
#[test]
fn lost_attempt_response_reconciles_before_any_launch() {
    let (mut h, mut s, cfg) = setup(70);
    h.lose_grant = true;
    assert!(tick(&mut h, &mut s, &cfg).is_err());
    assert_eq!(h.launches, 0);
    let saved = h.snapshots.last().unwrap().clone();
    s = saved;
    h.lose_grant = false;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 0);
    assert_eq!(
        s.transaction.as_ref().unwrap().attempt.as_deref(),
        Some("fixture_attempt")
    );
    assert_eq!(
        h.requests
            .iter()
            .filter(|o| matches!(o, Operation::Attempts))
            .count(),
        1
    );
}
#[test]
fn ambiguous_launch_never_reexecutes_or_claims_health() {
    let (mut h, mut s, cfg) = setup(70);
    h.lose_launch = true;
    assert!(tick(&mut h, &mut s, &cfg).is_err());
    assert_eq!(h.launches, 1);
    s = h.snapshots.last().unwrap().clone();
    h.healthy = true;
    h.lose_launch = false;
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    no_health(&h);
}
#[test]
fn equal_and_lower_targets_never_prepare_or_submit() {
    for target in [69, 68] {
        let (mut h, mut s, cfg) = setup(target);
        assert_eq!(tick(&mut h, &mut s, &cfg).unwrap_err().0, "same_version");
        assert_eq!(h.preparations, 0);
        assert_eq!(h.launches, 0);
        assert!(!h.requests.iter().any(|o| matches!(o, Operation::Attempts)));
    }
}
#[test]
fn local_pause_stop_session_and_daily_limits_fail_closed() {
    for reason in ["merchant_pause", "j23", "session_unknown"] {
        let (mut h, mut s, cfg) = setup(70);
        h.local_error = Some(reason);
        assert!(tick(&mut h, &mut s, &cfg).is_err());
        assert_eq!(h.launches, 0);
        assert_eq!(h.preparations, 0);
    }
    let (mut h, mut s, cfg) = setup(70);
    s.last_day = h.assignment["window"]["business_day"]
        .as_str()
        .unwrap()
        .into();
    assert_eq!(tick(&mut h, &mut s, &cfg).unwrap_err().0, "outside_window");
    assert_eq!(h.launches, 0);
}
#[test]
fn live_stop_denies_after_preparation_without_attempt() {
    let (mut h, mut s, cfg) = setup(70);
    h.stop = true;
    assert_eq!(tick(&mut h, &mut s, &cfg).unwrap_err().0, "no_safety");
    assert_eq!(h.preparations, 1);
    assert_eq!(h.launches, 0);
    assert!(s.transaction.is_none());
    assert!(!h.requests.iter().any(|o| matches!(o, Operation::Attempts)));
}
#[test]
fn manifest_and_signature_tamper_rejected_before_preparation() {
    for field in ["manifest", "signature"] {
        let (mut h, mut s, cfg) = setup(70);
        let mut bytes = STANDARD
            .decode(h.assignment[field].as_str().unwrap())
            .unwrap();
        bytes[0] ^= 1;
        h.assignment[field] = json!(STANDARD.encode(bytes));
        assert_eq!(
            tick(&mut h, &mut s, &cfg).unwrap_err().0,
            "manifest_signature"
        );
        assert_eq!(h.preparations, 0);
        assert_eq!(h.launches, 0);
    }
}
#[test]
fn native_verifier_failure_never_requests_install_authorization() {
    let (mut h, mut s, cfg) = setup(70);
    h.prepare_error = Some("artifact_signature");
    assert_eq!(
        tick(&mut h, &mut s, &cfg).unwrap_err().0,
        "artifact_signature"
    );
    assert_eq!(h.launches, 0);
    assert!(!h.requests.iter().any(|o| matches!(o, Operation::Attempts)));
    no_health(&h);
}
