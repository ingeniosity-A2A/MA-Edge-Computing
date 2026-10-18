/**
 * Self-test for the Call Control dialer script.
 *
 * Runs the real CLI against an in-process mock of the Telnyx V2 API so the
 * request sequence (dial -> speak -> hangup) and the error paths are exercised
 * without spending money on a live call:
 *
 *   node --test scripts/
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "telnyx-test-call.mjs");

function mockTelnyx({ speakFails = 0, dialFails = false } = {}) {
  const seen = [];
  let speakAttempts = 0;

  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      const body = raw ? JSON.parse(raw) : {};
      seen.push({ method: req.method, url: req.url, auth: req.headers.authorization, body });
      res.setHeader("Content-Type", "application/json");

      if (req.method === "POST" && req.url === "/calls") {
        if (dialFails) {
          res.statusCode = 422;
          res.end(
            JSON.stringify({
              errors: [{ code: "10009", detail: "Destination number is invalid" }],
            })
          );
          return;
        }
        res.statusCode = 200;
        res.end(JSON.stringify({ data: { call_control_id: "v3:test-call-id", call_leg_id: "leg" } }));
        return;
      }
      if (req.method === "POST" && req.url.endsWith("/actions/speak")) {
        speakAttempts += 1;
        if (speakAttempts <= speakFails) {
          res.statusCode = 422;
          res.end(JSON.stringify({ errors: [{ code: "90005", detail: "Call is not active" }] }));
          return;
        }
        res.end(JSON.stringify({ data: { result: "ok" } }));
        return;
      }
      if (req.method === "POST" && req.url.endsWith("/actions/hangup")) {
        res.end(JSON.stringify({ data: { result: "ok" } }));
        return;
      }
      res.statusCode = 404;
      res.end(JSON.stringify({ errors: [{ detail: `unhandled ${req.method} ${req.url}` }] }));
    });
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, seen, port: server.address().port });
    });
  });
}

function run(args, env) {
  // The CLI must not silently inherit the developer's real .env during tests.
  const isolated = { ...env, TELNYX_API_KEY: env.TELNYX_API_KEY ?? "" };
  return spawnRun(args, isolated);
}

function spawnRun(args, env) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [script, ...args], {
      env: { TELNYX_WAIT_SCALE: "0.01", TELNYX_ENV_FILE: "/nonexistent/.env", ...process.env, ...env },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (c) => (stdout += c));
    child.stderr.on("data", (c) => (stderr += c));
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

test("dials, speaks, and hangs up in order", async () => {
  const mock = await mockTelnyx();
  try {
    const { code, stdout } = await run(["--to=+14044481708"], {
      TELNYX_API_BASE: `http://127.0.0.1:${mock.port}`,
      TELNYX_API_KEY: "KEY_test",
    });
    assert.equal(code, 0, stdout);

    const paths = mock.seen.map((r) => r.url);
    assert.deepEqual(paths, [
      "/calls",
      "/calls/v3:test-call-id/actions/speak",
      "/calls/v3:test-call-id/actions/hangup",
    ]);
    assert.equal(mock.seen[0].auth, "Bearer KEY_test");
    assert.equal(mock.seen[0].body.to, "+14044481708");
    assert.ok(mock.seen[0].body.connection_id, "dial must carry a connection_id");
    assert.equal(Buffer.from(mock.seen[0].body.client_state, "base64").toString(), "a2a-test-call");
    assert.match(mock.seen[1].body.payload, /test call/i);
    assert.match(stdout, /Call ended/);
  } finally {
    mock.server.close();
  }
});

test("retries speak while the call is still ringing, then hangs up", async () => {
  const mock = await mockTelnyx({ speakFails: 1 });
  try {
    const { code, stdout } = await run(["--to=+14044481708"], {
      TELNYX_API_BASE: `http://127.0.0.1:${mock.port}`,
      TELNYX_API_KEY: "KEY_test",
    });
    assert.equal(code, 0, stdout);
    const speaks = mock.seen.filter((r) => r.url.endsWith("/actions/speak"));
    assert.equal(speaks.length, 2);
    assert.match(stdout, /Speak not ready yet/);
    assert.equal(mock.seen.at(-1).url, "/calls/v3:test-call-id/actions/hangup");
  } finally {
    mock.server.close();
  }
});

test("surfaces a rejected dial and never hangs up a call that was not placed", async () => {
  const mock = await mockTelnyx({ dialFails: true });
  try {
    const { code, stderr } = await run(["--to=+14044481708"], {
      TELNYX_API_BASE: `http://127.0.0.1:${mock.port}`,
      TELNYX_API_KEY: "KEY_test",
    });
    assert.equal(code, 1);
    assert.match(stderr, /HTTP 422/);
    assert.match(stderr, /Destination number is invalid/);
    assert.equal(mock.seen.length, 1, "must not speak or hang up after a failed dial");
  } finally {
    mock.server.close();
  }
});

test("reads credentials from .env so a new shell needs no exports", async () => {
  const mock = await mockTelnyx();
  const dir = mkdtempSync(join(tmpdir(), "telnyx-env-"));
  const envFile = join(dir, ".env");
  writeFileSync(
    envFile,
    [
      "# test env",
      "TELNYX_API_KEY=\"KEY_from_file\"",
      `TELNYX_API_BASE=http://127.0.0.1:${mock.port}`,
      "TELNYX_FROM=+14044391350",
    ].join("\n")
  );
  try {
    const { code, stdout } = await spawnRun(["--to=+14044481708", "--no-speak"], {
      TELNYX_ENV_FILE: envFile,
      TELNYX_API_KEY: "",
    });
    assert.equal(code, 0, stdout);
    assert.equal(mock.seen[0].auth, "Bearer KEY_from_file", "quotes must be stripped from .env values");
    assert.equal(mock.seen[0].body.from, "+14044391350");
    assert.deepEqual(
      mock.seen.map((r) => r.url),
      ["/calls", "/calls/v3:test-call-id/actions/hangup"],
      "--no-speak must skip the speak step"
    );
  } finally {
    mock.server.close();
  }
});

test("a real environment variable wins over .env", async () => {
  const mock = await mockTelnyx();
  const dir = mkdtempSync(join(tmpdir(), "telnyx-env-"));
  const envFile = join(dir, ".env");
  writeFileSync(envFile, `TELNYX_API_KEY=KEY_stale\nTELNYX_API_BASE=http://127.0.0.1:${mock.port}\n`);
  try {
    const { code, stdout } = await spawnRun(["--to=+14044481708", "--no-speak"], {
      TELNYX_ENV_FILE: envFile,
      TELNYX_API_KEY: "KEY_exported",
    });
    assert.equal(code, 0, stdout);
    assert.equal(mock.seen[0].auth, "Bearer KEY_exported");
  } finally {
    mock.server.close();
  }
});

test("exits 2 with guidance when no API key is present", async () => {
  const { code, stderr } = await run(["--to=+14044481708"], { TELNYX_API_KEY: "" });
  assert.equal(code, 2);
  assert.match(stderr, /TELNYX_API_KEY is not set/);
});
