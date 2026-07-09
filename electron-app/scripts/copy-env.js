#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..", "..");
const src = path.join(projectRoot, ".env");
const outDir = path.join(__dirname, "..", "build");
const dest = path.join(outDir, ".env");

fs.mkdirSync(outDir, { recursive: true });

if (fs.existsSync(src)) {
  fs.copyFileSync(src, dest);
  console.log(`Copied ${src} -> ${dest}`);
} else {
  fs.writeFileSync(dest, "# no .env provided at build time\n");
  console.log(`No project .env found; wrote empty placeholder at ${dest}`);
}
