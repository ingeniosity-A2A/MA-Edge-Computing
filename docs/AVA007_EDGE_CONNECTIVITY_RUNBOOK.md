# AVA-007 Edge Connectivity Runbook: S26 Ultra → Tailnet → OVH VPS

**Status:** Implementation runbook; live device/VPS state must be checked at execution time.  
**Scope:** Tailscale Android SDK, cellular/eSIM boundaries, private VPS reachability, Aperture, and OpenSandbox.  
**No GitHub Actions required.**

## Target topology

```text
Carrier eSIM / physical SIM + Android modem
                 │  (provides the actual upstream connection)
                 ▼
Samsung Galaxy S26 Ultra (Android 16/17, ARM64)
  ├─ Android telephony/eSIM APIs (permission- and carrier-controlled)
  ├─ Tailscale Android client / embedded libtailscale AAR
  └─ Termux + Debian proot (diagnostics/dev; not the modem or kernel)
                 │ encrypted Tailscale/WireGuard tailnet
                 ▼
OVH Ubuntu VPS (persistent tailnet node)
  ├─ private inference/API services
  ├─ OpenSandbox control plane (private, authenticated)
  └─ optional Tailscale exit-node role (only if explicitly enabled)
                 │
                 └─ Aperture gateway on its configured tailnet
```

The phone's cellular connection is the upstream network. Tailscale supplies encrypted reachability over that connection; the VPS can be an exit node for traffic routing, but it does not create cellular service or provide an eSIM subscription.

## 1. Existing repository components

- `apps/Tailscale-Android-SDK/` builds the upstream Tailscale Android project and produces `libtailscale.aar` plus a debug APK. The build script uses upstream source rather than a divergent fork.
- `apps/TailSocks/` documents a usable Android client path for the S26 Ultra, including Proxy and VPN/TUN modes.
- `apps/Ava007-GenieX/` is a separate on-device inference integration. Do not mix its Gradle dependencies into the Tailscale SDK project.
- The SDK AAR build is not equivalent to embedding a working node in Ava007's app. The host app still needs an explicit integration, Android VPN/user-consent handling, node state lifecycle, and on-device tests.

## 2. Critical 5G/eSIM boundary

The Android `EuiccManager` API manages supported eSIM operations when the device exposes eUICC support and the required carrier/platform permissions are satisfied. It is not a software modem API.

An ordinary Android SDK cannot replace the Snapdragon modem/baseband or implement a complete 5G modem in user space. A true software-defined modem requires compatible RF hardware, PHY/MAC implementation, drivers/firmware, a supported radio stack, and authorized spectrum/network access. Keep this project on the supported-device side: manage available connectivity, inspect network state with permitted Android APIs, and run Tailscale over the active mobile-data interface.

Do not silently download/install an eSIM profile, change carrier plans, alter radio bands, or switch a device's active subscription without the user's explicit Android/carrier flow.

## 3. Establish the VPS tailnet node

Run these checks on the Ubuntu VPS before modifying routes or firewall policy:

```bash
uname -m
cat /etc/os-release
tailscale version
tailscale status
tailscale ip -4
ip route
systemctl is-active tailscaled
```

If Tailscale is not installed, use the official Tailscale Ubuntu installation instructions for the current OS release. Then authenticate the VPS to the intended tailnet using the approved operator flow. Do not paste an auth key into shell history, a repository, or a chat transcript.

After the node appears in the Tailscale admin console, record its tailnet IP, MagicDNS name, tags, and advertised routes. Apply least-privilege Tailscale Grants to the specific source identity and service port. Do not advertise subnet routes or enable exit-node routing as a side effect of installation.

## 4. Bring up the S26 Ultra node

Preferred first validation: use the existing, maintained TailSocks/Tailscale Android integration. Sign in through the app's interactive authentication flow and confirm that the phone and VPS appear in the same tailnet.

On Termux, collect diagnostics without assuming that the Tailscale Android VPN service is installed inside Termux:

