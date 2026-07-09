// Launcher untuk E2E: nyalakan remote-debugging-port via switch
// (Electron 30+ tidak menerima flag CLI --remote-debugging-port).
const { app } = require("electron");

const cdpPort = process.env.AUTOCLIP_CDP_PORT || "9222";
app.commandLine.appendSwitch("remote-debugging-port", cdpPort);
app.commandLine.appendSwitch("remote-allow-origins", "*");

require("../src/main/main.js");
