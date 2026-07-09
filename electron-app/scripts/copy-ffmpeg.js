#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const ffmpeg = require("ffmpeg-static");
const ffprobe = require("ffprobe-static").path;

const isWin = process.platform === "win32";
const outDir = path.join(__dirname, "..", "build", "backend", "bin");

function copy(src, name) {
  if (!src || !fs.existsSync(src)) {
    console.error(`Binary not found: ${name} (${src})`);
    process.exit(1);
  }
  fs.mkdirSync(outDir, { recursive: true });
  const dest = path.join(outDir, `${name}${isWin ? ".exe" : ""}`);
  fs.copyFileSync(src, dest);
  fs.chmodSync(dest, 0o755);
  console.log(`Copied ${name} -> ${dest}`);
}

copy(ffmpeg, "ffmpeg");
copy(ffprobe, "ffprobe");
