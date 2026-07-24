const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("autoclip", {
  openOutputFolder: () => ipcRenderer.invoke("open-output-folder"),
  selectOutputDir: () => ipcRenderer.invoke("select-output-dir"),
  importCustomizationPreset: () => ipcRenderer.invoke("import-customization-preset"),
  exportCustomizationPreset: (data) => ipcRenderer.invoke("export-customization-preset", data),
  selectOverlayImage: () => ipcRenderer.invoke("select-overlay-image"),
});
