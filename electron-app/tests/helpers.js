const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "..", "src", "renderer", "index.html"), "utf-8");

/** FakeWebSocket: test dispatch pesan via instance.emit(event). */
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.onmessage = null;
    this.closed = false;
    FakeWebSocket.instances.push(this);
  }
  emit(event) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(event) });
  }
  close() {
    this.closed = true;
  }
}
FakeWebSocket.instances = [];

function loadApp({ autoCheck = false } = {}) {
  window.__AUTOCLIP_TEST__ = true; // cegah auto-setup saat require
  // autoCheck: true -> izinkan checkApiKey (onboarding gate) jalan seperti produksi,
  // tanpa menghidupkan lagi auto-bootstrap DOMContentLoaded (tetap dijaga __AUTOCLIP_TEST__).
  window.__AUTOCLIP_FORCE_API_KEY_CHECK__ = autoCheck;
  document.body.innerHTML = html.match(/<body>([\s\S]*)<\/body>/)[1];
  FakeWebSocket.instances = [];
  global.WebSocket = FakeWebSocket;
  jest.resetModules();
  const app = require("../src/renderer/app.js");
  app.setupApp(document);
  return app;
}

/** Respons fetch berurutan: tiap panggilan ambil antrian berikutnya. */
function mockFetchQueue(responses) {
  const queue = [...responses];
  global.fetch = jest.fn(() => {
    const next = queue.length > 1 ? queue.shift() : queue[0];
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(next),
    });
  });
  return global.fetch;
}

module.exports = { loadApp, mockFetchQueue, FakeWebSocket };
