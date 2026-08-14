const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");
const { promisify } = require("util");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

const execFileAsync = promisify(execFile);

let client;
let autoClosing = false;
let reviewOutput;
let structureRefreshTimer;

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

function codeText(text) {
  let quoted = false; let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === "#") return text.slice(0, index).trimEnd();
  }
  return text;
}

function multilineCommentDelimiter(text) {
  const candidate = text.trim();
  if (candidate === "##") return "";
  const found = /^##([\p{L}_][\p{L}\p{M}\p{N}_]*)$/u.exec(candidate);
  return found ? found[1] : undefined;
}

function labelAt(editor) {
  const line = codeText(editor.document.lineAt(editor.selection.active.line).text);
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
  let commentLabel;
  for (let line = 0; line < editor.document.lineCount; line += 1) {
    const raw = editor.document.lineAt(line).text; const delimiter = multilineCommentDelimiter(raw);
    if (delimiter !== undefined) { commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel); continue; }
    if (commentLabel !== undefined) continue;
    const text = codeText(raw); const opened = openPattern.exec(text); const closed = closePattern.exec(text);
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
  let commentLabel;
  for (let line = 0; line < editor.document.lineCount; line += 1) {
    const raw = editor.document.lineAt(line).text; const delimiter = multilineCommentDelimiter(raw);
    if (delimiter !== undefined) { commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel); continue; }
    if (commentLabel !== undefined) continue;
    const text = codeText(raw); const match = pattern.exec(text); const closed = closePattern.exec(text);
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
  const scope = await scopeAt(editor);
  if (!scope) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  await vscode.env.clipboard.writeText(`Modify only Separan scope ${scope.path}`);
  vscode.window.showInformationMessage(`Copied AI edit scope ${scope.path}`);
}

async function scopeAt(editor) {
  return client.sendRequest("separan/scopeAt", {
    textDocument: { uri: editor.document.uri.toString() },
    position: { line: editor.selection.active.line, character: editor.selection.active.character },
  });
}

async function headSource(editor) {
  const folder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
  if (!folder) throw new Error("Open the file inside a Git workspace first.");
  try {
    const rootResult = await execFileAsync("git", ["-C", folder.uri.fsPath, "rev-parse", "--show-toplevel"], { encoding: "utf8", windowsHide: true });
    const gitRoot = rootResult.stdout.trim();
    const relative = path.relative(gitRoot, editor.document.uri.fsPath).replace(/\\/g, "/");
    if (!relative || relative === ".." || relative.startsWith("../") || path.isAbsolute(relative)) throw new Error("The active file is outside the Git worktree.");
    const result = await execFileAsync("git", ["-C", gitRoot, "show", `HEAD:${relative}`], { encoding: "utf8", windowsHide: true });
    return result.stdout;
  } catch (error) {
    throw new Error("Could not read this file from Git HEAD. Commit the file once before comparing it.");
  }
}

function renderDiff(report) {
  const symbols = { added: "+", removed: "-", modified: "~", unchanged: "=" };
  const lines = ["Separan structural diff against HEAD", ""];
  if (!report.changes.length) lines.push("No structural changes.");
  for (const item of report.changes) lines.push(`${symbols[item.status]} ${item.path} (${item.status})`);
  const s = report.summary;
  lines.push("", `Added ${s.added}, removed ${s.removed}, modified ${s.modified}, unchanged ${s.unchanged}`);
  return lines.join("\n");
}

function showReview(title, content) {
  reviewOutput.clear(); reviewOutput.appendLine(title); reviewOutput.appendLine(""); reviewOutput.appendLine(content); reviewOutput.show(true);
}

const structureIcons = {
  function: "symbol-function", if: "symbol-boolean", while: "sync", for: "list-ordered",
  object: "symbol-object", list: "symbol-array", try: "shield", error: "error",
  transaction: "database", http_route: "globe",
};

class StructureTreeItem {
  constructor(data, parent = undefined) {
    this.data = data; this.parent = parent;
    this.children = (data.children || []).map((child) => new StructureTreeItem(child, this));
    this.insights = [];
    for (const [key, title, icon] of [["tags", "Tags", "tag"], ["parameters", "Parameters", "symbol-parameter"], ["reads", "Reads", "eye"], ["writes", "Writes", "edit"], ["calls", "Calls", "call-outgoing"]]) {
      if (data[key] && data[key].length) this.insights.push(new InsightGroup(title, icon, data[key], this));
    }
  }

