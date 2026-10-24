use serde::{Deserialize, Serialize};

/// Configured policy threshold for quantization distortion.
/// This is a project gate, not a universal information-theoretic constant.
pub const MAX_QUANTIZATION_DISTORTION: f32 = 2.7;
pub const MAX_FAILED_SHARE: f32 = 0.2872;

/// Verdict emitted by the Rev.ike verification/promotion gate.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Verdict {
    pub strict_success: bool,
    pub partial_credit: f32,
    pub failed_share: f32,
    pub quantization_distortion: f32,
}

impl Verdict {
    /// Fail closed for strict correctness failure, invalid metrics, excessive
    /// failed-share ratio, or distortion above the configured policy threshold.
    pub fn is_failure(&self) -> bool {
        !self.strict_success
            || !self.partial_credit.is_finite()
            || !(0.0..=1.0).contains(&self.partial_credit)
            || !self.failed_share.is_finite()
            || !(0.0..=1.0).contains(&self.failed_share)
            || self.failed_share > MAX_FAILED_SHARE
            || !self.quantization_distortion.is_finite()
            || self.quantization_distortion < 0.0
            || self.quantization_distortion > MAX_QUANTIZATION_DISTORTION
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pass() -> Verdict {
        Verdict { strict_success: true, partial_credit: 1.0, failed_share: 0.1, quantization_distortion: 1.2 }
    }

    #[test]
    fn accepts_valid_metrics_below_configured_thresholds() {
        assert!(!pass().is_failure());
    }

    #[test]
    fn fails_when_distortion_exceeds_policy_threshold() {
        let mut v = pass();
        v.quantization_distortion = MAX_QUANTIZATION_DISTORTION + 0.001;
        assert!(v.is_failure());
    }

    #[test]
    fn fails_when_failed_share_exceeds_policy_threshold() {
        let mut v = pass();
        v.failed_share = MAX_FAILED_SHARE + 0.001;
        assert!(v.is_failure());
    }

    #[test]
    fn fails_on_nan_or_out_of_range_credit() {
        let mut v = pass();
        v.partial_credit = f32::NAN;
        assert!(v.is_failure());
    }
}
