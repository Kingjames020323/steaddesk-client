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
    expire_on_submitted: bool,
    replace_on_submitted: bool,
    replacement: bool,
    break_clock_after_result: bool,
    clock_unavailable: bool,
    server_state: &'static str,
    server_seq: u64,
    report_fail_before_accept: bool,
    report_ack_loss: bool,
    snapshots: Vec<State>,
    events: Vec<(String, String)>,
}
impl Host for Mock {
    type Installer = ();
    fn now(&mut self) -> Result<u64> {
        if self.clock_unavailable {
            Err(Error("clock_unknown"))
        } else {
            Ok(self.at)
        }
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
            pid: if self.replacement { 43 } else { 42 },
            created: if self.replacement { 1001 } else { 1000 },
            binary_sha256: if self.replacement { [10; 32] } else { [9; 32] },
        })
    }
    fn request(&mut self, op: Operation, body: &Value, _version: u64) -> Result<Value> {
        self.requests.push(op);
        match op {
            Operation::Identity => Ok(json!({"key_version":1})),
            Operation::Assignment => {
                if self.granted {
                    Ok(
                        json!({"assignment":null,"reconcile_only":{"assignment":"fixture_assignment","attempt":"fixture_attempt","seq":self.server_seq,"state":self.server_state}}),
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
                if self.report_fail_before_accept {
                    self.report_fail_before_accept = false;
                    return Err(Error("no_safety"));
                }
                if body["id"] == "fixture_attempt" {
                    let seq = body["seq"]
                        .as_u64()
                        .ok_or(Error("backend_invalid_sequence"))?;
                    if seq <= self.server_seq {
                        if self.reports.iter().any(|previous| previous == body) {
                            return Ok(json!({"state":body["state"],"duplicate":true}));
                        }
                        return Err(Error("backend_sequence_conflict"));
                    }
                    let status = body["state"]
                        .as_str()
                        .ok_or(Error("backend_invalid_state"))?;
                    match (self.server_state, status) {
                        ("committing", "pending_reboot") if body["installer_code"] == 3010 => {
                            self.server_state = "pending_reboot"
                        }
                        ("committing", "observing") if body["installer_code"] == 0 => {
                            self.server_state = "observing"
                        }
                        ("pending_reboot", "observing") | ("observing", "observing") => {
                            self.server_state = "observing"
                        }
                        (_, "failed")
                            if body["reason"] == "install_failed"
                                && body["installer_code"]
                                    .as_u64()
                                    .map_or(false, |n| n != 0 && n != 3010) =>
                        {
                            self.server_state = "failed"
                        }
                        (_, "paused") if body["reason"] == "merchant_pause" => {}
                        _ => return Err(Error("backend_invalid_transition")),
                    }
                    self.server_seq = seq;
                }
                self.reports.push(body.clone());
                if self.report_ack_loss {
                    self.report_ack_loss = false;
                    return Err(Error("no_safety"));
                }
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
        if self.break_clock_after_result
            && s.transaction
                .as_ref()
                .map_or(false, |t| t.installer_code.is_some())
        {
            self.break_clock_after_result = false;
            self.clock_unavailable = true;
        }
        if s.transaction.as_ref().map_or(false, |t| {
            t.stage == "submitted" && t.installer_code.is_none()
        }) {
            if self.expire_on_submitted {
                self.at += 16;
                self.expire_on_submitted = false;
            }
            if self.replace_on_submitted {
                self.replacement = true;
                self.replace_on_submitted = false;
            }
        }
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
            expire_on_submitted: false,
            replace_on_submitted: false,
            replacement: false,
            break_clock_after_result: false,
            clock_unavailable: false,
            server_state: "committing",
            server_seq: 0,
            report_fail_before_accept: false,
            report_ack_loss: false,
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

#[test]
fn permit_expiring_during_submitted_fsync_never_launches() {
    let (mut h, mut s, cfg) = setup(70);
    h.expire_on_submitted = true;
    assert_eq!(tick(&mut h, &mut s, &cfg).unwrap_err().0, "no_safety");
    assert_eq!(h.launches, 0);
    assert_eq!(s.transaction.as_ref().unwrap().stage, "submitted");
    s = h.snapshots.last().unwrap().clone();
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 0);
    no_health(&h);
}
#[test]
fn same_build_service_identity_changed_during_submitted_fsync_never_launches() {
    let (mut h, mut s, cfg) = setup(70);
    h.replace_on_submitted = true;
    assert!(tick(&mut h, &mut s, &cfg).is_err());
    assert!(h.replacement);
    assert_eq!(h.launches, 0);
    s = h.snapshots.last().unwrap().clone();
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 0);
    no_health(&h);
}
#[test]
fn active_or_unknown_recovery_session_is_not_mislabeled_merchant_pause() {
    let (mut h, mut s, cfg) = setup(70);
    tick(&mut h, &mut s, &cfg).unwrap();
    h.healthy = true;
    h.local_error = Some("session_unknown");
    tick(&mut h, &mut s, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert!(h.reports.iter().all(|r| r["state"] != "paused"));
    no_health(&h);
}

fn result_persisted_before_report_gap(code: u32) -> (Mock, State, BuildConfig) {
    let (mut h, mut state, cfg) = setup(70);
    h.code = code;
    h.break_clock_after_result = true;
    assert_eq!(
        tick(&mut h, &mut state, &cfg).unwrap_err().0,
        "clock_unknown"
    );
    assert_eq!(h.launches, 1);
    assert!(h.reports.is_empty());
    assert_eq!(h.server_state, "committing");
    assert_eq!(h.server_seq, 0);
    let durable = h.snapshots.last().unwrap().clone();
    assert_eq!(
        durable.transaction.as_ref().unwrap().installer_code,
        Some(code)
    );
    assert!(durable.reports.is_empty());
    assert_eq!(durable.report_seq, 0);
    h.clock_unavailable = false;
    (h, durable, cfg)
}
#[test]
fn persisted_3010_replays_pending_receipt_before_postboot_health() {
    let (mut h, mut state, cfg) = result_persisted_before_report_gap(3010);
    h.boot = 101;
    h.healthy = true;
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.reports[0]["state"], "pending_reboot");
    assert_eq!(h.reports[0]["installer_code"], 3010);
    assert!(h.reports[0].get("heartbeat_at").is_none());
    assert!(h
        .reports
        .iter()
        .skip(1)
        .any(|r| r["state"] == "observing" && r["service_verified"] == true));
    assert_eq!(h.server_state, "observing");
    let pending = h
        .reports
        .iter()
        .filter(|r| r["state"] == "pending_reboot")
        .count();
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(
        h.reports
            .iter()
            .filter(|r| r["state"] == "pending_reboot")
            .count(),
        pending
    );
    assert_eq!(h.preparations, 1);
    assert_eq!(
        h.requests
            .iter()
            .filter(|op| matches!(op, Operation::Attempts))
            .count(),
        1
    );
}
#[test]
fn persisted_installer_failure_replays_before_freezing() {
    let (mut h, mut state, cfg) = result_persisted_before_report_gap(1603);
    h.healthy = true;
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.reports.len(), 1);
    assert_eq!(h.reports[0]["state"], "failed");
    assert_eq!(h.reports[0]["reason"], "install_failed");
    assert_eq!(h.reports[0]["installer_code"], 1603);
    assert_eq!(h.server_state, "failed");
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.reports.len(), 1);
    no_health(&h);
    assert_eq!(h.preparations, 1);
    assert_eq!(
        h.requests
            .iter()
            .filter(|op| matches!(op, Operation::Attempts))
            .count(),
        1
    );
}
#[test]
fn persisted_zero_replays_accepted_observing_without_relaunch() {
    let (mut h, mut state, cfg) = result_persisted_before_report_gap(0);
    h.healthy = false;
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.reports.len(), 1);
    assert_eq!(h.reports[0]["state"], "observing");
    assert_eq!(h.reports[0]["installer_code"], 0);
    assert_eq!(h.server_state, "observing");
    no_health(&h);
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.reports.len(), 1);
    no_health(&h);
    h.healthy = true;
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.reports.len(), 2);
    assert!(h.reports[1]["service_verified"] == true);
    assert!(h.reports[1].get("heartbeat_at").is_some());
    assert_eq!(
        h.reports
            .iter()
            .filter(|r| r.get("heartbeat_at").is_none())
            .count(),
        1
    );
    tick(&mut h, &mut state, &cfg).unwrap();
    assert_eq!(h.launches, 1);
    assert_eq!(h.preparations, 1);
    assert_eq!(
        h.requests
            .iter()
            .filter(|op| matches!(op, Operation::Attempts))
            .count(),
        1
    );
}

