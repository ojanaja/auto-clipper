const js = require("@eslint/js");
const prettier = require("eslint-config-prettier");

const browserGlobals = {
  window: "readonly",
  document: "readonly",
  fetch: "readonly",
  WebSocket: "readonly",
  setTimeout: "readonly",
};

module.exports = [
  js.configs.recommended,
  prettier,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        require: "readonly",
        module: "writable",
        process: "readonly",
        __dirname: "readonly",
        console: "readonly",
        ...browserGlobals,
      },
    },
  },
  {
    files: ["**/tests/**/*.js"],
    languageOptions: {
      globals: {
        describe: "readonly",
        test: "readonly",
        it: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        jest: "readonly",
        global: "writable",
      },
    },
  },
  {
    ignores: ["node_modules/", "dist/", "build/"],
  },
];
