// Process control for the Cab Deck server: spawn server.py as a child (or attach to one that is
// already running), poll its health, keep a log tail, and stop it through POST /api/shutdown.
// Used by main.js. Exports promise-returning startServer / stopServer / restartServer.
//
// States: unavailable | stopped | starting | running | stopping | crashed | attached

const { spawn } = require("child_process");
const { EventEmitter } = require("events");
const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const BASE_URL = "http://127.0.0.1:8000";
const PROBE_MS = 1500;          // health probe at start
const POLL_MS = 1000;           // health poll interval
const POLL_TIMEOUT_MS = 800;    // health request timeout
const STOP_WAIT_MS = 8000;      // wait after the shutdown request
const TERM_WAIT_MS = 3000;      // SIGTERM wait (macOS only)
const LOG_POLL_MS = 2000;       // /api/logs poll for an attached server
const ATTACHED_MISSES = 3;      // failed polls before an attached server counts as stopped
const MAX_LOG_LINES = 500;
const LOG_PUSH_MS = 100;

const NO_PYTHON = "Python environment not found. Run run.bat once to create it, then press Start.";

const events = new EventEmitter();
const isWindows = process.platform === "win32";

let dryRun = false;
let state = "stopped";
let child = null;               // managed child process
let exitCode = null;            // text such as "exit 1" or "signal SIGKILL"
let notice = "";
let health = null;              // last health body that answered ok
let lastOkAt = 0;               // ms timestamp of the last ok poll (or of the spawn)
let failing = false;            // the latest poll failed
let misses = 0;                 // consecutive failed polls (attached)
let pollTimer = null;
let logTimer = null;
let logLines = [];
let logSource = "server";       // "server" (child output) or "attached" (logs/cab_deck.log)
let partial = { out: "", err: "" };
let pushTimer = null;
let busy = null;                // promise of the running operation
let stopping = false;           // a stop was requested by us, so a child exit is not a crash

function pythonPath() {
  return isWindows
    ? path.join(REPO, ".venv", "Scripts", "python.exe")
    : path.join(REPO, ".venv", "bin", "python");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function emitChange() {
  events.emit("change", getSnapshot());
}

function setState(next, text) {
  state = next;
  if (text !== undefined) notice = text;
  emitChange();
}

function getSnapshot() {
  return {
    state: state === "initial" ? "starting" : state,   // "initial" = probing for a running server
    managed: child !== null,
    dryRun,
    exitCode,
    notice,
    health,
    healthAgeS: failing && (child || state === "attached") ? Math.max(1, Math.floor((Date.now() - lastOkAt) / 1000)) : 0,
  };
}

function getLog() {
  return { source: logSource, lines: logLines };
}

// ---- log tail ----

function schedulePush() {
  if (pushTimer) return;
  pushTimer = setTimeout(() => {
    pushTimer = null;
    events.emit("log", getLog());
  }, LOG_PUSH_MS);
}

function addLines(lines) {
  if (!lines.length) return;
  logLines = logLines.concat(lines).slice(-MAX_LOG_LINES);
  schedulePush();
}

function setLogLines(lines, source) {
  logLines = lines.slice(-MAX_LOG_LINES);
  logSource = source;
  schedulePush();
}

function feed(key, chunk) {
  const text = partial[key] + chunk.toString("utf8");
  const parts = text.split(/\r?\n/);
  partial[key] = parts.pop();
  addLines(parts);
}

function flushPartial() {
  const rest = [partial.out, partial.err].filter(Boolean);
  partial = { out: "", err: "" };
  addLines(rest);
}

// ---- HTTP ----

async function request(pathname, options = {}, timeoutMs = POLL_TIMEOUT_MS) {
  return fetch(BASE_URL + pathname, { ...options, signal: AbortSignal.timeout(timeoutMs) });
}

// Returns the health body when the server answers status "ok", otherwise null.
async function probeHealth(timeoutMs = POLL_TIMEOUT_MS) {
  try {
    const res = await request("/api/health", {}, timeoutMs);
    if (!res.ok) return null;
    const body = await res.json();
    return body && body.status === "ok" ? body : null;
  } catch (err) {
    return null;
  }
}

async function requestShutdown() {
  try {
    const res = await request("/api/shutdown", { method: "POST", headers: { "X-Cab-Deck-Console": "1" } }, 2000);
    return res.status === 202;
  } catch (err) {
    return false;
  }
}

// ---- polling ----

function stopTimers() {
  clearInterval(pollTimer);
  clearInterval(logTimer);
  pollTimer = null;
  logTimer = null;
}

async function pollOnce() {
  const body = await probeHealth();
  if (state !== "starting" && state !== "running" && state !== "attached" && state !== "stopping") return;
  if (body) {
    health = body;
    lastOkAt = Date.now();
    failing = false;
    misses = 0;
    if (state === "starting") setState("running", "");
    else emitChange();
    return;
  }
  failing = true;
  misses += 1;
  if (state === "attached" && misses >= ATTACHED_MISSES) {
    stopTimers();
    clearHealth();
    setState("stopped", "The server that was already running has stopped.");
    return;
  }
  emitChange();
}

function clearHealth() {
  health = null;
  failing = false;
  misses = 0;
}

async function pollLogs() {
  try {
    const res = await request("/api/logs?lines=200", {}, 1500);
    if (!res.ok) return;
    const text = await res.text();
    if (state === "attached") setLogLines(text.split(/\r?\n/).filter(Boolean), "logs/cab_deck.log");
  } catch (err) {
    // The next health poll decides whether the server is gone.
  }
}

function startPolling(withLogs) {
  stopTimers();
  pollTimer = setInterval(pollOnce, POLL_MS);
  if (withLogs) {
    pollLogs();
    logTimer = setInterval(pollLogs, LOG_POLL_MS);
  }
}

// ---- start ----

function attach(body) {
  child = null;
  exitCode = null;
  health = body;
  lastOkAt = Date.now();
  failing = false;
  misses = 0;
  logLines = [];
  logSource = "logs/cab_deck.log";
  setState("attached", "A server was already running; the console did not start it.");
  startPolling(true);
}

function spawnServer() {
  const python = pythonPath();
  if (!fs.existsSync(python)) {
    setState("unavailable", NO_PYTHON);
    return;
  }
  const args = ["-u", "server.py"];
  if (dryRun) args.push("--dry-run");
  logLines = [];
  logSource = "server";
  partial = { out: "", err: "" };
  exitCode = null;
  stopping = false;
  clearHealth();
  lastOkAt = Date.now();
  const proc = spawn(python, args, {
    cwd: REPO,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
  });
  child = proc;
  proc.stdout.on("data", (chunk) => feed("out", chunk));
  proc.stderr.on("data", (chunk) => feed("err", chunk));
  proc.on("error", (err) => {
    if (child !== proc) return;
    child = null;
    stopTimers();
    addLines([`Cannot start the server: ${err.message}`]);
    setState("crashed", `Cannot start the server: ${err.message}`);
  });
  proc.on("exit", (code, signal) => onChildExit(proc, code, signal));
  setState("starting", "");
  startPolling(false);
  pollOnce();
}

function onChildExit(proc, code, signal) {
  if (child !== proc) return;
  child = null;
  flushPartial();
  events.emit("child-exit");
  if (stopping) return;   // the stop sequence reports the result
  stopTimers();
  clearHealth();
  exitCode = signal ? `signal ${signal}` : `exit ${code}`;
  setState("crashed", `The server exited (${exitCode}).`);
}

async function doStart() {
  if (state !== "stopped" && state !== "crashed" && state !== "unavailable" && state !== "initial") return;
  if (!fs.existsSync(pythonPath())) {
    // A server started elsewhere can still be attached without the venv.
    const body = await probeHealth(PROBE_MS);
    if (body) attach(body);
    else setState("unavailable", NO_PYTHON);
    return;
  }
  const body = await probeHealth(PROBE_MS);
  if (body) attach(body);
  else spawnServer();
}

// ---- stop ----

function waitForExit(proc, ms) {
  return new Promise((resolve) => {
    if (child !== proc) return resolve(true);
    const timer = setTimeout(() => {
      events.removeListener("child-exit", onExit);
      resolve(false);
    }, ms);
    function onExit() {
      clearTimeout(timer);
      resolve(true);
    }
    events.once("child-exit", onExit);
  });
}

async function waitForGone(ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    await sleep(300);
    if (!(await probeHealth(500))) return true;
  }
  return false;
}

