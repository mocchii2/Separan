const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;
let autoClosing = false;

const blockPairs = {
  function: "end_function", if: "endif", while: "endwhile", for: "endfor",
  object: "end_object", list: "end_list", try: "endtry", error: "end_error",
  transaction: "end_transaction", http_route: "end_http_route",
};

function quoted(value) {
  return `"${String(value).replace(/"/g, '\\"')}"`;
}

function currentEditor() {
  const editor = vscode.window.activeTextEditor;
  return editor && editor.document.languageId === "separan" ? editor : undefined;
}

function labelAt(editor) {
  const line = editor.document.lineAt(editor.selection.active.line).text;
  const cursor = editor.selection.active.character;
  const matcher = /:([^\s:()]+)/gu;
  for (const found of line.matchAll(matcher)) {
    const start = found.index + 1;
    if (start <= cursor && cursor <= start + found[1].length) return found[1];
  }
  return undefined;
}

async function goToMatchingLabel() {
  const editor = currentEditor(); if (!editor) return;
  const label = labelAt(editor); if (!label) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  const stack = []; const completed = [];
  const openPattern = /^\s*(function|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(end_function|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  const closerKinds = { end_function: "function", endif: "if", endwhile: "while", endfor: "for", end_object: "object", end_list: "list", endtry: "try", end_error: "error", end_http_route: "http_route", end_transaction: "transaction" };
  for (let line = 0; line < editor.document.lineCount; line += 1) {
    const text = editor.document.lineAt(line).text; const opened = openPattern.exec(text); const closed = closePattern.exec(text);
    if (opened) stack.push({ kind: opened[1], label: opened[2], open: line });
    else if (closed && stack.length && stack[stack.length - 1].kind === closerKinds[closed[1]] && stack[stack.length - 1].label === closed[2]) {
      const item = stack.pop(); item.close = line; completed.push(item);
    }
  }
  const currentLine = editor.selection.active.line;
  const block = completed.find((item) => item.label === label && (item.open === currentLine || item.close === currentLine));
  if (!block) return vscode.window.showInformationMessage(`No matching endpoint found for :${label}.`);
  const targetLine = block.open === currentLine ? block.close : block.open;
  const text = editor.document.lineAt(targetLine).text; const start = text.lastIndexOf(`:${label}`) + 1;
  const target = new vscode.Position(targetLine, start);
  if (target) { editor.selection = new vscode.Selection(target, target); editor.revealRange(new vscode.Range(target, target)); }
}

async function goToLabel() {
  const editor = currentEditor(); if (!editor) return;
  const items = []; const stack = [];
  const pattern = /^\s*(function|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(end_function|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  for (let line = 0; line < editor.document.lineCount; line += 1) {
    const text = editor.document.lineAt(line).text; const match = pattern.exec(text); const closed = closePattern.exec(text);
    if (match) {
      const parent = stack.length ? `${stack.map((item) => item.label).join(" › ")} › ` : "";
      items.push({ label: match[2], description: `${parent}${match[1]} — line ${line + 1}`, line }); stack.push({ label: match[2] });
    } else if (closed && stack.length && stack[stack.length - 1].label === closed[2]) stack.pop();
  }
  const selected = await vscode.window.showQuickPick(items, { placeHolder: "Go to a labeled structure" });
  if (selected) { const position = new vscode.Position(selected.line, 0); editor.selection = new vscode.Selection(position, position); editor.revealRange(new vscode.Range(position, position)); }
}

async function runFile(ast = false) {
  const editor = currentEditor(); if (!editor) return;
  await editor.document.save();
  const python = vscode.workspace.getConfiguration("separan").get("pythonPath", "python");
  const terminal = vscode.window.createTerminal(ast ? "Separan AST" : "Separan");
  terminal.show(); terminal.sendText(`${quoted(python)} -m separan ${ast ? "--ast " : ""}${quoted(editor.document.uri.fsPath)}`);
}

async function runTests() {
  const terminal = vscode.window.createTerminal("Separan Tests"); terminal.show();
  terminal.sendText(`${quoted(vscode.workspace.getConfiguration("separan").get("pythonPath", "python"))} -m unittest discover -s tests -v`);
}

async function copyAiScope() {
  const editor = currentEditor(); if (!editor) return;
  const label = labelAt(editor); if (!label) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  await vscode.env.clipboard.writeText(`Modify only :${label}`);
  vscode.window.showInformationMessage(`Copied AI edit scope :${label}`);
}

async function autoClose(event) {
  if (autoClosing || event.document.languageId !== "separan" || !vscode.workspace.getConfiguration("separan").get("autoCloseLabels", true)) return;
  if (!event.contentChanges.some((change) => change.text.includes("\n"))) return;
  const editor = currentEditor(); if (!editor || editor.document !== event.document) return;
  const lineNumber = Math.max(0, editor.selection.active.line - 1); const text = event.document.lineAt(lineNumber).text;
  const match = /^\s*(function|if|while|for|object|list|try|error|transaction|http_route)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u.exec(text);
  if (!match || !blockPairs[match[1]]) return;
  const closer = `${blockPairs[match[1]]}:${match[2]}`;
  if (event.document.lineAt(editor.selection.active.line).text.trim() === closer) return;
  const indent = text.match(/^\s*/)[0]; const insertion = editor.selection.active; autoClosing = true;
  try {
    await editor.edit((builder) => builder.insert(insertion, `\n${indent}${closer}`));
    editor.selection = new vscode.Selection(insertion, insertion);
  } finally { autoClosing = false; }
}

function activate(context) {
  const config = vscode.workspace.getConfiguration("separan");
  const serverOptions = { command: config.get("pythonPath", "python"), args: ["-m", "separan.lsp"], transport: TransportKind.stdio };
  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "separan" }],
    synchronize: { fileEvents: vscode.workspace.createFileSystemWatcher("**/*.sep") },
    initializationOptions: { inlayHints: config.get("inlayHints.types", true) },
  };
  client = new LanguageClient("separan", "Separan Language Server", serverOptions, clientOptions); client.start();
  context.subscriptions.push(
    { dispose: () => client && client.stop() },
    vscode.commands.registerCommand("separan.runFile", () => runFile(false)),
    vscode.commands.registerCommand("separan.showAst", () => runFile(true)),
    vscode.commands.registerCommand("separan.runTests", runTests),
    vscode.commands.registerCommand("separan.goToMatchingLabel", goToMatchingLabel),
    vscode.commands.registerCommand("separan.goToLabel", goToLabel),
    vscode.commands.registerCommand("separan.copyAiEditScope", copyAiScope),
    vscode.workspace.onDidChangeTextDocument(autoClose),
  );
}

function deactivate() { return client ? client.stop() : undefined; }
module.exports = { activate, deactivate };
