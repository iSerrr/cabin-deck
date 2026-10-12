// Gives the dash page the overlay app's edit-mode calls: move the window while dragging, resize from the wheel.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("overlayApi", {
  resize: (step) => ipcRenderer.send("resize", step),
  move: (dx, dy) => ipcRenderer.send("move", dx, dy),
});
