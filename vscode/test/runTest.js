const path = require("path");
const { runTests } = require("@vscode/test-electron");

async function main() {
  delete process.env.ELECTRON_RUN_AS_NODE;
  await runTests({
    version: "1.95.3",
    extensionDevelopmentPath: path.resolve(__dirname, ".."),
    extensionTestsPath: path.resolve(__dirname, "suite", "index.js"),
    launchArgs: [path.resolve(__dirname, "fixtures"), "--disable-extensions"],
  });
}

main().catch((error) => { console.error(error); process.exit(1); });