async function stopManaged(proc) {
  const asked = await requestShutdown();
  if (asked && (await waitForExit(proc, STOP_WAIT_MS))) return true;
  if (!isWindows && child === proc) {
    proc.kill("SIGTERM");
    if (await waitForExit(proc, TERM_WAIT_MS)) return true;
  }
  if (child === proc) proc.kill();
  await waitForExit(proc, 2000);
  return false;
}

async function doStop() {
  if (state !== "starting" && state !== "running" && state !== "attached") return;
  const wasAttached = state === "attached";
  const proc = child;
  stopping = true;
  setState("stopping", "");
  if (proc) {
    const graceful = await stopManaged(proc);
    stopTimers();
    clearHealth();
    stopping = false;
    if (graceful) {
      setState("stopped", "");
    } else {
      const warning = "Server did not stop in time and was killed; vJoy buttons may stay down until the server starts again";
      addLines([warning]);
      setState("stopped", warning);
    }
    return;
  }
  if (wasAttached) {
    await requestShutdown();
    const gone = await waitForGone(STOP_WAIT_MS);
    stopping = false;
    if (gone) {
      stopTimers();
      clearHealth();
      setState("stopped", "");
    } else {
      setState("attached", "The server did not stop. Close its window (run.bat).");
    }
    return;
  }
  stopping = false;
  setState("stopped", "");
}

// ---- public API ----

// One operation at a time: a second call while one runs is ignored.
function exclusive(fn) {
  if (busy) return busy.then(() => undefined);
  busy = fn().catch((err) => {
    console.error(`Server control: ${err.stack || err}`);
  }).finally(() => {
    busy = null;
  });
  return busy;
}

function startServer() {
  return exclusive(doStart);
}

function stopServer() {
  return exclusive(doStop);
}

function restartServer() {
  return exclusive(async () => {
    await doStop();
    if (state === "stopped" || state === "crashed" || state === "unavailable") await doStart();
  });
}

// Called once at app start: attach to a running server or spawn one (R7, R8).
function init(options) {
  dryRun = Boolean(options && options.dryRun);
  state = "initial";
  return startServer();
}

// Waits for a running operation, then stops a managed server. An attached server is left alone (R20).
async function stopManagedForQuit() {
  if (busy) await busy;
  if (child) await stopServer();
}

// Last resort when the quit cap is over: end the child without waiting.
function killNow() {
  if (child) {
    try {
      child.kill();
    } catch (err) {
      console.error(`Cannot kill the server: ${err.message}`);
    }
  }
}

function isManaged() {
  return child !== null;
}

module.exports = {
  events,
  init,
  startServer,
  stopServer,
  restartServer,
  stopManagedForQuit,
  killNow,
  isManaged,
  getSnapshot,
  getLog,
};
