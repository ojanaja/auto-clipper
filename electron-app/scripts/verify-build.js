#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const distDir = process.env.DIST_DIR || path.join(root, "dist");

const isWin = process.platform === "win32";
const isMac = process.platform === "darwin";

function exists(p) {
  return fs.existsSync(p);
}

function findOne(baseDir, pattern) {
  if (!exists(baseDir)) return null;
  const entries = fs.readdirSync(baseDir);
  const match = entries.find((e) => pattern.test(e));
  return match ? path.join(baseDir, match) : null;
}

function fail(message) {
  console.error(`❌ ${message}`);
  process.exitCode = 1;
}

function ok(message) {
  console.log(`✅ ${message}`);
}

function main() {
  console.log(`Verifying build in ${distDir}\n`);

  let resourcesDir;
  let appExecutable;
  let installer;

  if (isMac) {
    const appBundle =
      [path.join(distDir, "mac-arm64", "AutoClip Lokal.app"), path.join(distDir, "mac", "AutoClip Lokal.app")].find(
        exists
      ) || null;
    if (appBundle) {
      resourcesDir = path.join(appBundle, "Contents", "Resources");
      appExecutable = path.join(appBundle, "Contents", "MacOS", "AutoClip Lokal");
    }
    installer = findOne(distDir, /^AutoClip Lokal-.*\.dmg$/);
  } else if (isWin) {
    const unpacked = path.join(distDir, "win-unpacked");
    if (exists(unpacked)) {
      resourcesDir = path.join(unpacked, "resources");
      appExecutable = path.join(unpacked, "AutoClip Lokal.exe");
    }
    installer = findOne(distDir, /^AutoClip Lokal Setup .*\.exe$/);
  } else {
    // Linux fallback: check unpacked dir only.
    const unpacked = path.join(distDir, "linux-unpacked");
    if (exists(unpacked)) {
      resourcesDir = path.join(unpacked, "resources");
      appExecutable = path.join(unpacked, "autoclip-lokal");
    }
  }

  // Either unpacked app or installer must exist.
  if (!resourcesDir && !installer) {
    fail("No packaged app or installer found in dist/");
    return;
  }

  if (installer) ok(`Installer: ${path.basename(installer)}`);
  if (appExecutable && exists(appExecutable)) ok(`App executable: ${path.basename(appExecutable)}`);

  if (resourcesDir) {
    ok(`Resources directory exists`);

    const sidecarName = isWin ? "autoclip-backend.exe" : "autoclip-backend";
    const sidecar = path.join(resourcesDir, "backend", sidecarName);
    if (exists(sidecar)) ok(`Backend sidecar: ${sidecarName}`);
    else fail(`Missing backend sidecar: ${sidecar}`);

    const ffmpeg = path.join(resourcesDir, "backend", "bin", isWin ? "ffmpeg.exe" : "ffmpeg");
    const ffprobe = path.join(resourcesDir, "backend", "bin", isWin ? "ffprobe.exe" : "ffprobe");
    if (exists(ffmpeg)) ok("ffmpeg bundled");
    else fail(`Missing ffmpeg: ${ffmpeg}`);
    if (exists(ffprobe)) ok("ffprobe bundled");
    else fail(`Missing ffprobe: ${ffprobe}`);

    const yunetModel = path.join(resourcesDir, "backend", "models", "face_detection_yunet_2023mar.onnx");
    if (exists(yunetModel)) ok("YuNet face-detection model bundled");
    else fail(`Missing YuNet model: ${yunetModel}`);

    // Renderer files are inside app.asar; verify the asar archive or unpacked package.
    const asarArchive = path.join(resourcesDir, "app.asar");
    const asarPackage = path.join(resourcesDir, "app", "package.json");
    if (exists(asarArchive) || exists(asarPackage)) ok("Renderer app package present");
    else fail(`Missing renderer app package: ${asarPackage} (or ${asarArchive})`);
  } else {
    console.log("ℹ️  Unpacked app not present; installer-only verification.");
  }

  if (process.exitCode) {
    console.error("\nBuild manifest verification failed.");
  } else {
    console.log("\nBuild manifest verification passed.");
  }
}

main();
