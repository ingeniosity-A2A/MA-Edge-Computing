RUST_VERSION := 1.99.1

.PHONY: fmt fmt-check lint test audit verify

fmt:
	cargo fmt --all

fmt-check:
	cargo fmt --all -- --check

lint:
	cargo clippy --workspace --all-targets -- -D warnings

test:
	cargo test --workspace --all-targets -- --nocapture

audit:
	@test -x target/release/air-audit || (echo "BLOCKED: air-audit binary not implemented/built yet"; exit 2)
	@test -f ./data/ledger.duckdb || (echo "BLOCKED: local evidence ledger missing"; exit 2)
	./target/release/air-audit --ledger ./data/ledger.duckdb --tolerance 0.02 --sample 1000

verify: fmt-check lint test audit
	@echo "VERIFY PASSED: all Air-Ava007 gates passed under Rust $(RUST_VERSION)"
