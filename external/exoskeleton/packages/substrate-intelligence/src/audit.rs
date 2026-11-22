use blake2::{Blake2b512, Digest};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEvent {
    pub seq: u64,
    pub kind: String,
    pub payload: String,
    pub prev_hash: String,
    pub hash: String,
}

pub struct AuditLedger {
    events: Vec<AuditEvent>,
    prev_hash: String,
}

impl AuditLedger {
    pub fn new() -> Self {
        Self { events: Vec::new(), prev_hash: "genesis".to_string() }
    }

    pub fn append(&mut self, kind: &str, payload: &str) -> AuditEvent {
        let seq = self.events.len() as u64 + 1;
        let data = format!("{}:{}:{}:{}", seq, kind, payload, self.prev_hash);
        let mut h = Blake2b512::new();
        h.update(data.as_bytes());
        let hash = hex_encode(h.finalize().as_slice());
        let ev = AuditEvent { seq, kind: kind.to_string(), payload: payload.to_string(), prev_hash: self.prev_hash.clone(), hash: hash.clone() };
        self.prev_hash = hash;
        self.events.push(ev.clone());
        ev
    }

    pub fn events(&self) -> &[AuditEvent] {
        &self.events
    }

    pub fn verify(&self) -> bool {
        let mut prev = "genesis".to_string();
        for ev in &self.events {
            if ev.prev_hash != prev { return false; }
            let data = format!("{}:{}:{}:{}", ev.seq, ev.kind, ev.payload, ev.prev_hash);
            let mut h = Blake2b512::new();
            h.update(data.as_bytes());
            let hash = hex_encode(h.finalize().as_slice());
            if hash != ev.hash { return false; }
            prev = ev.hash.clone();
        }
        true
    }
}

impl Default for AuditLedger {
    fn default() -> Self {
        Self::new()
    }
}

fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}
