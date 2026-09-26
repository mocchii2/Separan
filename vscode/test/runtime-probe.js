const fs = require("fs");

const arguments_ = process.argv.slice(2);
const sourcePath = arguments_[arguments_.length - 1];
const result = { arguments: arguments_, sourcePath, source: fs.readFileSync(sourcePath, "utf8") };
fs.writeFileSync(process.env.SEPARAN_TEST_OUTPUT, JSON.stringify(result), "utf8");
