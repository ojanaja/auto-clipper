// Helper untuk meluncurkan Electron dengan CDP (Electron 30+ tidak menerima
// flag --remote-debugging-port, jadi kita set switch dari main process).
const { spawn } = require("child_process");
const http = require("http");
const net = require("net");
const path = require("path");
const { chromium } = require("@playwright/test");

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function waitForCdp(port, timeoutMs = 10000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    function probe() {
      http
        .get(`http://127.0.0.1:${port}/json/version`, (res) => {
          if (res.statusCode === 200) return resolve();
          scheduleNext();
        })
        .on("error", () => scheduleNext());
    }
    function scheduleNext() {
      if (Date.now() - start > timeoutMs) {
        return reject(new Error(`CDP tidak tersedia di port ${port}`));
      }
      setTimeout(probe, 250);
    }
    probe();
  });
}

async function launchApp() {
  const cdpPort = await getFreePort();
  const electronPath = require("electron");
  const launcherPath = path.join(__dirname, "launcher.js");
  const child = spawn(electronPath, [launcherPath], {
    env: {
      ...process.env,
      AUTOCLIP_SKIP_BACKEND: "1",
      AUTOCLIP_CDP_PORT: String(cdpPort),
      ELECTRON_RUN_AS_NODE: "",
    },
    stdio: "pipe",
  });

  let logs = "";
  child.stderr.on("data", (chunk) => {
    logs += chunk.toString();
  });
  child.stdout.on("data", (chunk) => {
    logs += chunk.toString();
  });

  try {
    await waitForCdp(cdpPort);
  } catch (err) {
    child.kill();
    throw new Error(`${err.message}\nLogs:\n${logs}`, { cause: err });
  }

  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`);
  const context = browser.contexts()[0];
  const page = context.pages()[0] || (await context.newPage());

  async function close() {
    try {
      await browser.close();
    } catch {
      // ignore close errors
    }
    child.kill();
  }

  return { child, browser, page, close };
}

module.exports = { launchApp };
