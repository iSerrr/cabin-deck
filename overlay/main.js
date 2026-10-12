// Cab Deck overlay: the Alpha Gen v2 dash in an always-on-top, click-through window over the game.
// By default it is the dark dash cut to its own silhouette (the window around it is transparent);
// put "?overlay=1" on the url in overlay.json for a see-through HUD instead. The game must run windowed or borderless;
// exclusive fullscreen hides other windows.
//
// Ctrl+Shift+F9   show / hide
// Ctrl+Shift+F10  edit mode on: drag to move, mouse wheel or +/- to resize, arrows to nudge
//                 (Shift = 10 px); press again to save and lock

const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require("electron");
const fs = require("fs");
const path = require("path");

const CONFIG_PATH = path.join(__dirname, "overlay.json");
const ASPECT = 2.17;          // same as the dash page
const MIN_WIDTH = 320;
const RESIZE_STEP = 1.05;     // per wheel notch
const RETRY_MS = 2000;        // reload while the server is not up yet
const NUDGE = 1, NUDGE_FAST = 10;   // arrow keys in edit mode, px

const DEFAULTS = {
  url: "http://127.0.0.1:8702/?shape=1",   // dark dash cut to its silhouette; "?overlay=1" = see-through HUD
  width: 760,
  x: null,                    // null: centred near the bottom of the main screen
  y: null,
  opacity: 1,
  toggleKey: "Control+Shift+F9",
  editKey: "Control+Shift+F10",
};

let win = null;
let config = null;
let editing = false;

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

function createWindow() {
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

ipcMain.on("resize", (_e, step) => { if (editing) resizeBy(step); });
ipcMain.on("move", (_e, dx, dy) => { if (editing) moveBy(dx, dy); });

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
    [config.toggleKey, () => (win.isVisible() ? win.hide() : win.showInactive())],
    [config.editKey, () => setEditing(!editing)],
  ];
  for (const [key, action] of keys) {
    if (!globalShortcut.register(key, action)) console.warn(`Hotkey ${key} is taken by another program; change it in overlay.json.`);
  }
}

app.whenReady().then(() => {
  config = loadConfig();
  createWindow();
  registerKeys();
  console.log(`Overlay showing ${config.url}. ${config.toggleKey}: show/hide, ${config.editKey}: move/resize.`);
});

app.on("will-quit", () => globalShortcut.unregisterAll());
app.on("window-all-closed", () => app.quit());
