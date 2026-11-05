# Deep Fusion Memory integration — arXiv:2610.25100

**Reference:** Deep Fusion Memory (DFM), https://arxiv.org/abs/2610.25100.

## Architectural placement

DFM is the intended parametric-memory fast path between the authoritative
atomic substrate and AVA-007's reasoning/authorization gate. Mem0 arbitration
governs candidate promotion. Dream-RSI remains the retrieval-based fallback
for novel or unsupported contexts. The substrate remains the source of truth.

## What this commit implements

The `air-dfm` Rust crate implements a bounded governance scaffold:

- candidate validation (identity, finite embeddings, score range);
- quality and temporal-context-depth promotion gates;
- cosine-similarity deduplication during promotion review;
- Mem0-style ADD, UPDATE, and NOOP decisions;
- an in-memory registry with unit tests.

The `packages/csn/deep-reasoning.yaml` file declares the intended intelligence
slot and explicitly records implementation status.

## What it does not implement

This is **not the DFM model described in the paper**. It does not implement
the causal memory predictor, learned chunk-level parametric memory, gated
cross-attention inside transformer hidden states, training/fine-tuning,
frozen-backbone adaptation, weight export, or inference-time fast path.
No paper weights, training artifacts, or SHA-256 hashes are claimed.

The registry's cosine similarity is used only to detect duplicate candidates
at promotion time. It is not DFM inference and does not eliminate online
retrieval. The current crate is in-memory; it does not commit to DuckDB or the
Rust atomic substrate. DELETE arbitration and durable atomic promotion are
future integration work.

## Architecture invariants

1. Atomic substrate remains authoritative; DFM is a derived, reproducible tier.
2. Mem0 proposes ADD/UPDATE/DELETE/NOOP; the AVA-007 gate authorizes promotion.
3. Backbone weights remain frozen unless a separately approved training plan
   explicitly says otherwise.
4. Dream-RSI remains available when no validated parametric memory applies.
5. Every promoted memory and prediction must carry provenance, generation,
   model/artifact identity, and A2A evaluation evidence.

## Verification

From `air-ava007/`:

```sh
cargo fmt --all -- --check
cargo test --workspace --all-targets
cargo clippy --workspace --all-targets -- -D warnings
```

Crate tests cover local validation and promotion decisions only. They do not
validate DFM paper results, model quality, hidden-state fusion, training,
latency, or end-to-end Exoskeleton persistence.
