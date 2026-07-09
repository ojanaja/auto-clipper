const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const os = require("os");

const BACKEND_PORT = 8237;
let backendProcess = null;

function outputDir() {
  return process.env.AUTOCLIP_OUTPUT_DIR || path.join(os.homedir(), "Movies", "AutoClip");
}

function spawnBackend() {
  // Dev mode: jalankan uvicorn dari venv backend repo.
  // ponytail: fase 9 (packaging) ganti path ini ke sidecar PyInstaller.
  const backendDir = path.join(__dirname, "..", "..", "..", "backend");
  const python = path.join(backendDir, ".venv", "bin", "python");
  backendProcess = spawn(python, ["-m", "uvicorn", "app:app", "--port", String(BACKEND_PORT)], {
    cwd: backendDir,
    stdio: "inherit",
  });
  backendProcess.on("error", (err) => {
    console.error("Gagal spawn backend:", err.message);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 820,
    height: 720,
    backgroundColor: "#0F172A",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
}

app.whenReady().then(() => {
  ipcMain.handle("open-output-folder", () => shell.openPath(outputDir()));
  if (!process.env.AUTOCLIP_SKIP_BACKEND) {
    spawnBackend();
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (backendProcess && !backendProcess.killed) backendProcess.kill();
  app.quit();
});
