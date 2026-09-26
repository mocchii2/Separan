const path = require("path");
const Mocha = require("mocha");

async function run() {
  const mocha = new Mocha({ ui: "tdd", color: true, timeout: 20000 });
  mocha.addFile(path.resolve(__dirname, "providers.test.js"));
  await new Promise((resolve, reject) => mocha.run((failures) => failures ? reject(new Error(`${failures} test(s) failed`)) : resolve()));
}

module.exports = { run };
