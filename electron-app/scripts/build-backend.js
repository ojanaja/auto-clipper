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

process.exit(result.status ?? 0);
