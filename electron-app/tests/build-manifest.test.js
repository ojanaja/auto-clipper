const { execSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const verifyScript = path.resolve(__dirname, "..", "scripts", "verify-build.js");

describe("build manifest verification", () => {
  let tmpDir;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "autoclip-dist-"));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function runVerify() {
    return execSync(`node "${verifyScript}"`, {
      env: { ...process.env, DIST_DIR: tmpDir },
      encoding: "utf8",
      stdio: "pipe",
    });
  }

  function makeMacUnpacked() {
    const appBundle = path.join(tmpDir, "mac", "AutoClip Lokal.app");
    const resources = path.join(appBundle, "Contents", "Resources");
    const macos = path.join(appBundle, "Contents", "MacOS");
    fs.mkdirSync(resources, { recursive: true });
    fs.mkdirSync(macos, { recursive: true });
    fs.writeFileSync(path.join(macos, "AutoClip Lokal"), "");
    fs.mkdirSync(path.join(resources, "backend", "bin"), { recursive: true });
    fs.mkdirSync(path.join(resources, "backend", "models"), { recursive: true });
    fs.writeFileSync(path.join(resources, "backend", "autoclip-backend"), "");
    fs.writeFileSync(path.join(resources, "backend", "bin", "ffmpeg"), "");
    fs.writeFileSync(path.join(resources, "backend", "bin", "ffprobe"), "");
    fs.writeFileSync(
      path.join(resources, "backend", "models", "face_detection_yunet_2023mar.onnx"),
      ""
    );
    fs.mkdirSync(path.join(resources, "app"), { recursive: true });
    fs.writeFileSync(path.join(resources, "app", "package.json"), "{}");
  }

  function makeWinUnpacked() {
    const unpacked = path.join(tmpDir, "win-unpacked");
    const resources = path.join(unpacked, "resources");
    fs.mkdirSync(resources, { recursive: true });
    fs.writeFileSync(path.join(unpacked, "AutoClip Lokal.exe"), "");
    fs.mkdirSync(path.join(resources, "backend", "bin"), { recursive: true });
    fs.mkdirSync(path.join(resources, "backend", "models"), { recursive: true });
    fs.writeFileSync(path.join(resources, "backend", "autoclip-backend.exe"), "");
    fs.writeFileSync(path.join(resources, "backend", "bin", "ffmpeg.exe"), "");
    fs.writeFileSync(path.join(resources, "backend", "bin", "ffprobe.exe"), "");
    fs.writeFileSync(
      path.join(resources, "backend", "models", "face_detection_yunet_2023mar.onnx"),
      ""
    );
    fs.mkdirSync(path.join(resources, "app"), { recursive: true });
    fs.writeFileSync(path.join(resources, "app", "package.json"), "{}");
  }

  (process.platform === "darwin" ? test : test.skip)("passes for valid macOS unpacked app", () => {
    makeMacUnpacked();
    const output = runVerify();
    expect(output).toContain("Build manifest verification passed");
  });

  (process.platform === "win32" ? test : test.skip)("passes for valid Windows unpacked app", () => {
    makeWinUnpacked();
    const output = runVerify();
    expect(output).toContain("Build manifest verification passed");
  });

  (process.platform === "darwin" ? test : test.skip)(
    "fails when backend sidecar is missing",
    () => {
      makeMacUnpacked();
      fs.unlinkSync(
        path.join(
          tmpDir,
          "mac",
          "AutoClip Lokal.app",
          "Contents",
          "Resources",
          "backend",
          "autoclip-backend"
        )
      );
      expect(() => runVerify()).toThrow(/Missing backend sidecar/);
    }
  );

  (process.platform === "darwin" ? test : test.skip)(
    "fails when ffmpeg/ffprobe are missing",
    () => {
      makeMacUnpacked();
      fs.rmSync(
        path.join(tmpDir, "mac", "AutoClip Lokal.app", "Contents", "Resources", "backend", "bin"),
        {
          recursive: true,
          force: true,
        }
      );
      expect(() => runVerify()).toThrow(/Missing ffmpeg/);
    }
  );

  test("fails when no packaged app or installer exists", () => {
    expect(() => runVerify()).toThrow(/No packaged app or installer found/);
  });
});