```bash
printf '%s\n' '=== DEVICE ==='
getprop ro.product.model
getprop ro.build.version.release
getprop ro.build.version.sdk
printf '%s\n' '=== NETWORK ==='
ip route
getprop | grep -i 'net.dns'
printf '%s\n' '=== TAILSCALE CLI (IF PRESENT) ==='
command -v tailscale || true
tailscale status 2>&1 || true
```

Use the Android client UI to verify its VPN permission and node status. Android VPN/TUN mode routes traffic only after the user approves the system VPN dialog. A CLI binary inside Termux is not a substitute for the Android VPN service.

Only after direct node-to-node connectivity works should the app integration move from an AAR build artifact to an embedded node lifecycle. The app must handle authentication, logout, network changes, VPN consent, background restrictions, reconnects, and safe shutdown.

## 5. Verify the private tunnel

From an authorized client, verify the VPS tailnet IP and only the intended service port. Example placeholders must be replaced with the actual values discovered above:

```bash
tailscale ping <vps-magicdns-name>
curl --connect-timeout 5 http://<vps-tailnet-ip>:<health-port>/health
```

If the phone is using TailSocks VPN/TUN mode, test the private VPS service while cellular data is the upstream network. Record the active network, tailnet status, DNS behavior, route behavior, and reconnect outcome. Do not declare the tunnel verified from a successful ping alone.

If an exit node is needed to route phone traffic through the VPS, configure it explicitly in the Android Tailscale client and verify that forwarding/NAT and the VPS's egress policy are correctly configured. Keep a recovery path before changing default routes. A Tailscale exit node still requires working Wi-Fi or cellular data as its upstream.

## 6. Aperture by Tailscale

Aperture is the LLM gateway/agent entry point, not the A2A protocol and not a generic VPN. Keep its existing live configuration. Merge reviewed provider/connector fragments through the installed Aperture admin configuration; never replace the full configuration with an example.

For a self-hosted OpenAI-compatible inference server on the VPS, the provider entry has this shape:

```json
{
  "providers": {
    "ava007-edge": {
      "name": "AVA-007 private edge inference",
      "baseurl": "http://<vps-tailnet-ip>:<inference-port>",
      "models": ["<exact-model-id>"],
      "compatibility": {
        "openai_chat": true
      }
    }
  }
}
```

This is a template, not a deployable config until the real endpoint, port, and model ID are verified. The base URL should not include a trailing `/v1` when the client sends `/v1/chat/completions`, because Aperture appends the incoming path. Keep the upstream reachable only over the tailnet or loopback; use TLS where appropriate for the actual topology. Scope model grants to the intended user/device, and configure quotas and capture retention intentionally.

After saving, test the exact model in the Aperture admin Models page and from the authorized client. Do not store provider API keys or tailnet auth keys in this repository.

For a device that is not itself a tailnet member, use the documented Aperture CLI bridge or `ts-unplug` flow. Treat the embedded bridge as a separate tailnet identity; it does not automatically enroll the host OS.

## 7. OpenSandbox on the VPS

OpenSandbox provides sandbox lifecycle and execution APIs; it is not a modem or a Tailscale substitute. Start with the upstream Docker example on a supported Linux host and confirm the health endpoint before connecting any agent:

```bash
uvx opensandbox-server init-config ~/.sandbox.toml --example docker
uvx opensandbox-server
```

In a second terminal on the VPS:

```bash
curl --fail --show-error --connect-timeout 5 http://127.0.0.1:8080/health
```

The upstream quick start documents a local health endpoint at port 8080. Verify the actual server configuration and bind address before changing it. Keep the control API on loopback or a private tailnet interface; do not publish port 8080 to the public internet. If remote access is needed, place it behind an authenticated private endpoint and restrictive firewall/egress policy.

The Exoskeleton should expose only bounded capabilities to AVA-007: create a sandbox, execute a constrained job, retrieve logs/results, and terminate the sandbox. Enforce CPU/memory/time limits, outbound-network policy, image allowlists, per-task identity, secret isolation, and audit logging. Never give an untrusted model an unrestricted host shell or Docker socket.

## 8. DPI handling

