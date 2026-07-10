const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("autoclip", {
  openOutputFolder: () => ipcRenderer.invoke("open-output-folder"),
  selectOutputDir: () => ipcRenderer.invoke("select-output-dir"),
});