  treeItem() {
    const label = this.data.kind === "function" ? this.data.label : `:${this.data.label}`;
    const item = new vscode.TreeItem(label, this.children.length || this.insights.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
    item.id = this.data.id; item.contextValue = "separanStructure";
    item.description = this.data.status ? `${this.data.kind} • ${this.data.status}` : this.data.kind;
    item.iconPath = new vscode.ThemeIcon(this.data.status === "modified" ? "diff-modified" : this.data.status === "added" ? "diff-added" : (structureIcons[this.data.kind] || "symbol-namespace"));
    const details = [`**${this.data.path}**`, `Lines ${this.data.start_line}–${this.data.end_line}`];
    for (const [key, title] of [["tags", "Tags"], ["parameters", "Parameters"], ["reads", "Reads"], ["writes", "Writes"], ["calls", "Calls"]]) {
      if (this.data[key] && this.data[key].length) details.push(`${title}: \`${this.data[key].join("`, `")}\``);
    }
    item.tooltip = new vscode.MarkdownString(details.join("  \n"));
    item.command = { command: "separan.revealStructure", title: "Reveal Separan Structure", arguments: [this.data] };
    return item;
  }
}

class InsightGroup {
  constructor(label, icon, values, parent) {
    this.label = label; this.icon = icon; this.parent = parent;
    this.children = values.map((value) => new InsightValue(value, this));
  }
  treeItem() {
    const item = new vscode.TreeItem(`${this.label} (${this.children.length})`, vscode.TreeItemCollapsibleState.Collapsed);
    item.iconPath = new vscode.ThemeIcon(this.icon); item.contextValue = "separanInsightGroup"; return item;
  }
}

class InsightValue {
  constructor(value, parent) { this.value = value; this.parent = parent; this.children = []; }
  treeItem() { const tag = this.parent.label === "Tags"; const item = new vscode.TreeItem(tag ? `@${this.value}` : this.value, vscode.TreeItemCollapsibleState.None); item.iconPath = new vscode.ThemeIcon(tag ? "tag" : "symbol-variable"); return item; }
}

class RemovedGroup {
  constructor(changes) {
    this.parent = undefined;
    this.children = changes.map((change) => new RemovedItem(change, this));
  }
  treeItem() {
    const item = new vscode.TreeItem(`Removed from HEAD (${this.children.length})`, vscode.TreeItemCollapsibleState.Collapsed);
    item.iconPath = new vscode.ThemeIcon("diff-removed"); item.contextValue = "separanRemovedGroup"; return item;
  }
}

class RemovedItem {
  constructor(change, parent) { this.change = change; this.parent = parent; this.children = []; }
  treeItem() {
    const item = new vscode.TreeItem(this.change.path, vscode.TreeItemCollapsibleState.None);
    item.description = "removed"; item.iconPath = new vscode.ThemeIcon("diff-removed"); return item;
  }
}

class StructureProvider {
  constructor() {
    this.emitter = new vscode.EventEmitter(); this.onDidChangeTreeData = this.emitter.event;
    this.roots = []; this.loadedKey = undefined; this.nodesById = new Map();
  }

  refresh() { this.loadedKey = undefined; this.emitter.fire(undefined); }
  getTreeItem(element) { return element.treeItem(); }
  getParent(element) { return element.parent; }
  async getChildren(element) {
    if (element) return element.children || [];
    await this.load(); return this.roots;
  }

  async load() {
    const editor = currentEditor();
    if (!editor) { this.roots = []; this.loadedKey = undefined; return; }
    const key = `${editor.document.uri}:${editor.document.version}`;
    if (this.loadedKey === key) return;
    const report = await client.sendRequest("separan/documentStructure", { textDocument: { uri: editor.document.uri.toString() } });
    if (report.error) { this.roots = []; this.loadedKey = key; return; }
    const statuses = new Map(); let removed = [];
    try {
      const before = await headSource(editor);
      const diff = await client.sendRequest("separan/structuralDiff", { before, after: editor.document.getText(), uri: editor.document.uri.toString() });
      if (!diff.error) {
        for (const change of diff.changes) {
          if (change.status === "removed") removed.push(change);
          else statuses.set(change.id, change.status);
        }
      }
    } catch (_) { /* Untracked files still have a useful structure tree. */ }
    const applyStatus = (node) => {
      node.status = statuses.get(node.id);
      for (const child of node.children || []) applyStatus(child);
      return node;
    };
    this.roots = report.roots.map((root) => new StructureTreeItem(applyStatus(root)));
    if (removed.length) this.roots.push(new RemovedGroup(removed));
    this.nodesById.clear();
    const index = (node) => { if (node.data) this.nodesById.set(node.data.id, node); for (const child of node.children || []) index(child); };
    for (const root of this.roots) index(root);
    this.loadedKey = key;
  }

