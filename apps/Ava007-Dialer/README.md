# Ava007 Dialer (`com.s26ultra.a2a`)

Self-managed Android VoIP dialer for the S26 Ultra. Calls are negotiated with the
Telnyx WebRTC SDK and owned end-to-end by a `CAPABILITY_SELF_MANAGED`
`PhoneAccount`, so they never enter the carrier dialer.

## What is implemented

| Piece | File |
| --- | --- |
| Self-managed `PhoneAccount` + `TelecomManager.placeCall` | `telecom/VoIPAccountManager.kt` |
| `ConnectionService` (outgoing call lifecycle) | `telecom/A2AConnectionService.kt` |
| Self-managed `Connection` | `telecom/A2AConnection.kt` |
| Telnyx ↔ Telecom state bridge | `telecom/TelecomCallCoordinator.kt` |
| Telnyx WebRTC client (SIP credential login, INVITE, hangup) | `telnyx/TelnyxSession.kt` |
| `InCallService` hook | `telecom/A2AInCallService.kt` |
| `RoleManager.ROLE_DIALER` opt-in | `telecom/DialerRole.kt` |
| Android 17 call-log integration activity | `settings/CallLogIntegrationActivity.kt` |
| Dial screen | `MainActivity.kt`, `res/layout/activity_main.xml` |
| Call Control test-call script | `scripts/telnyx-test-call.mjs` |
| Wrapper/mode bootstrap for a fresh clone | `scripts/bootstrap-wrapper.sh` |

## Corrections to the "Android 17 Step 2" snippet

1. **`CAPABILITY_SELF_MANAGED | CAPABILITY_CALL_PROVIDER` is rejected by the
   platform.** Android's CTS asserts that registering that combination fails.
   The app registers `CAPABILITY_SELF_MANAGED` alone. This is the cause of the
   most common "account never appears" bug.
2. **`ROLE_DIALER` is not required for self-managed calls.** Self-managed
   accounts already bypass the carrier dialer. Requesting the role makes this
   app responsible for ordinary SIM calls (and their in-call UI), which is why
   it is an explicit, warned opt-in rather than automatic startup behaviour.
3. **`InCallService` is present but not load-bearing.** It is needed for
   `ROLE_DIALER` eligibility; self-managed call UI is `MainActivity`.
4. **`android.telecom.action.CONFIGURE_CALL_LOG_INTEGRATION` is real** and is
   handled by `CallLogIntegrationActivity`. It is an Android 17 (API 37)
   surface, so it is referenced as a manifest string and works with
   `compileSdk 36`.

## Telnyx setup still required

The Telnyx account currently has:

- number `+14044391350` on connection `3059923805699835244` ("Ava007 Voice")
- IP connection `3062153998363526227` ("Main Mobile Connection")
- credential connection `2924938123731273132` ("Forward Only")
- balance `$4.99`

The app logs in with **SIP credentials** (`sipUser` / `sipPassword`) from a
Telnyx *Credential Connection* that has an *Outbound Voice Profile* attached.
An IP connection does not have a SIP username/password, so if "Main Mobile
Connection" is the intended WebRTC endpoint, a credential connection (or
on-demand SIP credentials) must be created in the Telnyx portal first.

Enter the SIP credentials in the app, set the caller ID to `+14044391350`, tap
**Connect to Telnyx**, then **Call over Telnyx**.

## Build

Requires JDK 17 and Android SDK platform 36 / build-tools 36.

This repository was seeded through the GitHub API, which cannot carry binaries
and commits every file as mode 644. Before the first build, restore both:

```bash
./scripts/bootstrap-wrapper.sh    # or: bash scripts/bootstrap-wrapper.sh
```

That fetches `gradle/wrapper/gradle-wrapper.jar` from `gradle/gradle` at the
version in `gradle-wrapper.properties` (byte-identical to the jar the project
was built with) and marks `gradlew` and the shell scripts executable. Then:

```bash
export ANDROID_HOME=/path/to/android-sdk
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The debug APK is ~54 MB because it bundles the WebRTC native libraries.

Notes:

- The SDK is resolved from JitPack:
  `com.github.team-telnyx:telnyx-webrtc-android:3.7.3`.
- `compileSdk`/`targetSdk` are 36; API 37 was not available in the SDK
  repository used here. The call-log intent is declared as a string so it does
  not need the API 37 platform to compile.
- The SIP password is intentionally not persisted; only the username and
  caller ID are saved in `SharedPreferences`.

## Test call (server-side, no phone required)

`scripts/telnyx-test-call.mjs` places a real PSTN call through Call Control,
speaks a short message, and hangs up:

```bash
TELNYX_API_KEY=KEY_... node scripts/telnyx-test-call.mjs --to=+14044481708
```

- `--dry-run` prints the request body without calling.
- `--no-speak` just dials and hangs up.
- The default caller ID is `+14044391350` and the default connection is
  `3059923805699835244`.

The script also reads `./.env` on its own (real environment variables win), so
the usual flow is one edit and then a plain run:

```bash
# .env, gitignored, chmod 600
TELNYX_API_KEY=KEY_...
```

```bash
node scripts/telnyx-test-call.mjs --to=+14044481708
```

Or store the key without it ever appearing in scrollback: `./scripts/set-key.sh`
prompts with hidden input, validates the key against `/v2/balance`, and only
writes `.env` (mode 600, other values preserved) after Telnyx returns 200. A
typo or a revoked key changes nothing.

`.env` is deliberately untracked, so it does not travel with the repo: if this
workspace is re-created, restore it from `.env.example`. Losing the file loses
the key - it cannot be read back out of the Telnyx integration, so keep it in a
password manager too.

This verifies the Telnyx number, outbound voice configuration, and PSTN
routing independently of the APK.

The request contract is covered by an offline suite that runs the real CLI
against a mock Telnyx API (dial → speak → hangup order, speak retry while
ringing, rejected dial, `.env` loading and precedence, missing key):

```bash
node --test scripts/*.test.mjs
```

## Known limitations

- Incoming Telnyx invites are not bridged into Telecom yet
  (`onCreateIncomingConnection` returns a failed connection).
- Hold is advertised as a capability but is a no-op.
- No foreground call notification for the self-managed call while the app is
  backgrounded.
- The APK was compiled but not installed on a device or exercised against a
  live SIP registration in this environment.
