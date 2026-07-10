#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const backendDir = path.resolve(__dirname, "..", "..", "backend");

const candidates = [
  path.join(backendDir, ".venv", "Scripts", "python.exe"),
  path.join(backendDir, ".venv", "bin", "python"),
  process.platform === "win32" ? "python.exe" : "python3",
  "python",
];

const python = candidates.find((p) => fs.existsSync(p)) || candidates[candidates.length - 1];

console.log(`Building backend sidecar with ${python}`);
const electronBuildDir = path.resolve(__dirname, "..", "build", "backend");
const env = { ...process.env, AUTOCLIP_BACKEND_ROOT: backendDir };
const args = [
  "-m",
  "PyInstaller",
  "autoclip-backend.spec",
  "--distpath",
  electronBuildDir,
  "--workpath",
  path.join(backendDir, "build", "pyinstaller"),
];
const result = spawnSync(python, args, {
  cwd: backendDir,
  stdio: "inherit",
  shell: process.platform === "win32",
  env,
});

if (result.status !== 0 && result.status != null) {
  process.exit(result.status);
}

// Copy YuNet model next to the sidecar so it is shipped as an extra resource
// (PyInstaller datas are hidden inside the one-file archive and not visible
// to build manifest verification).
const modelName = "face_detection_yunet_2023mar.onnx";
const sourceModel = path.join(backendDir, "models", modelName);
const modelDir = path.join(electronBuildDir, "models");
const destModel = path.join(modelDir, modelName);

if (fs.existsSync(sourceModel)) {
  fs.mkdirSync(modelDir, { recursive: true });
  fs.copyFileSync(sourceModel, destModel);
  console.log(`Copied YuNet model to ${destModel}`);
} else {
  console.warn(`WARNING: YuNet model not found at ${sourceModel}; run npm run build:model first`);
}

process.exit(0);
