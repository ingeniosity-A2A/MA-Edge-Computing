# Air-Ava007

Air-Ava007 is the Rust-native execution and evidence substrate owned by **MA-Edge-Computing**. It is the renamed successor to the Air-LLM design, not a new AI model and not a quantum computer.

## Architectural contract

- **TurboVec proposes** candidate neighbors.
- **TurboQuant compresses** representations and reports quantization distortion.
- **Rev.ike verifies** candidates and promotion decisions.
- **GSAP schedules** execution, dependencies, synchronization, cancellation, and lifecycle.
- **The canonical timeline arbitrates** in both the logical application plane and the physical RF plane.
- **Rust is the substrate**; quantum-inspired methods remain optional and must beat classical baselines under reproducible tests.

## Workspace

- `crates/air-core`: canonical memory records, source provenance, verdict contracts.
- `crates/air-index`: vector-index contract and adapter boundary.
- `crates/air-ledger`: append-only evidence-ledger contract and DuckDB adapter boundary.
- `crates/air-gate`: Rev.ike BM25/RRF/SPR promotion and verification gates.

No placeholder implementation is represented as measured or production-ready. DuckDB, TurboVec, TurboQuant, and GSAP adapters must be pinned and verified against the actual upstream versions before the full workspace is declared green.

## Verify

From this directory:

```sh
make fmt-check
make lint
make test
make verify
```

`make verify` also runs the ledger audit; it must remain blocked until the audit binary and a real local ledger fixture are present. A missing trace is not a passing benchmark.
