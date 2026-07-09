const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const BACKEND_PORT = 8237;
let backendProcess = null;

function isDev() {
  return !app.isPackaged;
}

function outputDir() {
  return process.env.AUTOCLIP_OUTPUT_DIR || path.join(os.homedir(), "Movies", "AutoClip");
}

function sidecarPath() {
  const name = process.platform === "win32" ? "autoclip-backend.exe" : "autoclip-backend";
  return path.join(process.resourcesPath, "backend", name);
}

function backendBinDir() {
  return path.join(process.resourcesPath, "backend", "bin");
}

function spawnBackend() {
  if (process.env.AUTOCLIP_SKIP_BACKEND) {
    return;
  }

  if (isDev()) {
    // Dev mode: jalankan uvicorn dari venv backend repo.
    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    const python = path.join(backendDir, ".venv", "bin", "python");
    backendProcess = spawn(python, ["-m", "uvicorn", "app:app", "--port", String(BACKEND_PORT)], {
      cwd: backendDir,
      stdio: "inherit",
    });
  } else {
    // Production: pakai PyInstaller sidecar yang dibundle Electron Builder.
    const env = { ...process.env };
    const binDir = backendBinDir();
    if (fs.existsSync(binDir)) {
      env.PATH = binDir + path.delimiter + env.PATH;
    }
    backendProcess = spawn(sidecarPath(), [], {
      env,
      stdio: "inherit",
    });
  }

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
  spawnBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (backendProcess && !backendProcess.killed) backendProcess.kill();
  app.quit();
});
