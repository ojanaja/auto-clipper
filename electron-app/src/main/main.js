const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
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
    // GUI Electron di Windows tak punya console; "inherit" membuang log backend.
    // Alihkan stdout/stderr ke file supaya crash startup sidecar bisa dibaca user.
    const logPath = path.join(app.getPath("userData"), "backend.log");
    try {
      const logFd = fs.openSync(logPath, "a");
      backendProcess = spawn(sidecarPath(), [], { env, stdio: ["ignore", logFd, logFd] });
    } catch {
      backendProcess = spawn(sidecarPath(), [], { env, stdio: "inherit" });
    }
    console.log("Backend log:", logPath);
  }

  backendProcess.on("error", (err) => {
    console.error("Gagal spawn backend:", err.message);
  });
  backendProcess.on("exit", (code) => {
    if (code) console.error(`Backend keluar dengan kode ${code}`);
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
  ipcMain.handle("select-output-dir", async () => {
    const win = BrowserWindow.getFocusedWindow();
    const result = await dialog.showOpenDialog(win, {
      properties: ["openDirectory", "createDirectory"],
      defaultPath: outputDir(),
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle("import-customization-preset", async () => {
    const win = BrowserWindow.getFocusedWindow();
    const result = await dialog.showOpenDialog(win, {
      properties: ["openFile"],
      filters: [{ name: "Preset Kustomisasi (JSON)", extensions: ["json"] }],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    try {
      return JSON.parse(fs.readFileSync(result.filePaths[0], "utf-8"));
    } catch {
      throw new Error("File preset tidak valid (bukan JSON yang benar)");
    }
  });
  ipcMain.handle("select-overlay-image", async () => {
    const win = BrowserWindow.getFocusedWindow();
    const result = await dialog.showOpenDialog(win, {
      properties: ["openFile"],
      filters: [{ name: "Gambar", extensions: ["png", "jpg", "jpeg", "webp"] }],
    });
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
  });
  ipcMain.handle("export-customization-preset", async (_event, data) => {
    const win = BrowserWindow.getFocusedWindow();
    const result = await dialog.showSaveDialog(win, {
      defaultPath: "autoclip-preset.json",
      filters: [{ name: "Preset Kustomisasi (JSON)", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePath) return false;
    fs.writeFileSync(result.filePath, JSON.stringify(data, null, 2), "utf-8");
    return true;
  });
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
