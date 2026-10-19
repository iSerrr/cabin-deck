// Cab Deck Console: a control window (starts/stops the server, QR codes, health, log tail) plus the
// overlay window described below.
//
// Cab Deck overlay: the Alpha Gen v2 dash in an always-on-top, click-through window over the game.
// By default it is the dark dash cut to its own silhouette (the window around it is transparent);
// put "?overlay=1" on the url in overlay.json for a see-through HUD instead. The game must run windowed or borderless;
// exclusive fullscreen hides other windows.
//
// Ctrl+Shift+F9   show / hide
// Ctrl+Shift+F10  edit mode on: drag to move, mouse wheel or +/- to resize, arrows to nudge
//                 (Shift = 10 px); press again to save and lock

const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const serverControl = require("./server-control");
const updater = require("./updater");

const CONFIG_PATH = path.join(__dirname, "overlay.json");
const ASPECT = 2.17;          // same as the dash page
const MIN_WIDTH = 320;
const RESIZE_STEP = 1.05;     // per wheel notch
const RETRY_MS = 2000;        // reload while the server is not up yet
const NUDGE = 1, NUDGE_FAST = 10;   // arrow keys in edit mode, px
const QUIT_CAP_MS = 11000;    // longest wait for a managed server to stop on quit
const DRY_RUN = process.argv.includes("--dry-run");
const REPO = path.resolve(__dirname, "..");
const WAIT_FOR_UPDATE = "Wait for the update to finish; every step stops by itself within its time limit.";
const QR_MISSING = "QR codes need `npm install`: run console.bat again.";

const DEFAULTS = {
  url: "http://127.0.0.1:8702/?shape=1",   // dark dash cut to its silhouette; "?overlay=1" = see-through HUD
  width: 760,
  x: null,                    // null: centred near the bottom of the main screen
  y: null,
  opacity: 1,
  toggleKey: "Control+Shift+F9",
  editKey: "Control+Shift+F10",
};

let win = null;               // overlay window
let consoleWin = null;
let config = null;
let editing = false;
let chosenAddress = null;
let qrLib = null;
let qrError = "";
let quitting = false;
const qrCache = new Map();    // url -> PNG data URL

function loadConfig() {
  try {
    return { ...DEFAULTS, ...JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8")) };
  } catch (err) {
    if (err.code !== "ENOENT") console.warn(`overlay.json is not valid, using defaults: ${err.message}`);
    return { ...DEFAULTS };
  }
}

// Saves only the window's place and size; anything else stays as the user wrote it, so new
// defaults (such as the url) still reach them.
function savePlacement(placement) {
  let saved = {};
  try {
    saved = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  } catch (err) {
    if (err.code !== "ENOENT") console.warn(`overlay.json is not valid, rewriting it: ${err.message}`);
  }
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify({ ...saved, ...placement }, null, 2));
  } catch (err) {
    console.error(`Cannot save overlay.json: ${err.message}`);
  }
}

function initialBounds() {
  const area = screen.getPrimaryDisplay().workArea;
  const width = Math.max(MIN_WIDTH, Math.round(config.width));
  const height = Math.round(width / ASPECT);
  return {
    width,
    height,
    x: config.x ?? Math.round(area.x + (area.width - width) / 2),
    y: config.y ?? Math.round(area.y + area.height - height - 40),
  };
}

function createOverlayWindow() {
  win = new BrowserWindow({
    ...initialBounds(),
    transparent: true,
    backgroundColor: "#00000000",
    frame: false,
    resizable: false,
    hasShadow: false,
    skipTaskbar: true,
    focusable: false,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      backgroundThrottling: false,   // keep 60 fps while the game has focus
    },
  });
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true);
  win.setOpacity(config.opacity);
  win.webContents.on("before-input-event", onEditKey);
  win.webContents.on("did-fail-load", (_e, code, description) => {
    console.warn(`Cannot load ${config.url} (${description}), is the Cab Deck server running? Retrying.`);
    setTimeout(() => win && win.loadURL(config.url), RETRY_MS);
  });
  win.loadURL(config.url);
}

function setEditing(on) {
  editing = on;
  win.setIgnoreMouseEvents(!on);
  win.setFocusable(on);
  if (on) win.focus();
  win.webContents.executeJavaScript(`document.body.classList.toggle("edit", ${on})`).catch(() => {});
  if (!on) {
    const { x, y, width } = win.getBounds();
    Object.assign(config, { x, y, width });
    savePlacement({ x, y, width });
    console.log(`Overlay saved at ${x},${y}, ${width} px wide.`);
  }
  notifyConsole();
}

// One code path for the hotkeys and the console buttons.
function toggleOverlayVisible() {
  if (!win) return;
  if (win.isVisible()) win.hide();
  else win.showInactive();
  notifyConsole();
}

