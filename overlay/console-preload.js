// The console window's only bridge: process control, overlay control and snapshots from the main process.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("consoleApi", {
  getSnapshot: () => ipcRenderer.invoke("console:get-snapshot"),
  start: () => ipcRenderer.invoke("console:start"),
  stop: () => ipcRenderer.invoke("console:stop"),
  restart: () => ipcRenderer.invoke("console:restart"),
  update: () => ipcRenderer.invoke("console:update"),
  toggleOverlay: () => ipcRenderer.send("console:toggle-overlay"),
  toggleOverlayEdit: () => ipcRenderer.send("console:toggle-overlay-edit"),
  setAddress: (address) => ipcRenderer.send("console:set-address", String(address)),
  onSnapshot: (callback) => ipcRenderer.on("console:snapshot", (_e, snapshot) => callback(snapshot)),
  onLog: (callback) => ipcRenderer.on("console:log", (_e, log) => callback(log)),
});
