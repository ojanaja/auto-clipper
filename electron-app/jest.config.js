module.exports = {
  testEnvironment: "jsdom",
  testMatch: ["**/tests/**/*.test.js"],
  passWithNoTests: true,
  setupFilesAfterEnv: ["<rootDir>/tests/setup.js"],
};