Do not add GoodbyeDPI/ByeDPI as a default dependency. First determine whether the actual failure is DNS, IPv6 routing, carrier filtering, MTU, Tailscale control-plane reachability, Android VPN conflicts, or an endpoint firewall. DPI tools do not create an upstream internet connection and may be platform-incompatible or conflict with the VPN. Test the documented Tailscale transport and DNS paths first; consider any additional traffic-handling tool only after a measured diagnosis and review of applicable network terms/law.

## 9. Acceptance checklist

- [ ] S26 Ultra has a working carrier data connection independent of Tailscale.
- [ ] Phone and OVH VPS appear as authenticated nodes in the intended tailnet.
- [ ] Direct private VPS health check succeeds from the phone.
- [ ] DNS, reconnect, sleep/wake, and cellular network-change tests pass.
- [ ] Exit-node routing is enabled only if explicitly required and verified.
- [ ] Aperture provider endpoint/model is exact and its test request succeeds.
- [ ] Aperture grants are least-privilege; secrets are not stored in Git.
- [ ] OpenSandbox health check succeeds on loopback and is not publicly exposed.
- [ ] Sandbox jobs enforce resource and network limits and return inspectable logs.
- [ ] Embedded AAR integration is built and tested separately from the standalone client.
- [ ] All live claims include device/OS versions, commands, results, and timestamps.

## Source references

- Tailscale Android SDK source: https://github.com/tailscale/tailscale-android
- TailSocks upstream: https://github.com/bropines/tailsocks
- Aperture configuration: https://tailscale.com/docs/aperture/configuration
- Aperture private/self-hosted provider: https://tailscale.com/docs/aperture/how-to/use-self-hosted
- Aperture bridge / ts-unplug: https://tailscale.com/docs/aperture/connect-outside-tailnet
- OpenSandbox: https://github.com/opensandbox-group/OpenSandbox
- Android EuiccManager: https://developer.android.com/reference/android/telephony/euicc/EuiccManager


## 10. TEAL eSIM and connectivity orchestration

TEAL is a carrier-neutral connectivity/eSIM orchestration platform, not a software modem. If the intended provider is TEAL, integration is an optional control-plane adapter around an eSIM-capable device and a provisioned TEAL/carrier plan.

Before implementing the TEAL adapter, confirm all of the following with the operator account:

- The S26 Ultra model/region and active firmware support the required eSIM profile type and carrier provisioning path.
- The TEAL account has API access, an approved device/eSIM record, and an active data plan with compatible carrier/APN configuration.
- The intended API base URL, authentication mechanism, request-ID requirements, callback URL, rate limits, and supported operations are confirmed from the account's current TEAL documentation.
- Profile installation/activation follows the Android system UI, carrier privileges, TEAL account policy, and applicable GSMA remote-provisioning requirements.

The adapter should initially be read-only: query the authorized eSIM/device status, assigned plan, and usage/status metadata. Use unique request IDs and bounded retries for state-changing API calls. Profile assignment, data enable/suspend, or profile switching must require explicit operator authorization and should never be triggered automatically by a model's free-form output.

Keep TEAL API credentials in a server-side secret store, preferably behind a narrow backend adapter. Do not embed enterprise TEAL credentials in the APK, Termux scripts, prompts, or Git. Do not log EID, ICCID, IMSI, activation codes, or profile payloads. Store only the minimum operational metadata required for diagnostics.

Reference material:
- TEAL platform: https://teal.io/
- TEAL API access documentation (account access may be required): https://tealcommunications.atlassian.net/wiki/spaces/TD/pages/843186179/API+Access+to+Teal+Enterprise+Platform
- Android eSIM architecture: https://source.android.com/docs/core/connect/esim-overview

**Important:** TEAL profile orchestration, Android eSIM APIs, the Qualcomm modem/baseband, Tailscale networking, and the OVH VPS tunnel are five distinct layers. A successful TEAL API call does not prove that the device has active cellular data, and a working Tailscale tunnel does not prove that the eSIM plan is active.

## 11. Acceptance additions

