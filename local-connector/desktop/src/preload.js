const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("connectorDesktop", {
  getInitialState: () => ipcRenderer.invoke("desktop:get-initial-state"),
  startLauncher: () => ipcRenderer.invoke("desktop:start-launcher"),
  stopLauncher: () => ipcRenderer.invoke("desktop:stop-launcher"),
  openStatusPage: () => ipcRenderer.invoke("desktop:open-status-page"),
  openLogDir: () => ipcRenderer.invoke("desktop:open-log-dir"),
  openDataDir: () => ipcRenderer.invoke("desktop:open-data-dir"),
  openRootDir: () => ipcRenderer.invoke("desktop:open-root-dir"),
  pickWorkspace: () => ipcRenderer.invoke("desktop:pick-workspace"),
  onStatusUpdate: (handler) => ipcRenderer.on("status-update", (_event, payload) => handler(payload)),
  onRuntimeLog: (handler) => ipcRenderer.on("runtime-log", (_event, payload) => handler(payload)),
  onRuntimeLogBatch: (handler) => ipcRenderer.on("runtime-log-batch", (_event, payload) => handler(payload)),
  onLauncherState: (handler) => ipcRenderer.on("launcher-state", (_event, payload) => handler(payload))
});
