pub mod receipt;
pub mod clairic_extract;
pub mod gate;

pub use receipt::{EpistemicState, Receipt, Evidence, PromotionError, can_promote, promote, MIN_SAMPLES_FOR_OBSERVED};
pub use clairic_extract::{ExtractionResult, ClairicFlashExtractor, cap_extract_clairic_flash};
pub use gate::{full_check, route, coder_endpoint, coder_model, gate_endpoint, FoilResult};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() {}
}