- [ ] TEAL API access and the device's eligibility are confirmed by the account owner/provider.
- [ ] Read-only status lookup succeeds without exposing subscriber identifiers in logs.
- [ ] State-changing eSIM operations remain disabled until explicit authorization and rollback/recovery procedures are tested.
- [ ] The phone establishes cellular data before tailnet tunnel tests begin.


## 12. Executable network bootstrap (committed to `main`)

The first implementation layer is now in `ops/network/`:

- `vps-install-tailscale.sh`: guarded Ubuntu-only installer; enables `tailscaled`, prints service/node state, and leaves authentication interactive. It does not enable exit-node routing, forwarding, subnet routes, or public ports.
- `edge-preflight.sh`: read-only Termux/Android network diagnostics, DNS/control-plane reachability, optional tailnet IP ping, and optional private health URL check.

### Install Tailscale on the VPS

Review the script, then run on the VPS:

```bash
git clone https://github.com/ingeniosity-A2A/MA-Edge-Computing.git
cd MA-Edge-Computing
sudo bash ops/network/vps-install-tailscale.sh
```

Authenticate only through the interactive URL that Tailscale prints:

```bash
sudo tailscale up
tailscale status
tailscale ip -4
```

Do not repeat `tailscale up` with extra flags unless those settings have been explicitly reviewed. This first pass deliberately does not configure an exit node.

### Capture phone diagnostics

On Termux, after confirming the Android Tailscale app is signed in:

```bash
git clone https://github.com/ingeniosity-A2A/MA-Edge-Computing.git
cd MA-Edge-Computing
bash ops/network/edge-preflight.sh
```

After retrieving the *current* VPS tailnet IP from `tailscale ip -4`, rerun:

```bash
VPS_TAILNET_IP=100.x.y.z bash ops/network/edge-preflight.sh
```

Replace the example IP with the real value; do not assume historical IPs are current. A ping failure is not by itself proof that Tailscale is broken because ICMP may be blocked. The final acceptance test must be an authorized TCP/HTTP health request to a service bound to the tailnet interface.

### Current build state

- **Implemented in Git:** the two scripts above and this runbook.
- **Not yet deployed:** no script has been executed on the OVH VPS or S26 Ultra by this Git commit.
- **Not yet verified:** the live tailnet membership, private service reachability, DNS, and reconnect behavior.
- **Next gate:** verify both current tailnet IPs and a successful private TCP health check before starting OpenSandbox or enabling exit-node forwarding.

Official references:
- Tailscale Linux install and status checks: https://tailscale.com/docs/install/linux
- OpenSandbox server configuration and API-key behavior: https://open-sandbox.ai/getting-started/configuration


## 13. Provider decision: TEAL is not a network dependency

**Decision:** TEAL is excluded from the production network's critical path. Marketing claims, API documentation, or an AI-focused product narrative are not evidence that a compatible, working cellular service can be provisioned on this S26 Ultra. No TEAL-specific integration work should block the network build.

The core network must operate independently of any eSIM orchestration vendor:

1. **Upstream:** an already-working physical SIM or eSIM data plan from a carrier that is confirmed to support this exact device and region.
2. **Device networking:** Android's native cellular stack and the official Tailscale Android VPN client.
3. **Private transport:** Tailscale tailnet connectivity to the OVH VPS.
4. **VPS egress and services:** configured separately, with firewall and forwarding enabled only after explicit verification.
5. **Optional eSIM control plane:** a provider adapter may be evaluated later, but it remains disabled until a real device/plan activation test succeeds.

### Acceptance gate for any future eSIM vendor

Do not write a vendor integration based on marketing alone. Require all of the following first:

- Written confirmation of support for the exact device model, carrier profile, geography, and intended use.
- A real test plan and pricing, plus documented provisioning/API access.
- Successful activation on the actual device, with Android showing the profile and a working cellular data session.
- A repeatable test proving connectivity after reboot and after leaving/re-entering coverage.
- Clear rollback and support procedures, with no credentials or activation secrets stored in the app or repository.

Until all gates pass, mark the vendor **unvalidated** and do not make its API a runtime dependency. The baseline build proceeds using a verified carrier connection and Tailscale.
