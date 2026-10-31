# fapo-ran — RAN only

This repository is **strictly RAN**:

- `ran_capability/` — FAPO, SafetyEnvelope, adapters
- `srsran-patch/` — gNB scheduler control
- digital twin / fake gNB for tests

## Allowed containers (logical)

```text
containers/   (optional future)
├── ran-stack/      # srsRAN, gNB, UE harness
├── ran-gpu/        # Aerial CUDA if used
├── rf-front-end/   # SDR attached to gNB only
└── fapo-controller/
```

## Forbidden here

- Telnyx / carrier APIs
- SoftSIM provisioning
- Generic Termux USB modem stacks
- Onomondo / nRF91 product integration (Agent-X `cellular-edge`)
- SX1262 application LoRa (Agent-X `rf-edge`)

Ava007 imports only `ava007.capabilities` + `ran_capability.capability`.