#[test]
fn queued_pending_receipt_preserves_original_body_and_sequence_on_recovery() {
    for ack_lost_after_accept in [false, true] {
        let (mut h, mut state, cfg) = setup(70);
        h.code = 3010;
        h.report_fail_before_accept = !ack_lost_after_accept;
        h.report_ack_loss = ack_lost_after_accept;
        assert_eq!(tick(&mut h, &mut state, &cfg).unwrap_err().0, "no_safety");
        state = h.snapshots.last().unwrap().clone();
        assert_eq!(state.reports.len(), 1);
        let original = state.reports[0].clone();
        assert_eq!(original["state"], "pending_reboot");
        assert_eq!(original["installer_code"], 3010);
        assert_eq!(
            h.server_state,
            if ack_lost_after_accept {
                "pending_reboot"
            } else {
                "committing"
            }
        );
        h.at += 20;
        h.boot = 101;
        h.healthy = true;
        tick(&mut h, &mut state, &cfg).unwrap();
        assert!(state.reports.is_empty());
        assert_eq!(h.reports[0], original);
        assert_eq!(
            h.reports
                .iter()
                .filter(|r| r["state"] == "pending_reboot")
                .count(),
            1
        );
        assert!(h.reports.iter().any(|r| r["service_verified"] == true));
        assert_eq!(h.launches, 1);
        assert_eq!(h.preparations, 1);
        assert_eq!(
            h.requests
                .iter()
                .filter(|op| matches!(op, Operation::Attempts))
                .count(),
            1
        );
        tick(&mut h, &mut state, &cfg).unwrap();
        assert_eq!(h.launches, 1);
        assert_eq!(
            h.reports
                .iter()
                .filter(|r| r["state"] == "pending_reboot")
                .count(),
            1
        );
    }
}