  async activeNode(line) {
    await this.load(); let best;
    for (const node of this.nodesById.values()) {
      if (node.data.start_line - 1 <= line && line <= node.data.end_line - 1 && (!best || node.data.start_line >= best.data.start_line)) best = node;
    }
    return best;
  }
}

async function revealStructure(data) {
  const editor = currentEditor(); if (!editor || !data || !data.start_line) return;
  const position = new vscode.Position(data.start_line - 1, Math.max(0, data.start_column - 1));
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

async function showStructuralDiff() {
  const editor = currentEditor(); if (!editor) return;
  try {
    const before = await headSource(editor);
    const report = await client.sendRequest("separan/structuralDiff", { before, after: editor.document.getText(), uri: editor.document.uri.toString() });
    if (report.error) throw new Error(report.error);
    showReview("Separan v0.4 — Structural Diff", renderDiff(report));
  } catch (error) { vscode.window.showErrorMessage(error.message); }
}

async function verifyAiEditScope() {
  const editor = currentEditor(); if (!editor) return;
  try {
    const scope = await scopeAt(editor);
    if (!scope) return vscode.window.showInformationMessage("Place the cursor on the label that defines the allowed AI edit scope.");
    const before = await headSource(editor);
    const report = await client.sendRequest("separan/verifyScope", {
      before, after: editor.document.getText(), uri: editor.document.uri.toString(), scopes: [scope.path],
    });
    if (report.error) throw new Error(report.error);
    const lines = [report.passed ? "PASS: AI edit scope verified." : "FAIL: AI edit scope violation.", `Allowed: ${scope.path}`];
    for (const item of report.violations) lines.push(`! ${item.path}: ${item.reason}`);
    lines.push(`Allowed changes ${report.summary.allowed_changes}, violations ${report.summary.violations}`);
    showReview("Separan v0.4 — AI Edit Scope Verification", lines.join("\n"));
    if (report.passed) vscode.window.showInformationMessage(`Verified: changes stay inside ${scope.path}`);
    else vscode.window.showErrorMessage(`AI scope violation: ${report.summary.violations} out-of-scope change(s).`);
  } catch (error) { vscode.window.showErrorMessage(error.message); }
}

async function autoClose(event) {
  if (autoClosing || event.document.languageId !== "separan" || !vscode.workspace.getConfiguration("separan").get("autoCloseLabels", true)) return;
  if (!event.contentChanges.some((change) => change.text.includes("\n"))) return;
  const editor = currentEditor(); if (!editor || editor.document !== event.document) return;
  const lineNumber = Math.max(0, editor.selection.active.line - 1); const text = codeText(event.document.lineAt(lineNumber).text);
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
  reviewOutput = vscode.window.createOutputChannel("Separan Review");
  const structureProvider = new StructureProvider();
  const structureView = vscode.window.createTreeView("separan.structureExplorer", { treeDataProvider: structureProvider, showCollapseAll: true });
  const refreshStructureSoon = (event) => {
    if (event && event.document && event.document.languageId !== "separan") return;
    clearTimeout(structureRefreshTimer); structureRefreshTimer = setTimeout(() => structureProvider.refresh(), 250);
  };
  context.subscriptions.push(
    { dispose: () => client && client.stop() },
    vscode.commands.registerCommand("separan.runFile", () => runFile(false)),
    vscode.commands.registerCommand("separan.showAst", () => runFile(true)),
    vscode.commands.registerCommand("separan.runTests", runTests),
    vscode.commands.registerCommand("separan.goToMatchingLabel", goToMatchingLabel),
    vscode.commands.registerCommand("separan.goToLabel", goToLabel),
    vscode.commands.registerCommand("separan.copyAiEditScope", copyAiScope),
    vscode.commands.registerCommand("separan.showStructuralDiff", showStructuralDiff),
    vscode.commands.registerCommand("separan.verifyAiEditScope", verifyAiEditScope),
    vscode.commands.registerCommand("separan.refreshStructureExplorer", () => structureProvider.refresh()),
    vscode.commands.registerCommand("separan.revealStructure", revealStructure),
    reviewOutput,
    structureView,
    vscode.workspace.onDidChangeTextDocument(autoClose),
    vscode.workspace.onDidChangeTextDocument(refreshStructureSoon),
    vscode.workspace.onDidSaveTextDocument((document) => { if (document.languageId === "separan") structureProvider.refresh(); }),
    vscode.window.onDidChangeActiveTextEditor(() => structureProvider.refresh()),
    vscode.window.onDidChangeTextEditorSelection(async (event) => {
      if (event.textEditor.document.languageId !== "separan" || !structureView.visible) return;
      const node = await structureProvider.activeNode(event.selections[0].active.line);
      if (node) structureView.reveal(node, { select: true, focus: false, expand: true });
    }),
  );
}

function deactivate() { return client ? client.stop() : undefined; }
module.exports = { activate, deactivate };
