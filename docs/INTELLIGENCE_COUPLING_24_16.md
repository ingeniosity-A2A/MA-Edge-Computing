# 24/16 Intelligence Coupling and Execution Integration

## Purpose and authority

The engine coordinates independent model contributions without merging model weights. It validates input contracts, computes a reliability-weighted candidate state, records disagreement and provenance, and returns advisory evidence.

AVA-007 owns objectives, interpretation, acceptance into Source Truth, curation, promotion, and action authorization. Exoskeleton owns runtime execution and persistence mechanics. REV.IKE remains read-only interpretation and proposal generation. This crate has no Source Truth write path, promotion authority, or action executor.

## 24/16 profile

The requested name is retained as an architectural profile: 24 contributor slots and 16 target shared-state dimensions. This is not a proven physical gear law or universal invariant. The current API accepts any common non-empty vector dimension; 16 is a target profile, not a forced truncation.

## Executable contract

Every contribution requires non-empty identity, domain, provenance, and vector; vectors must have equal dimensions and finite values. Confidence and evaluation score must be finite in [0,1], latency finite and non-negative, and total confidence-times-evaluation weight must be positive. Invalid input fails closed with a typed error.

Consensus is a weighted arithmetic mean using confidence × eval_score. Pairwise disagreement uses Euclidean distance. Cross-domain rules also use L2 distance as a numeric proxy only. They cannot prove semantic statements such as object containment, evidence citation, or decision calibration; those require domain-specific typed validators.

The confidence summary is a conservative heuristic: weighted confidence mean capped by the weakest active contributor. It is not a calibrated probability. Evaluation scores are supplied by callers and are not certified by this crate.

## Model/service candidate registry

The Rust registry lists candidates and review states only. It does not download, execute, approve, or promote them. No hashes, weights, benchmark scores, or deployment status are fabricated. Pin exact revisions, verify license files, record quantization and provenance, and run domain-specific evaluations before promotion.

Audex is research-only pending license resolution; the stated One-Way Noncommercial terms block commercial use absent separate permission. LFM3, Dory, Mellum, Salience, d3-ultra, and Drex terms require exact artifact/vendor review. Plane labels are candidate intent, not proof that the handset or VPS can execute a model.

## NVIDIA AI Aerial / RAN research

NVIDIA Aerial is recorded as an optional external integration, not an installed runtime. cuPHY/cuMAC require a supported NVIDIA GPU and compatible drivers, CUDA, SDK, and licenses. No compatible GPU is established for the current VPS; Aerial remains disabled.

The RAN YAML records metadata extraction targets: channel-estimation profiles, 64T64R beamforming profile metadata, MU-MIMO scheduling policy metadata, spectral-efficiency benchmark metadata, and measured GPU L1/L2 latency profiles. It excludes proprietary CUDA binaries, containers, and deployment manifests. Do not fabricate beamforming weights or latency figures.

The supplied greater-than-100% 2028 spectral-efficiency claim is treated as a vendor-reported forward-looking projection, not a measured result, FAPO guarantee, or optimizer ceiling. The in-process FAPO twin is not an RF channel simulator or cuPHY/cuMAC substitute.

## Data and infrastructure mapping

- Docling: document extraction/normalization; preserve source provenance.
- LEANN: derived semantic index only. It does not replace authoritative source records or DuckDB.
- Drex Max / Drex Search: external API boundary; require vendor terms, privacy/cost controls, and task evaluation.
- TurboVecQuant: compression research; benchmark accuracy and reversibility before adoption.
- air-consensus: distributed candidate mixing and digital aggregation; no general Quasi-Fejer proof or physical OTA-C.
- air-dfm: governance scaffold only; no learned parametric DFM model.
- DuckDB / atomic substrate: durable source of truth, subject to AVA-007 acceptance.
- Rustunnel / Tailscale: transport, not decision authority.

LEANN index-size claims apply to the derived vector index, not original records. A 64 MB index target for a 1.8 GB corpus remains unverified until source DB, index, cache, recall, latency, and rebuild costs are separately measured.

## Execution order

1. Establish reproducible Docling ingestion and provenance; benchmark source storage separately from LEANN.
2. Test local model candidates on real device memory, thermals, latency, and task quality.
3. Integrate air-coupling; add typed domain validators before treating numeric constraint diagnostics as semantic verification.
4. Add Drex behind an API adapter with timeout, privacy, cost, and vendor-license controls.
5. Evaluate remote specialists by pinned revision and task suite; verify license and hardware.
6. Integrate Aerial only on a supported NVIDIA GPU/CUDA stack; otherwise retain the disabled research profile.
7. Route promotion and action authorization through AVA-007.

## Verification status

The crate includes tests for weighted consensus, disagreement, dimension mismatch, zero total weight, invalid numeric input, and registry state. They are committed but not claimed executed until Cargo output is captured using the pinned toolchain.

No model weights were downloaded or merged. No Aerial runtime was installed. No GPU latency, spectral-efficiency gain, 64T64R result, 64 MB index, or local-model benchmark is claimed.
