// Update from the console: git pull, Python environment and packages, console packages, relaunch.
// Used by main.js. runUpdate() runs inside server-control's one-operation lock and resolves to
// { action: "none" | "relaunch" | "handover", mustRun, canStart }; consumeResultFile() reads the
// note a previous console left before it relaunched.
//
// Git is limited to rev-parse HEAD, pull --ff-only and diff --name-only: nothing is ever reset,
// stashed or forced.

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const serverControl = require("./server-control");

const REPO = path.resolve(__dirname, "..");
const RESULT_PATH = path.join(REPO, "logs", "console-update.json");
const isWindows = process.platform === "win32";

const GIT_SHORT_MS = 10000;
const PULL_MS = 60000;
const VENV_MS = 120000;
const INSTALL_MS = 300000;
const KILL_GRACE_MS = 2000;
const RESULT_MAX_AGE_MS = 600000;
const RESULT_LINES = 200;
const HANDOVER_NOTICE = "Console packages changed: the console closes, installs them in a separate window and opens again.";

let updateLines = [];       // everything this update logged, for the result file

function venvPython() {
  return isWindows
    ? path.join(REPO, ".venv", "Scripts", "python.exe")
    : path.join(REPO, ".venv", "bin", "python");
}

function short(hash) {
  return hash.slice(0, 7);
}

function log(lines) {
  updateLines = updateLines.concat(lines).slice(-RESULT_LINES);
  serverControl.appendLog(lines);
}

function describeFailure(program, r) {
  if (r.error) return `${program} failed (${r.error.message})`;
  if (r.timedOut) return `${program} failed (timed out after ${Math.round(r.timeoutMs / 1000)} s)`;
  if (r.signal) return `${program} failed (signal ${r.signal})`;
  return `${program} failed (exit ${r.code})`;
}

// ---- step runner (R24, R28, R29) ----

