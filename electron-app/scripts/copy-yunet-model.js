#!/usr/bin/env node
"use strict";

const fs = require("fs");
const https = require("https");
const path = require("path");

const MODEL_URL =
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx";
const backendDir = path.resolve(__dirname, "..", "..", "backend");
const modelsDir = path.join(backendDir, "models");
const dest = path.join(modelsDir, "face_detection_yunet_2023mar.onnx");

function download(url, filePath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(filePath);
    https
      .get(url, { redirect: "follow" }, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          return download(response.headers.location, filePath).then(resolve).catch(reject);
        }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          return reject(new Error(`Download failed: HTTP ${response.statusCode}`));
        }
        response.pipe(file);
        file.on("finish", () => {
          file.close();
          resolve();
        });
      })
      .on("error", (err) => {
        fs.unlink(filePath, () => {});
        reject(err);
      });
  });
}

async function main() {
  if (fs.existsSync(dest)) {
    console.log(`YuNet model already exists: ${dest}`);
    return;
  }
  console.log(`Downloading YuNet model to ${dest}`);
  fs.mkdirSync(modelsDir, { recursive: true });
  await download(MODEL_URL, dest);
  console.log("YuNet model downloaded");
}

main().catch((err) => {
  console.error("Failed to download YuNet model:", err.message);
  process.exit(1);
});
