// Gives the dash page one call into the overlay app: resize the window from the mouse wheel in edit mode.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("overlayApi", {
  resize: (step) => ipcRenderer.send("resize", step),
});