// Runs one command without a shell. Resolves (never rejects) to
// { ok, code, signal, timedOut, error, timeoutMs, stdout }.
function runStep(program, args, options) {
  const { cwd, env, timeoutMs } = options;
  const started = Date.now();
  log([`[update] $ ${[program, ...args].join(" ")}`]);
  return new Promise((resolve) => {
    const result = { ok: false, code: null, signal: null, timedOut: false, error: null, timeoutMs, stdout: "" };
    const partial = { out: "", err: "" };
    let settled = false;
    let killTimer = null;
    let exitTimer = null;
    let child = null;

    function settle() {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(killTimer);
      clearTimeout(exitTimer);
      const rest = [partial.out, partial.err].filter(Boolean);
      if (rest.length) log(rest);
      result.ok = !result.error && !result.timedOut && result.code === 0;
      const seconds = ((Date.now() - started) / 1000).toFixed(1);
      log([result.ok ? `[update] done in ${seconds} s` : `[update] ERROR: ${describeFailure(program, result)}`]);
      resolve(result);
    }

    function feed(key, chunk) {
      const parts = (partial[key] + chunk.toString("utf8")).split(/\r?\n/);
      partial[key] = parts.pop();
      if (parts.length) log(parts);
    }

    const timer = setTimeout(() => {
      result.timedOut = true;
      if (!child) return;
      if (isWindows) {
        child.kill();
      } else {
        child.kill("SIGTERM");
        killTimer = setTimeout(() => child.kill("SIGKILL"), KILL_GRACE_MS);
      }
      // A grandchild may keep the pipes open; do not wait for them forever.
      exitTimer = setTimeout(settle, KILL_GRACE_MS + 1000);
    }, timeoutMs);

    try {
      child = spawn(program, args, { cwd, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
    } catch (err) {
      result.error = err;
      settle();
      return;
    }
    child.stdout.on("data", (chunk) => {
      if (result.stdout.length < 100000) result.stdout += chunk.toString("utf8");
      feed("out", chunk);
    });
    child.stderr.on("data", (chunk) => feed("err", chunk));
    child.on("error", (err) => {
      result.error = err;
      settle();
    });
    child.on("exit", (code, signal) => {
      result.code = code;
      result.signal = signal;
      clearTimeout(exitTimer);
      exitTimer = setTimeout(settle, 1000);   // "close" normally comes first
    });
    child.on("close", (code, signal) => {
      if (result.code === null) result.code = code;
      if (!result.signal) result.signal = signal;
      settle();
    });
  });
}

function git(args, timeoutMs) {
  return runStep("git", args, { cwd: REPO, env: { ...process.env, GIT_TERMINAL_PROMPT: "0" }, timeoutMs });
}

function pythonEnv() {
  return { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" };
}

function firstHash(r) {
  const line = r.stdout.split(/\r?\n/)[0].trim();
  return r.ok && /^[0-9a-f]{40}$/i.test(line) ? line.toLowerCase() : null;
}

// ---- pieces of the update ----

async function createVenv() {
  const opts = { cwd: REPO, env: pythonEnv(), timeoutMs: VENV_MS };
  let r;
  if (isWindows) {
    r = await runStep("py", ["-3", "-m", "venv", ".venv"], opts);
    if (r.error && r.error.code === "ENOENT") r = await runStep("python", ["-m", "venv", ".venv"], opts);
  } else {
    r = await runStep("python3", ["-m", "venv", ".venv"], opts);
  }
  return r.ok && fs.existsSync(venvPython());
}

async function installPip() {
  const args = ["-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "-r", "requirements.txt"];
  return (await runStep(venvPython(), args, { cwd: REPO, env: pythonEnv(), timeoutMs: INSTALL_MS })).ok;
}

async function installNpm() {
  const r = await runStep("npm", ["install", "--no-save", "--no-audit", "--no-fund"], {
    cwd: path.join(REPO, "overlay"),
    env: process.env,
    timeoutMs: INSTALL_MS,
  });
  return r.ok;
}

// Paths changed by the pull -> what the console itself needs.
function classify(files) {
  const packages = files.includes("overlay/package.json") || files.includes("overlay/package-lock.json");
  const code = packages || files.some((f) => f.startsWith("overlay/") && f !== "overlay/overlay.json");
  return { packages, code };
}

// Exactly one notice per update (R26); the first failure in this order wins.
function buildNotice(f) {
  if (f.venvFailed) {
    return { result: "error", text: "Cannot create the Python environment. Is Python 3.10+ installed and on PATH? (see the log)" };
  }
  if (f.npmFailed) {
    return { result: "warning", text: `Updated ${f.from} → ${f.to}, but installing the console's packages failed (see the log). Run npm install in overlay/ and restart the console.` };
  }
  if (f.pipFailed) {
    const lead = f.upToDate ? `Already up to date (commit ${f.from})` : `Updated ${f.from} → ${f.to}`;
    return { result: "warning", text: `${lead}, but installing Python packages failed (see the log).${f.mustRun ? " The server was started anyway." : ""}` };
  }
  const base = f.upToDate ? `Already up to date (commit ${f.from}).` : `Updated ${f.from} → ${f.to}.`;
  const text = (f.venvCreated ? "Python environment created. " : "")
    + base
    + (f.relaunch ? " The console was relaunched with its new code." : "")
    + (f.pipOk ? " Python packages installed." : "");
  return { result: "ok", text };
}

function writeResultFile(from, to, notice) {
  fs.mkdirSync(path.dirname(RESULT_PATH), { recursive: true });
  const body = {
    version: 1,
    writtenAt: new Date().toISOString(),
    from,
    to,
    result: notice.result,
    notice: notice.text,
    lines: updateLines.slice(-RESULT_LINES),
  };
  fs.writeFileSync(RESULT_PATH, JSON.stringify(body, null, 2));
}

function discardResultFile() {
  try {
    fs.unlinkSync(RESULT_PATH);
  } catch (err) {
    if (err.code !== "ENOENT") console.warn(`Cannot delete ${RESULT_PATH}: ${err.message}`);
  }
}

// Reads the note of a previous console (R22) before the server is started.
function consumeResultFile() {
  let body = null;
  try {
    body = JSON.parse(fs.readFileSync(RESULT_PATH, "utf8"));
  } catch (err) {
    if (err.code !== "ENOENT") console.warn(`Ignoring ${RESULT_PATH}: ${err.message}`);
  }
  discardResultFile();
  if (!body || body.version !== 1) return;
  const age = Date.now() - Date.parse(body.writtenAt);
  const valid = Number.isFinite(age) && age <= RESULT_MAX_AGE_MS
    && typeof body.notice === "string" && ["ok", "warning", "error"].includes(body.result);
  if (!valid) return;
  const lines = Array.isArray(body.lines) ? body.lines.filter((l) => typeof l === "string") : [];
  serverControl.useUpdateLog(true);
  serverControl.appendLog(lines);
  serverControl.setUpdate({
    from: typeof body.from === "string" ? body.from : null,
    to: typeof body.to === "string" ? body.to : null,
    notice: body.notice,
    result: body.result,
  });
}

// ---- the update ----

// Runs the whole sequence under server-control's lock (R2). The caller (main.js) performs a
// relaunch or handover when the result says so; update.running then stays true until the app exits.
function runUpdate() {
  let outcome = { action: "none", mustRun: false, canStart: true };
  return serverControl.runExclusive(async () => {
    try {
      outcome = await sequence();
    } catch (err) {
      outcome = { action: "none", mustRun: false, canStart: true };
      log([`[update] ERROR: ${err.message}`]);
      serverControl.finishUpdateLog();
      serverControl.setUpdate({
        running: false, step: null, closeRefused: null, result: "error",
        notice: `Update failed: ${err.message} (see the log).`,
      });
    }
  }).then(() => outcome);
}

// Ends the update on the path that keeps this console: server back as it was (R16), then the notice.
async function end(notice, mustRun, canStart) {
  if (mustRun && canStart) {
    serverControl.setUpdate({ step: "starting" });
    await serverControl.startUnlocked();
  }
  serverControl.finishUpdateLog();
  serverControl.setUpdate({ running: false, step: null, closeRefused: null, notice: notice.text, result: notice.result });
  return { action: "none", mustRun, canStart };
}

async function sequence() {
  const snap = serverControl.getSnapshot();
  const none = { action: "none", mustRun: false, canStart: true };
  if (snap.probing || !["running", "attached", "stopped", "crashed", "unavailable"].includes(snap.state)) return none;
  const mustRun = ["running", "attached", "unavailable"].includes(snap.state);   // R5
  const f = { mustRun };
  updateLines = [];
  serverControl.useUpdateLog(true);
  serverControl.setUpdate({ running: true, step: "checking", from: null, to: null, notice: "", result: null });

  // checking (R4): nothing is touched when this fails
  const head = await git(["rev-parse", "HEAD"], GIT_SHORT_MS);
  const oldHash = firstHash(head);
  if (!oldHash) {
    const missing = head.error && head.error.code === "ENOENT";
    return end({
      result: "error",
      text: missing
        ? "Update failed: git is not installed or not on PATH. Nothing was changed."
        : "Update failed: cannot read the current commit (see the log). Nothing was changed.",
    }, false, true);
  }
  f.from = short(oldHash);
  serverControl.setUpdate({ from: f.from });

  // stopping (R6, R7)
  if (["running", "attached"].includes(snap.state)) {
    serverControl.setUpdate({ step: "stopping" });
    await serverControl.stopUnlocked();
    if (serverControl.getSnapshot().state === "attached") {
      return end({
        result: "error",
        text: "Update cancelled: the server did not stop. Close its window (run.bat), then press Update again.",
      }, false, true);
    }
  }

  // pulling (R8, R9, R11)
  serverControl.setUpdate({ step: "pulling" });
  const pull = await git(["pull", "--ff-only"], PULL_MS);
  const newHash = pull.ok ? firstHash(await git(["rev-parse", "HEAD"], GIT_SHORT_MS)) : null;
  if (!newHash) {
    return end({
      result: "error",
      text: pull.timedOut
        ? "Update failed: git pull did not finish in 60 s and was stopped (see the log)."
        : "Update failed: git pull did not succeed (see the log). Nothing was changed.",
    }, mustRun, true);
  }
  f.upToDate = newHash === oldHash;
  f.to = short(newHash);
  let files = [];
  if (!f.upToDate) {
    serverControl.setUpdate({ to: f.to });
    const diff = await git(["diff", "--name-only", oldHash, newHash], GIT_SHORT_MS);
    files = diff.ok
      ? diff.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
      : ["requirements.txt", "overlay/package-lock.json"];   // R11: assume the worst
  }

  // venv (R12, R14) and pip (R13, R15)
  let canStart = true;
  if (!fs.existsSync(venvPython())) {
    serverControl.setUpdate({ step: "venv" });
    if (await createVenv()) {
      f.venvCreated = true;
    } else {
      f.venvFailed = true;
      canStart = false;
      serverControl.markUnavailable();
    }
  }
  if (!f.venvFailed && (f.venvCreated || files.includes("requirements.txt"))) {
    serverControl.setUpdate({ step: "pip" });
    if (await installPip()) f.pipOk = true;
    else f.pipFailed = true;
  }

  // the console itself (R17, R18, R19)
  const need = classify(files);
  if (need.packages && !isWindows) {
    serverControl.setUpdate({ step: "npm" });
    if (!(await installNpm())) {
      f.npmFailed = true;
      return end(buildNotice(f), mustRun, canStart);
    }
  }
  if (need.code) {
    f.relaunch = true;
    const handover = need.packages && isWindows;
    const notice = buildNotice(f);
    try {
      writeResultFile(f.from, f.to, notice);
    } catch (err) {
      log([`[update] ERROR: cannot write ${RESULT_PATH} (${err.message})`]);
    }
    serverControl.setUpdate({
      step: handover ? "handover" : "relaunching",
      notice: handover ? HANDOVER_NOTICE : notice.text,
      result: handover ? "ok" : notice.result,
    });
    return { action: handover ? "handover" : "relaunch", mustRun, canStart };
  }
  return end(buildNotice(f), mustRun, canStart);
}

// Used by main.js when the handover could not start: the server goes back as it was (R16).
function restoreAfterFailedHandover(outcome, text) {
  discardResultFile();
  const restart = outcome.mustRun && outcome.canStart;
  if (!restart) serverControl.finishUpdateLog();
  serverControl.setUpdate({ running: false, step: null, closeRefused: null, notice: text, result: "error" });
  if (restart) return serverControl.startServer();
  return Promise.resolve();
}

module.exports = { runUpdate, consumeResultFile, restoreAfterFailedHandover };
