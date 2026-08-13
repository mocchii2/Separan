const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const python = vscode.workspace.getConfiguration("separan").get("pythonPath", "python");
  const serverOptions = {
    command: python,
    args: ["-m", "separan.lsp"],
    transport: TransportKind.stdio,
  };
  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "separan" }],
    synchronize: { fileEvents: vscode.workspace.createFileSystemWatcher("**/*.sep") },
  };
  client = new LanguageClient("separan", "Separan Language Server", serverOptions, clientOptions);
  client.start();
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