function toggleOverlayEdit() {
  if (win) setEditing(!editing);
}

// Grow (step > 0) or shrink around the centre, keeping the dash's aspect ratio.
function resizeBy(step) {
  const b = win.getBounds();
  const width = Math.max(MIN_WIDTH, Math.round(b.width * (step > 0 ? RESIZE_STEP : 1 / RESIZE_STEP)));
  const height = Math.round(width / ASPECT);
  win.setBounds({ x: Math.round(b.x + (b.width - width) / 2), y: Math.round(b.y + (b.height - height) / 2), width, height });
}

function moveBy(dx, dy) {
  const [x, y] = win.getPosition();
  win.setPosition(Math.round(x + dx), Math.round(y + dy));
}

ipcMain.on("resize", (e, step) => { if (editing && win && e.sender === win.webContents) resizeBy(step); });
ipcMain.on("move", (e, dx, dy) => { if (editing && win && e.sender === win.webContents) moveBy(dx, dy); });

// Keyboard in edit mode (the window has focus then): +/- resize, arrows nudge.
function onEditKey(event, input) {
  if (!editing || input.type !== "keyDown") return;
  const step = input.shift ? NUDGE_FAST : NUDGE;
  const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
  if (moves[input.key]) moveBy(...moves[input.key]);
  else if (input.key === "+" || input.key === "=") resizeBy(1);
  else if (input.key === "-" || input.key === "_") resizeBy(-1);
  else return;
  event.preventDefault();
}

function registerKeys() {
  const keys = [
    [config.toggleKey, toggleOverlayVisible],
    [config.editKey, toggleOverlayEdit],
  ];
  for (const [key, action] of keys) {
    if (!globalShortcut.register(key, action)) console.warn(`Hotkey ${key} is taken by another program; change it in overlay.json.`);
  }
}

// ---- console window ----

function createConsoleWindow() {
  consoleWin = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    center: true,
    title: "Cab Deck Console",
    backgroundColor: "#08090B",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "console-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  consoleWin.setMenu(null);
  consoleWin.webContents.on("will-navigate", (e) => e.preventDefault());
  consoleWin.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  consoleWin.webContents.on("did-finish-load", () => {
    notifyConsole();
    sendLog();
  });
  consoleWin.on("close", (e) => {
    if (!updateRunning()) return;
    e.preventDefault();
    serverControl.setUpdate({ closeRefused: WAIT_FOR_UPDATE });   // R30
  });
  consoleWin.on("closed", () => {
    consoleWin = null;
    app.quit();
  });
  consoleWin.loadFile(path.join(__dirname, "console.html"));
}

function showConsole() {
  if (!consoleWin) return;
  if (consoleWin.isMinimized()) consoleWin.restore();
  consoleWin.show();
  consoleWin.focus();
}

function fromConsole(event) {
  return Boolean(consoleWin) && event.sender === consoleWin.webContents;
}

function loadQr() {
  if (qrLib || qrError) return qrLib;
  try {
    qrLib = require("qrcode");
  } catch (err) {
    console.warn(`Cannot load qrcode: ${err.message}`);
    qrError = QR_MISSING;
  }
  return qrLib;
}

async function qrDataUrl(url) {
  if (!qrCache.has(url)) {
    qrCache.set(url, await qrLib.toDataURL(url, { margin: 2, width: 440, errorCorrectionLevel: "M" }));
  }
  return qrCache.get(url);
}

// QR codes for the panel and dash v2 of the chosen address, or null (the page explains why).
async function buildQr(snapshot) {
  const h = snapshot.health;
  if ((snapshot.state !== "running" && snapshot.state !== "attached") || !h) return null;
  const addresses = Array.isArray(h.addresses) ? h.addresses : [];
  if (!addresses.length || !h.ports) return null;
  if (!loadQr()) return null;
  const address = addresses.includes(chosenAddress) ? chosenAddress : addresses[0];
  const panelUrl = `http://${address}:${h.ports.panel}`;
  const dash2Url = `http://${address}:${h.ports.dash2}`;
  try {
    return {
      address,
      addresses,
      panel: { url: panelUrl, dataUrl: await qrDataUrl(panelUrl) },
      dash2: { url: dash2Url, dataUrl: await qrDataUrl(dash2Url) },
    };
  } catch (err) {
    console.warn(`Cannot make QR codes: ${err.message}`);
    qrError = QR_MISSING;
    return null;
  }
}

async function fullSnapshot() {
  const snapshot = serverControl.getSnapshot();
  snapshot.overlay = { visible: Boolean(win) && win.isVisible(), editing };
  snapshot.qr = await buildQr(snapshot);
  snapshot.qrError = qrError;
  return snapshot;
}

