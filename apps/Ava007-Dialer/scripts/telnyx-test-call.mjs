#!/usr/bin/env node
import { readFileSync } from "node:fs";

/**
 * Places a real PSTN test call through Telnyx Call Control.
 *
 *   TELNYX_API_KEY=... node scripts/telnyx-test-call.mjs --to=+14044481708
 *
 * Optional environment:
 *   TELNYX_FROM           caller ID (default +14044391350)
 *   TELNYX_CONNECTION_ID  Call Control / Voice API connection (default 3059923805699835244)
 *   TELNYX_API_BASE       override the API root (used by the self-test mock server)
 *   TELNYX_ENV_FILE       read credentials from this file instead of ./.env
 *
 * The default connection is the "Ava007 Voice" connection currently attached to
 * +14044391350 in the Telnyx account.
 */

/**
 * Loads KEY=VALUE pairs from ./.env without overwriting anything already in the
 * environment, so the key does not have to be exported in every shell (and
 * survives a new terminal). Hand-rolled instead of relying on a Node flag so the
 * script keeps working on older runtimes.
 */
function loadEnvFile(file = new URL("../.env", import.meta.url)) {
  let raw;
  try {
    raw = readFileSync(file, "utf8");
  } catch {
    return false;
  }
  for (const line of raw.split("\n")) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!match) continue;
    const [, key, value] = match;
    if (process.env[key] !== undefined && process.env[key] !== "") continue;
    process.env[key] = value.trim().replace(/^(['"])(.*)\1$/, "$2");
  }
  return true;
}

loadEnvFile(process.env.TELNYX_ENV_FILE || new URL("../.env", import.meta.url));

const API = process.env.TELNYX_API_BASE || "https://api.telnyx.com/v2";
const DEFAULT_TO = "+14044481708";
const DEFAULT_FROM = "+14044391350";
const DEFAULT_CONNECTION_ID = "3059923805699835244";

const argv = process.argv.slice(2);
const dryRun = argv.includes("--dry-run");
const noSpeak = argv.includes("--no-speak");
const toOption = argv.find((a) => a.startsWith("--to="));
const to = toOption ? toOption.slice("--to=".length) : DEFAULT_TO;

const apiKey = process.env.TELNYX_API_KEY;
const from = process.env.TELNYX_FROM || DEFAULT_FROM;
const connectionId = process.env.TELNYX_CONNECTION_ID || DEFAULT_CONNECTION_ID;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// Tests shorten the polling delays; a real call always runs at 1x.
const waitScale = Number(process.env.TELNYX_WAIT_SCALE || "1");
const wait = (ms) => sleep(Math.round(ms * waitScale));

async function call(path, { method = "POST", body } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await response.text();
  let json;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text };
  }

  if (!response.ok) {
    const detail = JSON.stringify(json?.errors ?? json);
    throw new Error(`${method} ${path} -> HTTP ${response.status}: ${detail}`);
  }
  return json;
}

async function main() {
  const dialBody = {
    connection_id: connectionId,
    from,
    to,
    timeout_secs: 30,
    client_state: Buffer.from("a2a-test-call").toString("base64"),
  };

  console.log(`Telnyx Call Control test call`);
  console.log(`  from : ${from}`);
  console.log(`  to   : ${to}`);
  console.log(`  conn : ${connectionId}`);

  if (dryRun) {
    console.log("\n--dry-run, request body:");
    console.log(JSON.stringify(dialBody, null, 2));
    return;
  }

  if (!apiKey) {
    console.error(
      "\nTELNYX_API_KEY is not set. Put it in .env (gitignored) or export it:\n" +
        "  printf 'TELNYX_API_KEY=%s\\n' 'KEY_...' >> .env   # then rerun this script\n" +
        "  TELNYX_API_KEY=KEY_... node scripts/telnyx-test-call.mjs --to=" +
        to
    );
    process.exitCode = 2;
    return;
  }

  const dial = await call("/calls", { body: dialBody });
  const callControlId = dial?.data?.call_control_id;
  if (!callControlId) {
    throw new Error(`No call_control_id in response: ${JSON.stringify(dial)}`);
  }
  console.log(`\nDialing… call_control_id=${callControlId}`);

  if (!noSpeak) {
    let spoken = false;
    for (const waitMs of [12_000, 8_000, 8_000]) {
      await wait(waitMs);
      try {
        await call(`/calls/${callControlId}/actions/speak`, {
          body: {
            payload:
              "This is a test call from Ava 0 0 7. The Telnyx dialer is working. Goodbye.",
            voice: "female",
            language: "en-US",
          },
        });
        spoken = true;
        console.log("Callee answered; test message is playing.");
        break;
      } catch (error) {
        console.log(`Speak not ready yet: ${error.message}`);
      }
    }
    if (!spoken) {
      console.log("Call was not answered in time; hanging up.");
    }
    await wait(spoken ? 8_000 : 2_000);
  }

  await call(`/calls/${callControlId}/actions/hangup`, { body: {} });
  console.log("Call ended.");
}

main().catch((error) => {
  console.error(`\nTest call failed: ${error.message}`);
  process.exitCode = 1;
});
