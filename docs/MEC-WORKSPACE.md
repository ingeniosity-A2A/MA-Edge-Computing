# MEC workspace map (A)

Repository: `ingeniosity-A2A/MA-Edge-Computing`

## Tree (as of main)

```
MA-Edge-Computing/
├── README.md
├── S26ULTRA                    # device plane + GenieX reference
├── apps/
│   └── Ava007-Dialer/           # Android Gradle project ONLY
│       ├── app/                  # com.s26ultra.a2a
│       ├── gradle/wrapper/       # Gradle 8.11.1
│       ├── scripts/              # bootstrap, telnyx test (Node)
│       ├── build.gradle.kts
│       ├── settings.gradle.kts
│       └── README.md
├── docs/                       # workspace + container notes
└── .github/workflows/           # present; not required for acceptance
```

## JS vs Android

| Area | Tooling | Notes |
|------|---------|--------|
| `apps/Ava007-Dialer` | **Gradle 8.11.1**, JDK 17, SDK 36 | Produces APK |
| `apps/Ava007-Dialer/scripts/*.mjs` | Node (optional) | Telnyx test only |
| Repo root | **No** `package.json` / `pnpm-workspace.yaml` | Do not invent a pnpm root that owns the Android module |

## pnpm policy

- Use pnpm **only** if a future JS package is added under e.g. `packages/*` and registered in `pnpm-workspace.yaml`.
- Never route `:app:assembleDebug` through pnpm.
- pin / workspace guidance for Cybernetic-Ava007 intellect stays separate from this MEC Android tree.

## Dialer identity

- Application id / package: `com.s26ultra.a2a`
- Self-managed VoIP (Telnyx WebRTC) + Telecom bridge
- Target device plane: Galaxy S26 Ultra