let notifySeq = 0;
async function notifyConsole() {
  if (!consoleWin || consoleWin.webContents.isLoading()) return;
  const seq = ++notifySeq;
  const snapshot = await fullSnapshot();
  if (seq !== notifySeq || !consoleWin) return;   // a newer snapshot is on its way
  consoleWin.webContents.send("console:snapshot", snapshot);
}

function sendLog() {
  if (consoleWin && !consoleWin.webContents.isLoading()) consoleWin.webContents.send("console:log", serverControl.getLog());
}

function updateRunning() {
  return serverControl.getSnapshot().update.running;
}

// R17, R19: the server is already stopped; start the same app again after this process exits.
function relaunchConsole() {
  app.releaseSingleInstanceLock();
  app.relaunch({ execPath: process.execPath, args: [app.getAppPath(), ...(DRY_RUN ? ["--dry-run"] : [])] });
  app.exit(0);
}

// R18 (Windows): console.bat installs the console's packages while no Electron file is in use.
async function handoverToBat(outcome) {
  await new Promise((resolve) => setTimeout(resolve, 600));   // let the console show the notice
  app.releaseSingleInstanceLock();
  const line = `""${path.join(REPO, "console.bat")}" update ${process.pid}${DRY_RUN ? " dry" : ""}"`;
  let failure = null;
  try {
    const child = spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", line], {
      cwd: REPO,
      detached: true,
      stdio: "ignore",
      windowsHide: false,
      windowsVerbatimArguments: true,
    });
    failure = await new Promise((resolve) => {
      child.once("spawn", () => resolve(null));
      child.once("error", resolve);
    });
    if (!failure) child.unref();
  } catch (err) {
    failure = err;
  }
  if (!failure) {
    app.exit(0);
    return;
  }
  app.requestSingleInstanceLock();
  await updater.restoreAfterFailedHandover(
    outcome,
    `Cannot start console.bat for the update: ${failure.message}. Close the console and run console.bat.`,
  );
}

async function runUpdateFromConsole() {
  if (updateRunning()) return;
  const outcome = await updater.runUpdate();
  if (outcome.action === "relaunch") relaunchConsole();
  else if (outcome.action === "handover") await handoverToBat(outcome);
}

function registerConsoleIpc() {
  ipcMain.handle("console:get-snapshot", (e) => (fromConsole(e) ? fullSnapshot() : null));
  ipcMain.handle("console:start", (e) => { if (fromConsole(e) && !updateRunning()) return serverControl.startServer(); });
  ipcMain.handle("console:stop", (e) => { if (fromConsole(e) && !updateRunning()) return serverControl.stopServer(); });
  ipcMain.handle("console:restart", (e) => { if (fromConsole(e) && !updateRunning()) return serverControl.restartServer(); });
  ipcMain.handle("console:update", (e) => { if (fromConsole(e)) return runUpdateFromConsole(); });
  ipcMain.on("console:toggle-overlay", (e) => { if (fromConsole(e)) toggleOverlayVisible(); });
  ipcMain.on("console:toggle-overlay-edit", (e) => { if (fromConsole(e)) toggleOverlayEdit(); });
  ipcMain.on("console:set-address", (e, address) => {
    if (!fromConsole(e) || typeof address !== "string") return;
    chosenAddress = address;
    notifyConsole();
  });
  serverControl.events.on("change", () => notifyConsole());
  serverControl.events.on("log", () => sendLog());
}

// ---- lifecycle ----

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", showConsole);

  app.whenReady().then(() => {
    config = loadConfig();
    registerConsoleIpc();
    createConsoleWindow();
    createOverlayWindow();
    registerKeys();
    console.log(`Overlay showing ${config.url}. ${config.toggleKey}: show/hide, ${config.editKey}: move/resize.`);
    updater.consumeResultFile();   // the note of a previous console, before the server starts (R22)
    serverControl.init({ dryRun: DRY_RUN });
  });

  // A managed server is stopped (R11, R12) before the app exits; an attached one is left running.
  app.on("before-quit", (event) => {
    if (updateRunning()) {   // R30
      event.preventDefault();
      serverControl.setUpdate({ closeRefused: WAIT_FOR_UPDATE });
      return;
    }
    if (quitting || !serverControl.isManaged()) return;
    event.preventDefault();
    quitting = true;
    const cap = new Promise((resolve) => setTimeout(resolve, QUIT_CAP_MS));
    Promise.race([serverControl.stopManagedForQuit(), cap])
      .catch((err) => console.error(`Stopping the server on quit failed: ${err.message}`))
      .finally(() => {
        serverControl.killNow();
        app.exit(0);
      });
  });

  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => app.quit());
}
