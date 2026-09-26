const vscode = require("vscode");
const { execFile } = require("child_process");
const fs = require("fs");
const builtinMetadata = require("./data/builtins.json");
const path = require("path");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);

let autoClosing = false;
let reviewOutput;
let runtimeOutput;
let structureRefreshTimer;
let runStatus;
let checkStatus;
let structureDiagnostics;
let nativeDiagnostics;
let analysisDiagnostics;
let diagnosticTimer;
const diagnosticVersions = new Map();
const temporaryRuns = new Map();

const blockPairs = {
  SEP: "END_SEP", if: "endif", while: "endwhile", for: "endfor",
  object: "end_object", list: "end_list", try: "endtry", error: "end_error",
  transaction: "end_transaction", http_route: "end_http_route",
};

const builtinSignatureOverrides = {
  print: "print(value)", print_error: "print_error(value)", type_of: "type_of(value)", length: "length(value)",
  string: "string(value)", number: "number(value)", boolean: "boolean(value)", format: "format(template, values...)",
  trim: "trim(value)", upper: "upper(value)", lower: "lower(value)", substring: "substring(value, start, end?)",
  split: "split(value, separator)", join: "join(values, separator)", replace: "replace(value, old, new)",
  list_append: "list_append(values, value)", first: "first(values)", last: "last(values)", slice: "slice(values, start, end)",
  map: "map(values, function)", filter: "filter(values, function)", reduce: "reduce(values, function, initial)",
  object_get: "object_get(object, key)", object_set: "object_set(object, key, value)", object_has: "object_has(object, key)",
  json_encode: "json_encode(value)", json_decode: "json_decode(text)", read_text: "read_text(path)", write_text: "write_text(path, text)",
  bytes_from_string: "bytes_from_string(value, encoding?)", string_from_bytes: "string_from_bytes(value, encoding?)",
  regex_find: "regex_find(pattern, text)", regex_find_all: "regex_find_all(pattern, text)", regex_replace: "regex_replace(pattern, text, replacement)",
  db_connect: "db_connect(driver:, database:, host?:, port?:, user?:, password?:)", db_query: "db_query(connection, query, parameters, timeout?:)",
  exec: "exec(command, arguments, cwd?:, timeout?:)", http_get: "http_get(url, headers?:, timeout?:)",
  duration: "duration(value)", datetime_parse: "datetime_parse(value)", random_int: "random_int(minimum, maximum)",
};
const builtinReturnTypeOverrides = {
  type_of: "string", length: "number", string: "string", number: "number", boolean: "boolean", format: "string",
  trim: "string", upper: "string", lower: "string", substring: "string", join: "string", replace: "string",
  split: "list<string>", list_append: "list", first: "value", last: "value", slice: "list", map: "list", filter: "list",
  object_get: "value", object_set: "object", object_has: "boolean", json_encode: "string", json_decode: "value",
  read_text: "string", bytes_from_string: "bytes", string_from_bytes: "string", regex_find: "regex_match_result",
  regex_find_all: "list<regex_match_result>", db_connect: "db_connection", db_query: "list<object>", exec: "exec_result",
  http_get: "http_response", duration: "duration", datetime_parse: "datetime", random_int: "number",
};
const builtinSignatures = Object.fromEntries(Object.entries(builtinMetadata).map(([name, value]) => [name, builtinSignatureOverrides[name] || value.signature]));
const builtinReturnTypes = Object.fromEntries(Object.entries(builtinMetadata).map(([name, value]) => [name, builtinReturnTypeOverrides[name] || value.returnType.split(" | ", 1)[0]]));

function runtimeConfiguration(resource) {
  const config = vscode.workspace.getConfiguration("separan", resource);
  return {
    executable: config.get("executablePath", "separan"),
    arguments: config.get("runtimeArguments", []),
    environment: config.get("environment", {}),
  };
}

async function executeSeparanTask(name, resource, arguments_) {
  const config = runtimeConfiguration(resource);
  const folder = resource ? vscode.workspace.getWorkspaceFolder(resource) : undefined;
  const scope = folder || vscode.TaskScope.Workspace;
  const execution = new vscode.ProcessExecution(config.executable, [...config.arguments, ...arguments_], {
    cwd: folder ? folder.uri.fsPath : undefined,
    env: { ...process.env, ...config.environment },
  });
  const task = new vscode.Task({ type: "separan", task: name }, scope, name, "Separan", execution);
  task.presentationOptions = { reveal: vscode.TaskRevealKind.Always, panel: vscode.TaskPanelKind.Dedicated, clear: true };
  return vscode.tasks.executeTask(task);
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

function labelAtPosition(document, position) {
  const line = codeText(document.lineAt(position.line).text); const matcher = /:([^\s:()]+)/gu;
  for (const found of line.matchAll(matcher)) {
    const start = found.index + 1; const end = start + found[1].length;
    if (start <= position.character && position.character <= end) return { name: found[1], range: new vscode.Range(position.line, start, position.line, end) };
  }
  return undefined;
}

function identifierAtPosition(document, position) {
  const range = document.getWordRangeAtPosition(position, /[\p{L}_][\p{L}\p{M}\p{N}_]*/u);
  return range ? { name: document.getText(range), range } : undefined;
}

function tagAtPosition(document, position) {
  const text = codeText(document.lineAt(position.line).text); const matcher = /@([\p{L}_][\p{L}\p{M}\p{N}_]*)/gu;
  for (const found of text.matchAll(matcher)) {
    const start = found.index + 1; const end = start + found[1].length;
    if (start <= position.character && position.character <= end) return { name: found[1], range: new vscode.Range(position.line, start, position.line, end) };
  }
  return undefined;
}

function tagLocations(document, name) {
  const locations = []; const escaped = name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"); const pattern = new RegExp(`@${escaped}\\b`, "gu");
  for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern))
    locations.push(new vscode.Location(document.uri, new vscode.Range(line, match.index + 1, line, match.index + 1 + name.length)));
  return locations;
}

function allLabelLocations(document, name) {
  const locations = []; const pattern = new RegExp(`:${name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}(?=\\s|\\(|$)`, "gu");
  for (let line = 0; line < document.lineCount; line += 1) {
    const text = codeText(document.lineAt(line).text);
    for (const match of text.matchAll(pattern)) locations.push(new vscode.Location(document.uri, new vscode.Range(line, match.index + 1, line, match.index + 1 + name.length)));
  }
  return locations;
}

function functionDefinitions(document) {
  const definitions = new Map();
  for (const item of flattenStructures(documentStructure(document.getText()).roots)) {
    if (item.kind === "SEP") definitions.set(item.label, new vscode.Location(document.uri,
      new vscode.Position(item.start_line - 1, item.start_column - 1)));
  }
  return definitions;
}

function functionLocations(document, name) {
  const locations = []; const definition = flattenStructures(documentStructure(document.getText()).roots).find((item) => item.kind === "SEP" && item.label === name);
  if (!definition) return locations;
  for (const line of [definition.start_line - 1, definition.end_line - 1]) {
    const text = codeText(document.lineAt(line).text); const at = text.indexOf(`:${name}`);
    if (at >= 0) locations.push(new vscode.Location(document.uri, new vscode.Range(line, at + 1, line, at + 1 + name.length)));
  }
  const pattern = new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}\\s*(?=\\()`, "gu");
  for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern))
    locations.push(new vscode.Location(document.uri, new vscode.Range(line, match.index, line, match.index + name.length)));
  const unique = new Map();
  for (const location of locations) unique.set(`${location.range.start.line}:${location.range.start.character}`, location);
  return [...unique.values()];
}

async function workspaceSeparanDocuments() {
  const files = await vscode.workspace.findFiles("**/*.sep", "**/{.git,node_modules,build,dist}/**", 2000);
  const documents = await Promise.all(files.map((uri) => vscode.workspace.openTextDocument(uri)));
  const unique = new Map(documents.map((document) => [document.uri.toString(), document]));
  for (const document of vscode.workspace.textDocuments)
    if (document.languageId === "separan" && document.uri.scheme === "file") unique.set(document.uri.toString(), document);
  return [...unique.values()];
}

function importAliases(document) {
  const aliases = new Map(); const pattern = /^\s*import\s+"([^"]+)"\s+as\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*$/u;
  for (let line = 0; line < document.lineCount; line += 1) { const found = pattern.exec(codeText(document.lineAt(line).text)); if (found) aliases.set(found[2], found[1]); }
  return aliases;
}

function importDeclarations(document) {
  const declarations = []; const pattern = /^\s*import\s+"([^"]+)"\s+as\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*$/u;
  for (let line = 0; line < document.lineCount; line += 1) {
    const text = codeText(document.lineAt(line).text); const found = pattern.exec(text);
    if (found) declarations.push({ path: found[1], alias: found[2], line,
      pathRange: new vscode.Range(line, found.index + text.indexOf(found[1]), line, found.index + text.indexOf(found[1]) + found[1].length),
      aliasRange: new vscode.Range(line, text.lastIndexOf(found[2]), line, text.lastIndexOf(found[2]) + found[2].length) });
  }
  return declarations;
}

function importAtPosition(document, position) {
  return importDeclarations(document).find((item) => item.pathRange.contains(position));
}

function moduleUri(document, relative) {
  if (!relative || document.uri.scheme !== "file") return undefined;
  const candidate = path.resolve(path.dirname(document.uri.fsPath), relative.endsWith(".sep") ? relative : relative + ".sep");
  return vscode.Uri.file(candidate);
}

function importedUri(document, alias) {
  return moduleUri(document, importAliases(document).get(alias));
}

function qualifiedFunctionLocations(document, alias, name) {
  const locations = []; const escapedAlias = alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const escapedName = name.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const pattern = new RegExp("\\b" + escapedAlias + "\\.(" + escapedName + ")\\s*(?=\\()", "gu");
  for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
    const start = match.index + alias.length + 1;
    locations.push(new vscode.Location(document.uri, new vscode.Range(line, start, line, start + name.length)));
  }
  return locations;
}

async function importedFunctionLocations(targetDocument, name, sourceDocument) {
  const workspaceDocuments = await workspaceSeparanDocuments();
  const documents = new Map([[targetDocument.uri.toString(), targetDocument], [sourceDocument.uri.toString(), sourceDocument],
    ...workspaceDocuments.map((candidate) => [candidate.uri.toString(), candidate])]);
  const locations = []; const definition = functionDefinitions(targetDocument).get(name); if (definition) locations.push(definition);
  for (const candidate of documents.values()) for (const alias of importAliases(candidate).keys()) {
    const uri = importedUri(candidate, alias);
    if (uri && uri.fsPath.toLocaleLowerCase() === targetDocument.uri.fsPath.toLocaleLowerCase())
      locations.push(...qualifiedFunctionLocations(candidate, alias, name));
  }
  return locations;
}

async function importedDocument(document, alias) {
  const relative = importAliases(document).get(alias); if (!relative || document.uri.scheme !== "file") return undefined;
  const candidate = path.resolve(path.dirname(document.uri.fsPath), relative.endsWith(".sep") ? relative : `${relative}.sep`);
  try { return await vscode.workspace.openTextDocument(vscode.Uri.file(candidate)); } catch (_) { return undefined; }
}

async function importReaches(document, targetUri, visited = new Set()) {
  const key = document.uri.toString().toLocaleLowerCase();
  if (key === targetUri.toString().toLocaleLowerCase()) return true;
  if (visited.has(key)) return false;
  visited.add(key);
  for (const declaration of importDeclarations(document)) {
    const uri = moduleUri(document, declaration.path); if (!uri) continue;
    if (uri.toString().toLocaleLowerCase() === targetUri.toString().toLocaleLowerCase()) return true;
    try {
      const imported = await vscode.workspace.openTextDocument(uri);
      if (await importReaches(imported, targetUri, visited)) return true;
    } catch (_) { /* Missing imports are diagnosed separately. */ }
  }
  return false;
}

async function importRenameEdit(files) {
  const renamed = new Map(files.filter((file) => file.oldUri.scheme === "file" && file.newUri.scheme === "file")
    .map((file) => [file.oldUri.fsPath.toLocaleLowerCase(), file.newUri.fsPath]));
  const edit = new vscode.WorkspaceEdit(); if (!renamed.size) return edit;
  for (const document of await workspaceSeparanDocuments()) {
    const futureDocumentPath = renamed.get(document.uri.fsPath.toLocaleLowerCase()) || document.uri.fsPath;
    for (const declaration of importDeclarations(document)) {
      const target = moduleUri(document, declaration.path); const renamedTarget = target && renamed.get(target.fsPath.toLocaleLowerCase());
      if (!renamedTarget) continue;
      let relative = path.relative(path.dirname(futureDocumentPath), renamedTarget).replace(/\\/gu, "/");
      if (relative.endsWith(".sep")) relative = relative.slice(0, -4);
      if (!relative.startsWith(".")) relative = "./" + relative;
      edit.replace(document.uri, declaration.pathRange, relative);
    }
  }
  return edit;
}

function qualifiedIdentifierAt(document, position) {
  const text = codeText(document.lineAt(position.line).text); const pattern = /([\p{L}_][\p{L}\p{M}\p{N}_]*)\.([\p{L}_][\p{L}\p{M}\p{N}_]*)/gu;
  for (const found of text.matchAll(pattern)) {
    const memberStart = found.index + found[1].length + 1; const memberEnd = memberStart + found[2].length;
    if (memberStart <= position.character && position.character <= memberEnd) return { alias: found[1], name: found[2] };
  }
  return undefined;
}

class SeparanCompletionProvider {
  async provideCompletionItems(document, position) {
    const prefix = document.lineAt(position.line).text.slice(0, position.character);
    const importPath = /^\s*import\s+"([^"]*)$/u.exec(prefix);
    if (importPath && document.uri.scheme === "file") {
      const fragment = importPath[1]; const slash = Math.max(fragment.lastIndexOf("/"), fragment.lastIndexOf("\\"));
      const directoryPart = slash >= 0 ? fragment.slice(0, slash + 1) : "";
      const namePart = fragment.slice(slash + 1); const directory = path.resolve(path.dirname(document.uri.fsPath), directoryPart || ".");
      try {
        const entries = await fs.promises.readdir(directory, { withFileTypes: true }); const start = position.character - fragment.length;
        return entries.filter((entry) => (entry.isDirectory() || entry.name.endsWith(".sep")) && entry.name.startsWith(namePart)).map((entry) => {
          const name = entry.isDirectory() ? entry.name + "/" : entry.name.slice(0, -4);
          const completion = new vscode.CompletionItem(directoryPart.replace(/\\/gu, "/") + name,
            entry.isDirectory() ? vscode.CompletionItemKind.Folder : vscode.CompletionItemKind.Module);
          completion.range = new vscode.Range(position.line, start, position.line, position.character);
          completion.insertText = directoryPart.replace(/\\/gu, "/") + name; return completion;
        });
      } catch (_) { return []; }
    }
    const imported = /([\p{L}_][\p{L}\p{M}\p{N}_]*)\.$/u.exec(prefix);
    if (imported) {
      const target = await importedDocument(document, imported[1]); if (!target) return [];
      return [...functionDefinitions(target).keys()].map((name) => new vscode.CompletionItem(name, vscode.CompletionItemKind.Function));
    }
    if (/^\s*:end\w*$/u.test(prefix)) {
      const open = flattenStructures(documentStructure(document.getText(new vscode.Range(new vscode.Position(0, 0), position))).roots)
        .filter((item) => item.start_line <= position.line + 1 && item.end_line >= position.line + 1)
        .sort((a, b) => b.start_line - a.start_line);
      return open.map((item, index) => {
        const closer = `${blockPairs[item.kind]}:${item.label}`;
        const completion = new vscode.CompletionItem(closer, vscode.CompletionItemKind.Keyword);
        completion.detail = `Closes ${item.kind}:${item.label} from line ${item.start_line}`;
        completion.sortText = String(index).padStart(4, "0"); completion.insertText = closer; return completion;
      });
    }
    const functions = [...functionDefinitions(document).keys()].map((name) => {
      const completion = new vscode.CompletionItem(name, vscode.CompletionItemKind.Function);
      completion.detail = `Separan function SEP:${name}`; completion.insertText = new vscode.SnippetString(`${name}($0)`); return completion;
    });
    const builtins = Object.entries(builtinSignatures).map(([name, signature]) => {
      const completion = new vscode.CompletionItem(name, vscode.CompletionItemKind.Function);
      completion.detail = signature; completion.insertText = new vscode.SnippetString(`${name}($0)`); return completion;
    });
    return [...functions, ...builtins];
  }
}

function activeCall(document, position) {
  const text = document.lineAt(position.line).text.slice(0, position.character); let depth = 0;
  for (let index = text.length - 1; index >= 0; index -= 1) {
    if (text[index] === ")") depth += 1;
    else if (text[index] === "(") {
      if (depth) { depth -= 1; continue; }
      const before = text.slice(0, index); const found = /((?:[\p{L}_][\p{L}\p{M}\p{N}_]*\.)?[\p{L}_][\p{L}\p{M}\p{N}_]*)\s*$/u.exec(before);
      if (!found) return undefined;
      const argumentsText = text.slice(index + 1); let commas = 0; let nested = 0; let quotedText = false; let escaped = false;
      for (const char of argumentsText) {
        if (quotedText) { if (escaped) escaped = false; else if (char === "\\") escaped = true; else if (char === '"') quotedText = false; }
        else if (char === '"') quotedText = true; else if (char === "(") nested += 1; else if (char === ")") nested -= 1; else if (char === "," && nested === 0) commas += 1;
      }
      return { name: found[1], activeParameter: commas };
    }
  }
  return undefined;
}

class SeparanSignatureHelpProvider {
  async provideSignatureHelp(document, position) {
    const call = activeCall(document, position); if (!call) return undefined;
    const qualified = /^([^.]+)\.(.+)$/u.exec(call.name); let local;
    if (qualified) {
      const target = await importedDocument(document, qualified[1]);
      local = target && flattenStructures(documentStructure(target.getText()).roots).find((item) => item.kind === "SEP" && item.label === qualified[2]);
    } else local = flattenStructures(documentStructure(document.getText()).roots).find((item) => item.kind === "SEP" && item.label === call.name);
    const label = local ? `${call.name}(${local.parameters.join(", ")})` : builtinSignatures[call.name];
    if (!label) return undefined;
    const signature = new vscode.SignatureInformation(label);
    const parameterText = label.slice(label.indexOf("(") + 1, label.lastIndexOf(")"));
    signature.parameters = parameterText ? parameterText.split(",").map((value) => new vscode.ParameterInformation(value.trim())) : [];
    const help = new vscode.SignatureHelp(); help.signatures = [signature]; help.activeSignature = 0;
    help.activeParameter = Math.min(call.activeParameter, Math.max(0, signature.parameters.length - 1)); return help;
  }
}

class SeparanWorkspaceSymbolProvider {
  async provideWorkspaceSymbols(query) {
    const symbols = []; const files = await vscode.workspace.findFiles("**/*.sep", "**/{.git,node_modules,build,dist}/**", 2000);
    for (const uri of files) {
      const document = await vscode.workspace.openTextDocument(uri);
      for (const item of flattenStructures(documentStructure(document.getText()).roots)) {
        if (query && !item.label.toLocaleLowerCase().includes(query.toLocaleLowerCase())) continue;
        const kind = item.kind === "SEP" ? vscode.SymbolKind.Function : item.kind === "object" ? vscode.SymbolKind.Object : vscode.SymbolKind.Namespace;
        symbols.push(new vscode.SymbolInformation(`${item.kind}:${item.label}`, kind, item.path,
          new vscode.Location(uri, new vscode.Position(item.start_line - 1, item.start_column - 1))));
      }
    }
    return symbols;
  }
}

function splitTopLevelValues(source) {
  const values = []; let start = 0; let depth = 0; let quoted = false; let escaped = false;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quoted) { if (escaped) escaped = false; else if (character === "\\") escaped = true; else if (character === '"') quoted = false; }
    else if (character === '"') quoted = true;
    else if ("([{".includes(character)) depth += 1;
    else if (")]}".includes(character)) depth -= 1;
    else if (character === "," && depth === 0) { values.push(source.slice(start, index).trim()); start = index + 1; }
  }
  values.push(source.slice(start).trim()); return values.filter(Boolean);
}

function callsOnLine(source) {
  const identifier = "[\\p{L}_][\\p{L}\\p{M}\\p{N}_]*";
  const calls = []; const pattern = new RegExp("(" + identifier + "(?:\\." + identifier + ")?)\\s*\\(", "gu");
  for (const match of source.matchAll(pattern)) {
    const open = source.indexOf("(", match.index); let depth = 1; let quoted = false; let escaped = false; let close = -1;
    for (let index = open + 1; index < source.length; index += 1) {
      const character = source[index];
      if (quoted) { if (escaped) escaped = false; else if (character === "\\") escaped = true; else if (character === '"') quoted = false; }
      else if (character === '"') quoted = true;
      else if (character === "(") depth += 1;
      else if (character === ")" && --depth === 0) { close = index; break; }
    }
    if (close >= 0) calls.push({ name: match[1], start: match.index, arguments: splitTopLevelValues(source.slice(open + 1, close)) });
  }
  return calls;
}

function inferredExpressionType(expression, customReturns = new Map(), variables = new Map()) {
  const value = expression.trim();
  if (/^-?(?:\d+(?:\.\d+)?|\.\d+)$/u.test(value)) return "number";
  if (/^(?:true|false)$/u.test(value)) return "boolean";
  if (/^"(?:[^"\\]|\\.)*"$/u.test(value)) return "string";
  if (/^\[.*\]$/su.test(value)) {
    const members = splitTopLevelValues(value.slice(1, -1)).map((member) => inferredExpressionType(member, customReturns, variables));
    if (!members.length) return "list";
    return members.every((member) => member && member === members[0]) ? "list<" + members[0] + ">" : "list";
  }
  if (/^\{/u.test(value)) return "object";
  if (/^EMPTY$/u.test(value)) return "EMPTY";
  if (/^EMPTYS$/u.test(value)) return "list";
  if (/^(?:.+)\s+(?:==|!=|<|<=|>|>=|is(?:\s+not)?)\s+(?:.+)$/u.test(value)) return "boolean";
  const call = /^((?:[\p{L}_][\p{L}\p{M}\p{N}_]*\.)?[\p{L}_][\p{L}\p{M}\p{N}_]*)\s*\(/u.exec(value);
  if (call) return builtinReturnTypes[call[1]] || customReturns.get(call[1]);
  const identifier = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)$/u.exec(value);
  if (identifier) return variables.get(identifier[1]);
  const member = /^([\p{L}_][\p{L}\p{M}\p{N}_]*\.[\p{L}_][\p{L}\p{M}\p{N}_]*)$/u.exec(value);
  if (member) return variables.get(member[1]);
  const arithmetic = /^(.+?)\s*(?:\+|-|\*|\/|%)\s*(.+)$/u.exec(value);
  if (arithmetic) {
    const left = inferredExpressionType(arithmetic[1], customReturns, variables);
    const right = inferredExpressionType(arithmetic[2], customReturns, variables);
    if (left === "number" && right === "number") return "number";
    if (left === "string" && right === "string" && value.includes("+")) return "string";
  }
  return undefined;
}

function inferredFunctionReturns(document) {
  const result = new Map(); const functions = flattenStructures(documentStructure(document.getText()).roots).filter((entry) => entry.kind === "SEP");
  for (let pass = 0; pass < functions.length + 1; pass += 1) {
    let changed = false;
    for (const item of functions) {
      const variables = new Map();
      for (const parameter of item.parameters) {
        const typed = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*:\s*(.+)$/u.exec(parameter);
        if (typed) variables.set(typed[1], typed[2].trim());
      }
      for (const line of item.source.split(/\r?\n/u)) {
        const typedAssignment = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(codeText(line));
        if (typedAssignment) { variables.set(typedAssignment[2], typedAssignment[1]); continue; }
        const assignment = /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(codeText(line));
        if (assignment) {
          const type = inferredExpressionType(assignment[2], result, variables);
          if (type) variables.set(assignment[1], type);
        }
      }
      const expressions = [...item.source.matchAll(/^\s*return\s+(.+)$/gmu)].map((match) => codeText(match[1]));
      const returns = expressions.map((expression) => inferredExpressionType(expression, result, variables));
      if (returns.length && returns.every((value) => value && value === returns[0]) && result.get(item.label) !== returns[0]) {
        result.set(item.label, returns[0]); changed = true;
      }
    }
    if (!changed) break;
  }
  return result;
}

class SeparanInlayHintsProvider {
  async provideInlayHints(document, range) {
    if (!vscode.workspace.getConfiguration("separan", document.uri).get("inlayHints.types", true)) return [];
    const hints = []; const customReturns = inferredFunctionReturns(document); let variables = new Map();
    for (const structure of flattenStructures(documentStructure(document.getText()).roots).filter((item) => item.kind === "object")) {
      variables.set(structure.label, "object");
      for (const line of structure.source.split(/\r?\n/u)) {
        const typed = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(codeText(line));
        const assignment = typed || /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(codeText(line));
        if (assignment) variables.set(structure.label + "." + (typed ? typed[2] : assignment[1]),
          typed ? typed[1] : inferredExpressionType(assignment[2], customReturns, variables));
      }
    }
    const objectTypes = new Map(variables);
    for (const alias of importAliases(document).keys()) {
      const imported = await importedDocument(document, alias); if (imported) for (const [name, type] of inferredFunctionReturns(imported)) customReturns.set(`${alias}.${name}`, type);
    }
    for (let line = range.start.line; line <= Math.min(range.end.line, document.lineCount - 1); line += 1) {
      const text = codeText(document.lineAt(line).text);
      const functionStart = /^\s*SEP:[^\s:()]+\s*(?:\(([^)]*)\))?/u.exec(text);
      if (functionStart) {
        variables = new Map(objectTypes);
        for (const parameter of splitTopLevelValues(functionStart[1] || "")) {
          const typed = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*:\s*(.+)$/u.exec(parameter);
          if (typed) variables.set(typed[1], typed[2].trim());
        }
        continue;
      }
      const typedAssignment = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
      if (typedAssignment) { variables.set(typedAssignment[2], typedAssignment[1]); continue; }
      const loop = /^\s*for\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s+in\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\b/u.exec(text);
      if (loop) {
        const collection = variables.get(loop[2]); const element = collection && /^list<(.+)>$/u.exec(collection);
        if (element) variables.set(loop[1], element[1]);
        continue;
      }
      const assignment = /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
      if (!assignment) continue;
      let expression = assignment[2].trim(); const qualified = /^([\p{L}_][\p{L}\p{M}\p{N}_]*\.[\p{L}_][\p{L}\p{M}\p{N}_]*)\s*\(/u.exec(expression);
      const type = qualified ? customReturns.get(qualified[1]) : inferredExpressionType(expression, customReturns, variables); if (!type) continue;
      variables.set(assignment[1], type);
      const column = text.indexOf(assignment[1]) + assignment[1].length;
      const hint = new vscode.InlayHint(new vscode.Position(line, column), `: ${type}`, vscode.InlayHintKind.Type);
      hint.paddingLeft = true; hints.push(hint);
    }
    return hints;
  }
}

function functionItem(document, structure) {
  const start = new vscode.Position(structure.start_line - 1, structure.start_column - 1);
  const endLine = Math.min(document.lineCount - 1, structure.end_line - 1);
  return new vscode.CallHierarchyItem(vscode.SymbolKind.Function, structure.label, structure.path, document.uri,
    new vscode.Range(new vscode.Position(structure.start_line - 1, 0), new vscode.Position(endLine, document.lineAt(endLine).text.length)),
    new vscode.Range(start, start.translate(0, structure.label.length)));
}

function callRanges(document, structure, name) {
  const ranges = []; const escaped = name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"); const pattern = new RegExp(`\\b${escaped}\\s*(?=\\()`, "gu");
  for (let line = structure.start_line - 1; line < Math.min(document.lineCount, structure.end_line); line += 1)
    for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) ranges.push(new vscode.Range(line, match.index, line, match.index + name.length));
  return ranges;
}

function qualifiedCallRanges(document, structure, alias, name) {
  const ranges = []; const escapedAlias = alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const escapedName = name.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
  const pattern = new RegExp("\\b" + escapedAlias + "\\." + escapedName + "\\s*(?=\\()", "gu");
  for (let line = structure.start_line - 1; line < Math.min(document.lineCount, structure.end_line); line += 1)
    for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
      const start = match.index + alias.length + 1;
      ranges.push(new vscode.Range(line, start, line, start + name.length));
    }
  return ranges;
}

class SeparanCallHierarchyProvider {
  async prepareCallHierarchy(document, position) {
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const targetDocument = await importedDocument(document, qualified.alias);
      const target = targetDocument && flattenStructures(documentStructure(targetDocument.getText()).roots)
        .find((item) => item.kind === "SEP" && item.label === qualified.name);
      if (target) return functionItem(targetDocument, target);
    }
    const identifier = identifierAtPosition(document, position); const label = labelAtPosition(document, position); const name = label ? label.name : identifier && identifier.name;
    const structure = name && flattenStructures(documentStructure(document.getText()).roots).find((item) => item.kind === "SEP" && item.label === name);
    return structure ? functionItem(document, structure) : undefined;
  }
  async provideCallHierarchyIncomingCalls(item) {
    const sourceDocument = await vscode.workspace.openTextDocument(item.uri); const workspaceDocuments = await workspaceSeparanDocuments();
    const documents = new Map([[sourceDocument.uri.toString(), sourceDocument], ...workspaceDocuments.map((document) => [document.uri.toString(), document])]);
    const result = []; for (const document of documents.values()) {
      for (const structure of flattenStructures(documentStructure(document.getText()).roots).filter((entry) => entry.kind === "SEP")) {
        const ranges = document.uri.toString() === item.uri.toString() ? callRanges(document, structure, item.name) : [];
        for (const alias of importAliases(document).keys()) {
          const target = importedUri(document, alias);
          if (target && target.fsPath.toLocaleLowerCase() === item.uri.fsPath.toLocaleLowerCase())
            ranges.push(...qualifiedCallRanges(document, structure, alias, item.name));
        }
        if (ranges.length) result.push(new vscode.CallHierarchyIncomingCall(functionItem(document, structure), ranges));
      }
    }
    return result;
  }
  async provideCallHierarchyOutgoingCalls(item) {
    const document = await vscode.workspace.openTextDocument(item.uri);
    const source = flattenStructures(documentStructure(document.getText()).roots).find((entry) => entry.kind === "SEP" && entry.label === item.name);
    if (!source) return [];
    const definitions = new Map();
    for (const structure of flattenStructures(documentStructure(document.getText()).roots))
      if (structure.kind === "SEP") definitions.set(structure.label, structure);
    const result = [];
    for (const called of source.calls) {
      const target = definitions.get(called); if (target) result.push(new vscode.CallHierarchyOutgoingCall(functionItem(document, target), callRanges(document, source, called)));
    }
    for (const alias of importAliases(document).keys()) {
      const targetDocument = await importedDocument(document, alias); if (!targetDocument) continue;
      for (const target of flattenStructures(documentStructure(targetDocument.getText()).roots).filter((entry) => entry.kind === "SEP")) {
        const ranges = qualifiedCallRanges(document, source, alias, target.label);
        if (ranges.length) result.push(new vscode.CallHierarchyOutgoingCall(functionItem(targetDocument, target), ranges));
      }
    }
    return result;
  }
}

class SeparanCodeLensProvider {
  async provideCodeLenses(document) {
    const lenses = []; const structures = flattenStructures(documentStructure(document.getText()).roots).filter((item) => item.kind === "SEP");
    const workspaceDocuments = await workspaceSeparanDocuments();
    const documents = new Map([[document.uri.toString(), document], ...workspaceDocuments.map((candidate) => [candidate.uri.toString(), candidate])]);
    for (const structure of structures) {
      const range = new vscode.Range(structure.start_line - 1, 0, structure.start_line - 1, 0);
      let references = 0;
      for (const candidate of documents.values()) references += functionLocations(candidate, structure.label).filter((location) => !(location.uri.toString() === document.uri.toString() && location.range.start.line === structure.start_line - 1)).length;
      lenses.push(new vscode.CodeLens(range, { title: `${references} reference${references === 1 ? "" : "s"}`, command: "editor.action.showReferences",
        arguments: [document.uri, new vscode.Position(structure.start_line - 1, structure.start_column - 1), await new SeparanReferenceProvider().provideReferences(document, new vscode.Position(structure.start_line - 1, structure.start_column - 1))] }));
      if (structure.parameters.length === 0 && structure.label !== "main") lenses.push(new vscode.CodeLens(range, { title: "$(play) Run Function", command: "separan.runFunction", arguments: [document.uri, structure.label] }));
      if (structure.parameters.length === 0 && structure.label.startsWith("test_")) lenses.push(new vscode.CodeLens(range, { title: "$(beaker) Run Test", command: "separan.runFunction", arguments: [document.uri, structure.label] }));
    }
    return lenses;
  }
}

class SeparanHoverProvider {
  async provideHover(document, position) {
    const label = labelAtPosition(document, position);
    if (label) {
      const item = flattenStructures(documentStructure(document.getText()).roots).find((entry) => entry.label === label.name);
      if (!item) return undefined;
      return new vscode.Hover(new vscode.MarkdownString(`**${item.kind}:${item.label}**  \nPath: \`${item.path}\`  \nLines ${item.start_line}–${item.end_line}`), label.range);
    }
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const target = await importedDocument(document, qualified.alias); const importedDefinition = target && functionDefinitions(target).get(qualified.name);
      if (importedDefinition) return new vscode.Hover("Imported function " + qualified.alias + "." + qualified.name + " in " + path.basename(target.uri.fsPath));
    }
    const identifier = identifierAtPosition(document, position); const definition = identifier && functionDefinitions(document).get(identifier.name);
    return definition ? new vscode.Hover(new vscode.MarkdownString(`**Function** \`SEP:${identifier.name}\`  \nDefined on line ${definition.range.start.line + 1}`), identifier.range) : undefined;
  }
}

class SeparanDefinitionProvider {
  async provideDefinition(document, position) {
    const imported = importAtPosition(document, position);
    if (imported) {
      const uri = importedUri(document, imported.alias);
      if (uri) try {
        await vscode.workspace.fs.stat(uri);
        return new vscode.Location(uri, new vscode.Position(0, 0));
      } catch (_) { return undefined; }
    }
    const label = labelAtPosition(document, position);
    if (label) return allLabelLocations(document, label.name)[0];
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) { const target = await importedDocument(document, qualified.alias); return target && functionDefinitions(target).get(qualified.name); }
    const identifier = identifierAtPosition(document, position); if (!identifier) return undefined;
    const local = functionDefinitions(document).get(identifier.name); if (local) return local;
    for (const candidate of await workspaceSeparanDocuments()) {
      const found = functionDefinitions(candidate).get(identifier.name); if (found) return found;
    }
    return undefined;
  }
}

class SeparanReferenceProvider {
  async provideReferences(document, position) {
    const label = labelAtPosition(document, position);
    if (label) return allLabelLocations(document, label.name);
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const target = await importedDocument(document, qualified.alias);
      return target ? importedFunctionLocations(target, qualified.name, document) : [];
    }
    const identifier = identifierAtPosition(document, position); if (!identifier) return [];
    const documents = await workspaceSeparanDocuments();
    if (![document, ...documents].some((candidate) => functionDefinitions(candidate).has(identifier.name))) return [];
    const uniqueDocuments = new Map([[document.uri.toString(), document], ...documents.map((candidate) => [candidate.uri.toString(), candidate])]);
    return [...uniqueDocuments.values()].flatMap((candidate) => functionLocations(candidate, identifier.name));
  }
}

class SeparanRenameProvider {
  async prepareRename(document, position) {
    const tag = tagAtPosition(document, position); if (tag) return { range: tag.range, placeholder: tag.name };
    const label = labelAtPosition(document, position); if (label) return { range: label.range, placeholder: label.name };
    const qualified = qualifiedIdentifierAt(document, position);
    if (qualified) {
      const target = await importedDocument(document, qualified.alias);
      if (target && functionDefinitions(target).has(qualified.name)) {
        const identifier = identifierAtPosition(document, position);
        return { range: identifier.range, placeholder: qualified.name };
      }
    }
    const identifier = identifierAtPosition(document, position);
    if (identifier) {
      if (functionDefinitions(document).has(identifier.name)) return { range: identifier.range, placeholder: identifier.name };
      for (const candidate of await workspaceSeparanDocuments()) if (functionDefinitions(candidate).has(identifier.name)) return { range: identifier.range, placeholder: identifier.name };
    }
    throw new Error("Place the cursor on a Separan label or function.");
  }
  async provideRenameEdits(document, position, newName) {
    if (!/^[\p{L}_][\p{L}\p{M}\p{N}_]*$/u.test(newName)) throw new Error("Separan labels must be valid identifiers.");
    const tag = tagAtPosition(document, position); const label = labelAtPosition(document, position);
    const qualified = qualifiedIdentifierAt(document, position); const identifier = identifierAtPosition(document, position); let locations = [];
    if (tag) {
      const documents = await workspaceSeparanDocuments();
      const uniqueDocuments = new Map([[document.uri.toString(), document], ...documents.map((candidate) => [candidate.uri.toString(), candidate])]);
      for (const candidate of uniqueDocuments.values()) locations.push(...tagLocations(candidate, tag.name));
    }
    else if (label) locations = allLabelLocations(document, label.name);
    else if (qualified) {
      const target = await importedDocument(document, qualified.alias);
      if (target && functionDefinitions(target).has(qualified.name)) locations = await importedFunctionLocations(target, qualified.name, document);
    }
    else if (identifier) {
      const documents = await workspaceSeparanDocuments();
      if ([document, ...documents].some((candidate) => functionDefinitions(candidate).has(identifier.name))) {
        const uniqueDocuments = new Map([[document.uri.toString(), document], ...documents.map((candidate) => [candidate.uri.toString(), candidate])]);
        locations = [...uniqueDocuments.values()].flatMap((candidate) => functionLocations(candidate, identifier.name));
      }
    }
    if (!locations.length) return undefined;
    const edit = new vscode.WorkspaceEdit(); for (const location of locations) edit.replace(location.uri, location.range, newName); return edit;
  }
}

class SeparanDocumentSymbolProvider {
  provideDocumentSymbols(document) {
    const convert = (item) => {
      const kind = item.kind === "SEP" ? vscode.SymbolKind.Function : item.kind === "object" ? vscode.SymbolKind.Object : item.kind === "list" ? vscode.SymbolKind.Array : vscode.SymbolKind.Namespace;
      const start = new vscode.Position(item.start_line - 1, 0); const endLine = Math.min(document.lineCount - 1, item.end_line - 1);
      const symbol = new vscode.DocumentSymbol(`${item.kind}:${item.label}`, item.path, kind,
        new vscode.Range(start, new vscode.Position(endLine, document.lineAt(endLine).text.length)),
        new vscode.Range(start, new vscode.Position(item.start_line - 1, document.lineAt(item.start_line - 1).text.length)));
      symbol.children = (item.children || []).map(convert); return symbol;
    };
    return documentStructure(document.getText()).roots.map(convert);
  }
}

function formatSource(source, indentation = "    ") {
  const result = []; let depth = 0; let commentLabel;
  const open = /^(?:SEP|if|while|for|object|list|try|error|http_route|transaction)\b.*:[^\s:()]+(?:\([^)]*\))?\s*$/u;
  const close = /^(?:END_SEP|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):[^\s:()]+\s*$/u;
  const branch = /^(?:elseif\b|else:|catch\b|finally:)/u;
  const trailingNewline = source.endsWith("\n") || source.endsWith("\r");
  for (const raw of source.split(/\r?\n/u)) {
    const stripped = raw.trim();
    if (!stripped) { result.push(""); continue; }
    const delimiter = multilineCommentDelimiter(stripped);
    if (delimiter !== undefined) {
      result.push(indentation.repeat(depth) + stripped);
      commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel);
      continue;
    }
    if (commentLabel !== undefined) { result.push(indentation.repeat(depth) + stripped); continue; }
    const code = codeText(stripped);
    if (close.test(code) || branch.test(code)) depth = Math.max(0, depth - 1);
    result.push(indentation.repeat(depth) + stripped);
    if (open.test(code) || branch.test(code)) depth += 1;
  }
  if (trailingNewline && result[result.length - 1] === "") result.pop();
  return result.join("\n") + (trailingNewline ? "\n" : "");
}

class SeparanFormattingProvider {
  provideDocumentFormattingEdits(document, options) {
    const indentation = options.insertSpaces ? " ".repeat(options.tabSize) : "\t";
    const formatted = formatSource(document.getText(), indentation); if (formatted === document.getText()) return [];
    const end = document.lineAt(document.lineCount - 1).rangeIncludingLineBreak.end;
    return [vscode.TextEdit.replace(new vscode.Range(new vscode.Position(0, 0), end), formatted)];
  }
}

async function goToMatchingLabel() {
  const editor = currentEditor(); if (!editor) return;
  const label = labelAt(editor); if (!label) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  const stack = []; const completed = [];
  const openPattern = /^\s*(SEP|sep|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(END_SEP|end_sep|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  const closerKinds = { endif: "if", endwhile: "while", endfor: "for", end_object: "object", end_list: "list", endtry: "try", end_error: "error", end_http_route: "http_route", end_transaction: "transaction" };
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
  const pattern = /^\s*(SEP|sep|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
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

async function runFile() {
  const editor = currentEditor(); if (!editor) return;
  await editor.document.save();
  await executeSeparanTask("Run File", editor.document.uri, [editor.document.uri.fsPath]);
}

async function checkFile() {
  const editor = currentEditor();
  if (!editor) return vscode.window.showInformationMessage("Open a Separan file before checking it.");
  await editor.document.save();
  await executeSeparanTask("Check Current File", editor.document.uri, ["--check", editor.document.uri.fsPath]);
}

async function runFunction(uri, name) {
  if (!uri || !name) {
    const editor = currentEditor(); if (!editor) return vscode.window.showInformationMessage("Open a Separan file and place the cursor inside a function.");
    const scope = await scopeAt(editor); if (!scope || scope.kind !== "SEP") return vscode.window.showInformationMessage("Place the cursor inside a Separan function.");
    uri = editor.document.uri; name = scope.label;
  }
  const document = await vscode.workspace.openTextDocument(uri); if (document.isDirty) await document.save();
  const structures = flattenStructures(documentStructure(document.getText()).roots);
  const target = structures.find((item) => item.kind === "SEP" && item.label === name);
  if (!target) return vscode.window.showErrorMessage(`Function ${name} was not found.`);
  if (target.parameters.length) return vscode.window.showErrorMessage(`Run Function currently requires zero parameters; ${name} has ${target.parameters.length}.`);
  return runFunctionList(document, structures, [name], `Run ${name}`);
}

async function runFunctionList(document, structures, names, title) {
  const uri = document.uri;
  const lines = document.getText().split(/\r?\n/u); const main = structures.find((item) => item.kind === "SEP" && item.label === "main");
  if (main) lines.splice(main.start_line - 1, main.end_line - main.start_line + 1);
  lines.push("", "SEP:main", ...names.map((functionName) => `${functionName}()`), "END_SEP:main", "");
  const temporary = path.join(path.dirname(uri.fsPath), `.separan-vscode-run-${process.pid}-${Date.now()}.sep`);
  await fs.promises.writeFile(temporary, lines.join("\n"), "utf8");
  try {
    const execution = await executeSeparanTask(title, uri, [temporary]);
    temporaryRuns.set(execution, temporary);
  } catch (error) {
    await fs.promises.rm(temporary, { force: true }); throw error;
  }
}

async function runTests() {
  const editor = currentEditor(); if (!editor) return vscode.window.showInformationMessage("Open a Separan file containing test_ functions.");
  if (editor.document.isDirty) await editor.document.save();
  const structures = flattenStructures(documentStructure(editor.document.getText()).roots);
  const tests = structures.filter((item) => item.kind === "SEP" && item.label.startsWith("test_") && item.parameters.length === 0).map((item) => item.label);
  if (!tests.length) return vscode.window.showInformationMessage("No zero-argument test_ functions were found in the active file.");
  return runFunctionList(editor.document, structures, tests, `Run ${tests.length} Separan Tests`);
}

async function diagnoseRuntime() {
  const editor = currentEditor();
  const resource = editor && editor.document.uri;
  const config = runtimeConfiguration(resource);
  runtimeOutput.clear();
  runtimeOutput.appendLine(`Executable: ${config.executable}`);
  runtimeOutput.appendLine(`Workspace: ${resource && vscode.workspace.getWorkspaceFolder(resource) ? vscode.workspace.getWorkspaceFolder(resource).uri.fsPath : "(none)"}`);
  try {
    const folder = resource ? vscode.workspace.getWorkspaceFolder(resource) : undefined;
    const result = await execFileAsync(config.executable, [...config.arguments, "--help"], {
      cwd: folder ? folder.uri.fsPath : undefined,
      env: { ...process.env, ...config.environment },
      encoding: "utf8",
      windowsHide: true,
    });
    runtimeOutput.appendLine("");
    runtimeOutput.append(result.stdout.trimEnd());
    if (result.stderr) runtimeOutput.appendLine(`\n${result.stderr.trimEnd()}`);
    runtimeOutput.show(true);
    vscode.window.showInformationMessage("Separan native runtime is available.");
  } catch (error) {
    runtimeOutput.appendLine("");
    runtimeOutput.appendLine(error.stderr || error.message);
    runtimeOutput.show(true);
    vscode.window.showErrorMessage("Separan runtime could not be started. See the Separan Runtime output.");
  }
}

async function copyAiScope() {
  const editor = currentEditor(); if (!editor) return;
  const scope = await scopeAt(editor);
  if (!scope) return vscode.window.showInformationMessage("Place the cursor on a Separan label.");
  await vscode.env.clipboard.writeText(`Modify only Separan scope ${scope.path}`);
  vscode.window.showInformationMessage(`Copied AI edit scope ${scope.path}`);
}

function documentStructure(source) {
  const roots = []; const stack = []; const diagnostics = []; let commentLabel;
  const lines = source.split(/\r?\n/u);
  const openPattern = /^\s*(SEP|if|while|for|object|list|try|error|http_route|transaction)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u;
  const closePattern = /^\s*(END_SEP|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):([^\s:()]+)\s*$/u;
  const closerKinds = { END_SEP: "SEP", endif: "if", endwhile: "while", endfor: "for", end_object: "object", end_list: "list", endtry: "try", end_error: "error", end_http_route: "http_route", end_transaction: "transaction" };
  for (let line = 0; line < lines.length; line += 1) {
    const delimiter = multilineCommentDelimiter(lines[line]);
    if (delimiter !== undefined) { commentLabel = commentLabel === delimiter ? undefined : (commentLabel === undefined ? delimiter : commentLabel); continue; }
    if (commentLabel !== undefined) continue;
    const text = codeText(lines[line]); const opened = openPattern.exec(text); const closed = closePattern.exec(text);
    if (opened) {
      const parent = stack[stack.length - 1];
      const pathName = parent ? `${parent.path}/${opened[2]}` : opened[2];
      const node = { id: `${opened[1]}:${pathName}:${line + 1}`, kind: opened[1], label: opened[2], path: pathName,
        start_line: line + 1, start_column: Math.max(1, lines[line].indexOf(`:${opened[2]}`) + 2), end_line: line + 1,
        tags: [], parameters: [], reads: [], writes: [], calls: [], children: [], source: "" };
      if (opened[1] === "SEP") {
        const parameters = new RegExp(`^\\s*SEP:${opened[2].replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}\\s*\\(([^)]*)\\)`, "u").exec(text);
        if (parameters && parameters[1].trim()) node.parameters = parameters[1].split(",").map((value) => value.trim()).filter(Boolean);
      }
      if (parent) parent.children.push(node); else roots.push(node);
      stack.push(node);
    } else if (closed) {
      const expectedKind = closerKinds[closed[1]]; const top = stack[stack.length - 1];
      if (!top) diagnostics.push({ line, column: Math.max(0, lines[line].indexOf(closed[0].trim())), message: `Unexpected closing label :${closed[2]}.` });
      else if (top.kind !== expectedKind || top.label !== closed[2]) diagnostics.push({ line, column: Math.max(0, lines[line].indexOf(`:${closed[2]}`)), message: `Expected ${blockPairs[top.kind]}:${top.label}.` });
      else {
        const node = stack.pop(); node.end_line = line + 1; node.source = lines.slice(node.start_line - 1, line + 1).join("\n");
        const callPattern = /\b([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*(?=\()/gu;
        node.calls = [...new Set([...node.source.matchAll(callPattern)].map((match) => match[1]).filter((name) => name !== node.label))];
      }
    } else if (/^\s*@[^\s]+\s*$/u.test(text) && stack.length) stack[stack.length - 1].tags.push(text.trim().slice(1));
  }
  for (const node of stack) {
    node.end_line = lines.length; node.source = lines.slice(node.start_line - 1).join("\n");
    const callPattern = /\b([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*(?=\()/gu;
    node.calls = [...new Set([...node.source.matchAll(callPattern)].map((match) => match[1]).filter((name) => name !== node.label))];
    diagnostics.push({ line: node.start_line - 1, column: node.start_column - 1, message: `Missing ${blockPairs[node.kind]}:${node.label}.` });
  }
  return { roots, diagnostics };
}

function publishStructureDiagnostics(document) {
  if (document.languageId !== "separan") return;
  const report = documentStructure(document.getText());
  const items = report.diagnostics.map((item) => {
    const line = Math.min(item.line, Math.max(0, document.lineCount - 1));
    const start = new vscode.Position(line, Math.min(item.column, document.lineAt(line).text.length));
    const end = new vscode.Position(line, Math.min(document.lineAt(line).text.length, start.character + 1));
    const diagnostic = new vscode.Diagnostic(new vscode.Range(start, end), item.message, vscode.DiagnosticSeverity.Error);
    diagnostic.source = "Separan Structure"; diagnostic.code = "structure"; return diagnostic;
  });
  structureDiagnostics.set(document.uri, items);
}

async function publishNativeDiagnostics(document) {
  if (document.languageId !== "separan" || document.isDirty || document.uri.scheme !== "file") return;
  const version = document.version; diagnosticVersions.set(document.uri.toString(), version);
  const config = runtimeConfiguration(document.uri); const folder = vscode.workspace.getWorkspaceFolder(document.uri);
  try {
    await execFileAsync(config.executable, [...config.arguments, "--check", document.uri.fsPath], {
      cwd: folder ? folder.uri.fsPath : undefined, env: { ...process.env, ...config.environment }, encoding: "utf8", windowsHide: true,
    });
    if (diagnosticVersions.get(document.uri.toString()) === version) nativeDiagnostics.delete(document.uri);
  } catch (error) {
    if (diagnosticVersions.get(document.uri.toString()) !== version) return;
    const output = `${error.stderr || ""}\n${error.stdout || ""}`; const items = [];
    const pattern = /SEPARAN\s+(E\d+):\s*(.*?)\s+at line\s+(\d+),\s*column\s+(\d+)/gu;
    for (const match of output.matchAll(pattern)) {
      const line = Math.max(0, Math.min(document.lineCount - 1, Number(match[3]) - 1));
      const column = Math.max(0, Math.min(document.lineAt(line).text.length, Number(match[4]) - 1));
      const start = new vscode.Position(line, column);
      const end = new vscode.Position(line, Math.min(document.lineAt(line).text.length, column + 1));
      const diagnostic = new vscode.Diagnostic(new vscode.Range(start, end), match[2], vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Native"; diagnostic.code = match[1]; items.push(diagnostic);
    }
    if (!items.length) {
      const start = new vscode.Position(0, 0); const message = output.trim() || error.message;
      const diagnostic = new vscode.Diagnostic(new vscode.Range(start, start), message, vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Native"; items.push(diagnostic);
    }
    nativeDiagnostics.set(document.uri, items);
  }
}

async function publishAnalysisDiagnostics(document) {
  if (document.languageId !== "separan" || document.uri.scheme !== "file") return;
  const version = document.version; const items = []; const declarations = importDeclarations(document); const seen = new Map();
  const customReturns = inferredFunctionReturns(document);
  const customFunctions = new Map();
  for (const structure of flattenStructures(documentStructure(document.getText()).roots).filter((item) => item.kind === "SEP"))
    customFunctions.set(structure.label, structure.parameters);
  for (const declaration of declarations) {
    if (seen.has(declaration.alias)) {
      const diagnostic = new vscode.Diagnostic(declaration.aliasRange, "Duplicate import alias '" + declaration.alias + "'.", vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "duplicate-import-alias"; items.push(diagnostic);
      continue;
    }
    seen.set(declaration.alias, declaration);
    const uri = moduleUri(document, declaration.path);
    try {
      await vscode.workspace.fs.stat(uri);
      const target = await vscode.workspace.openTextDocument(uri); const definitions = functionDefinitions(target);
      if (await importReaches(target, document.uri)) {
        const diagnostic = new vscode.Diagnostic(declaration.pathRange, "Import creates a cycle through '" + declaration.path + "'.", vscode.DiagnosticSeverity.Error);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "cyclic-import"; items.push(diagnostic);
      }
      for (const [name, type] of inferredFunctionReturns(target)) customReturns.set(declaration.alias + "." + name, type);
      for (const structure of flattenStructures(documentStructure(target.getText()).roots).filter((item) => item.kind === "SEP"))
        customFunctions.set(declaration.alias + "." + structure.label, structure.parameters);
      const escaped = declaration.alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
      const pattern = new RegExp("\\b" + escaped + "\\.([\\p{L}_][\\p{L}\\p{M}\\p{N}_]*)\\s*(?=\\()", "gu");
      for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
        if (definitions.has(match[1])) continue;
        const start = match.index + declaration.alias.length + 1;
        const range = new vscode.Range(line, start, line, start + match[1].length);
        const diagnostic = new vscode.Diagnostic(range, "Module '" + declaration.path + "' has no function '" + match[1] + "'.", vscode.DiagnosticSeverity.Error);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "unknown-import-member"; items.push(diagnostic);
      }
    } catch (_) {
      const diagnostic = new vscode.Diagnostic(declaration.pathRange, "Imported module '" + declaration.path + "' was not found.", vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "missing-import"; items.push(diagnostic);
    }
  }
  for (const declaration of declarations) {
    const escaped = declaration.alias.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&");
    let used = false;
    const pattern = new RegExp("\\b" + escaped + "\\.", "u");
    for (let line = 0; line < document.lineCount && !used; line += 1)
      if (line !== declaration.line && pattern.test(codeText(document.lineAt(line).text))) used = true;
    if (!used) {
      const diagnostic = new vscode.Diagnostic(declaration.aliasRange, "Import alias '" + declaration.alias + "' is never used.", vscode.DiagnosticSeverity.Warning);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "unused-import"; items.push(diagnostic);
    }
  }
  const variables = new Map();
  for (let line = 0; line < document.lineCount; line += 1) {
    const text = codeText(document.lineAt(line).text);
    for (const call of callsOnLine(text)) {
      const metadata = builtinMetadata[call.name]; const parameters = customFunctions.get(call.name);
      if (!metadata && !parameters) {
        if (!call.name.includes(".") && !new RegExp("^\\s*SEP:" + call.name.replace(/[.*+?^{}()|[\]\\$]/gu, "\\$&") + "\\s*\\(", "u").test(text)) {
          const range = new vscode.Range(line, call.start, line, call.start + call.name.length);
          const diagnostic = new vscode.Diagnostic(range, "Function '" + call.name + "' is not defined.", vscode.DiagnosticSeverity.Error);
          diagnostic.source = "Separan Analysis"; diagnostic.code = "undefined-function"; items.push(diagnostic);
        }
        continue;
      }
      const count = call.arguments.length;
      const minimum = metadata ? metadata.minimum : parameters.length; const maximum = metadata ? metadata.maximum : parameters.length;
      const range = new vscode.Range(line, call.start, line, call.start + call.name.length);
      if (count < minimum || count > maximum) {
        const expected = minimum === maximum ? String(minimum) : minimum + "–" + maximum;
        const diagnostic = new vscode.Diagnostic(range, "'" + call.name + "' expects " + expected + " argument(s), but received " + count + ".", vscode.DiagnosticSeverity.Error);
        diagnostic.source = "Separan Analysis"; diagnostic.code = "argument-count"; items.push(diagnostic);
      }
      if (parameters) {
        const names = new Set(parameters.map((parameter) => parameter.split(":", 1)[0].trim()));
        for (const argument of call.arguments) {
          const named = /^([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=/u.exec(argument);
          if (named && !names.has(named[1])) {
            const diagnostic = new vscode.Diagnostic(range, "'" + call.name + "' has no parameter named '" + named[1] + "'.", vscode.DiagnosticSeverity.Error);
            diagnostic.source = "Separan Analysis"; diagnostic.code = "unknown-named-argument"; items.push(diagnostic);
          }
        }
      }
    }
    const typed = /^\s*((?:list<[^>]+>|[\p{L}_][\p{L}\p{M}\p{N}_]*))\s+([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
    const assignment = typed || /^\s*([\p{L}_][\p{L}\p{M}\p{N}_]*)\s*=\s*(.+)$/u.exec(text);
    if (!assignment) continue;
    const name = typed ? typed[2] : assignment[1]; const expression = typed ? typed[3] : assignment[2];
    const actual = inferredExpressionType(expression, customReturns, variables); const expected = typed ? typed[1] : variables.get(name);
    if (actual && actual !== "EMPTY" && expected && expected !== actual && expected !== "value") {
      const start = text.indexOf(name); const range = new vscode.Range(line, start, line, start + name.length);
      const diagnostic = new vscode.Diagnostic(range, "Cannot assign " + actual + " to " + expected + " variable '" + name + "'.", vscode.DiagnosticSeverity.Error);
      diagnostic.source = "Separan Analysis"; diagnostic.code = "type-mismatch"; items.push(diagnostic);
    }
    if (typed) variables.set(name, typed[1]); else if (actual) variables.set(name, actual);
  }
  if (document.version === version) analysisDiagnostics.set(document.uri, items);
}

function refreshDiagnostics(document, runNative = false) {
  if (!document || document.languageId !== "separan") return;
  publishStructureDiagnostics(document);
  void publishAnalysisDiagnostics(document);
  if (runNative) void publishNativeDiagnostics(document);
}

function flattenStructures(roots, result = []) {
  for (const node of roots) { result.push(node); flattenStructures(node.children || [], result); }
  return result;
}

function structuralDiff(before, after) {
  const oldItems = new Map(flattenStructures(documentStructure(before).roots).map((item) => [item.path, item]));
  const newItems = new Map(flattenStructures(documentStructure(after).roots).map((item) => [item.path, item]));
  const changes = [];
  for (const [pathName, item] of newItems) {
    const old = oldItems.get(pathName); const status = !old ? "added" : old.source === item.source ? "unchanged" : "modified";
    changes.push({ id: item.id, path: pathName, status }); oldItems.delete(pathName);
  }
  for (const [pathName, item] of oldItems) changes.push({ id: item.id, path: pathName, status: "removed" });
  const summary = { added: 0, removed: 0, modified: 0, unchanged: 0 };
  for (const item of changes) summary[item.status] += 1;
  return { changes, summary };
}

async function scopeAt(editor) {
  const line = editor.selection.active.line + 1;
  return flattenStructures(documentStructure(editor.document.getText()).roots)
    .filter((item) => item.start_line <= line && line <= item.end_line)
    .sort((a, b) => b.start_line - a.start_line)[0];
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
  SEP: "symbol-namespace", if: "symbol-boolean", while: "sync", for: "list-ordered",
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
    const label = this.data.kind === "SEP" ? `SEP:${this.data.label}` : `:${this.data.label}`;
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

class SemanticTagItem {
  constructor(name, locations, provider) { this.name = name; this.locations = locations; this.provider = provider; }
  treeItem() {
    const item = new vscode.TreeItem(`@${this.name}`, vscode.TreeItemCollapsibleState.Collapsed);
    item.description = `${this.locations.length} location${this.locations.length === 1 ? "" : "s"}`;
    item.iconPath = new vscode.ThemeIcon("tag"); item.contextValue = "separanSemanticTag"; return item;
  }
}

class SemanticTagLocationItem {
  constructor(tag, location) { this.tag = tag; this.location = location; }
  treeItem() {
    const folder = vscode.workspace.getWorkspaceFolder(this.location.uri); const relative = folder ? path.relative(folder.uri.fsPath, this.location.uri.fsPath) : this.location.uri.fsPath;
    const item = new vscode.TreeItem(`${relative}:${this.location.range.start.line + 1}`, vscode.TreeItemCollapsibleState.None);
    item.iconPath = new vscode.ThemeIcon("go-to-file"); item.contextValue = "separanSemanticTagLocation";
    item.command = { command: "separan.revealLocation", title: "Reveal Semantic Tag", arguments: [this.location] }; return item;
  }
}

class SemanticTagProvider {
  constructor() { this.emitter = new vscode.EventEmitter(); this.onDidChangeTreeData = this.emitter.event; this.tags = undefined; }
  refresh() { this.tags = undefined; this.emitter.fire(undefined); }
  getTreeItem(element) { return element.treeItem(); }
  async getChildren(element) {
    if (element instanceof SemanticTagItem) return element.locations.map((location) => new SemanticTagLocationItem(element.name, location));
    if (element) return [];
    if (!this.tags) {
      const tags = new Map();
      for (const document of await workspaceSeparanDocuments()) {
        const pattern = /@([\p{L}_][\p{L}\p{M}\p{N}_]*)/gu;
        for (let line = 0; line < document.lineCount; line += 1) for (const match of codeText(document.lineAt(line).text).matchAll(pattern)) {
          const location = new vscode.Location(document.uri, new vscode.Range(line, match.index + 1, line, match.index + 1 + match[1].length));
          if (!tags.has(match[1])) tags.set(match[1], []); tags.get(match[1]).push(location);
        }
      }
      this.tags = [...tags.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, locations]) => new SemanticTagItem(name, locations, this));
    }
    return this.tags;
  }
}

async function revealLocation(location) {
  const document = await vscode.workspace.openTextDocument(location.uri); const editor = await vscode.window.showTextDocument(document);
  editor.selection = new vscode.Selection(location.range.start, location.range.start); editor.revealRange(location.range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

async function renameSemanticTag(item) {
  if (!item || !item.name) return;
  const name = await vscode.window.showInputBox({ title: `Rename @${item.name}`, value: item.name, validateInput: (value) => /^[\p{L}_][\p{L}\p{M}\p{N}_]*$/u.test(value) ? undefined : "Enter a valid identifier." });
  if (!name || name === item.name) return;
  const edit = new vscode.WorkspaceEdit();
  for (const document of await workspaceSeparanDocuments()) for (const location of tagLocations(document, item.name)) edit.replace(location.uri, location.range, name);
  await vscode.workspace.applyEdit(edit);
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
    const report = documentStructure(editor.document.getText());
    const statuses = new Map(); let removed = [];
    try {
      const before = await headSource(editor);
      const diff = structuralDiff(before, editor.document.getText());
      for (const change of diff.changes) {
        if (change.status === "removed") removed.push(change);
        else statuses.set(change.path, change.status);
      }
    } catch (_) { /* Untracked files still have a useful structure tree. */ }
    const applyStatus = (node) => {
      node.status = statuses.get(node.path);
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
    const report = structuralDiff(before, editor.document.getText());
    showReview("Separan v0.4 — Structural Diff", renderDiff(report));
  } catch (error) { vscode.window.showErrorMessage(error.message); }
}

async function verifyAiEditScope() {
  const editor = currentEditor(); if (!editor) return;
  try {
    const scope = await scopeAt(editor);
    if (!scope) return vscode.window.showInformationMessage("Place the cursor on the label that defines the allowed AI edit scope.");
    const before = await headSource(editor);
    const diff = structuralDiff(before, editor.document.getText());
    const violations = diff.changes.filter((item) => item.status !== "unchanged" && item.path !== scope.path && !item.path.startsWith(`${scope.path}/`));
    const allowedChanges = diff.changes.filter((item) => item.status !== "unchanged").length - violations.length;
    const report = { passed: violations.length === 0, violations: violations.map((item) => ({ path: item.path, reason: `${item.status} outside allowed scope` })), summary: { allowed_changes: allowedChanges, violations: violations.length } };
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
  if (event.contentChanges.length !== 1 || !/^\r?\n[ \t]*$/u.test(event.contentChanges[0].text)) return;
  const editor = currentEditor(); if (!editor || editor.document !== event.document) return;
  const lineNumber = Math.max(0, editor.selection.active.line - 1); const text = codeText(event.document.lineAt(lineNumber).text);
  const match = /^\s*(SEP|if|while|for|object|list|try|error|transaction|http_route)\b.*?:([^\s:()]+)\s*(?:\([^)]*\))?\s*$/u.exec(text);
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
  reviewOutput = vscode.window.createOutputChannel("Separan Review");
  runtimeOutput = vscode.window.createOutputChannel("Separan Runtime");
  structureDiagnostics = vscode.languages.createDiagnosticCollection("separan-structure");
  nativeDiagnostics = vscode.languages.createDiagnosticCollection("separan-native");
  analysisDiagnostics = vscode.languages.createDiagnosticCollection("separan-analysis");
  runStatus = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 90);
  runStatus.text = "$(play) Separan"; runStatus.tooltip = "Run the active Separan file"; runStatus.command = "separan.runFile";
  checkStatus = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 89);
  checkStatus.text = "$(check) Check"; checkStatus.tooltip = "Check the active Separan file"; checkStatus.command = "separan.checkFile";
  const updateStatus = () => {
    const visible = Boolean(currentEditor());
    if (visible) { runStatus.show(); checkStatus.show(); } else { runStatus.hide(); checkStatus.hide(); }
  };
  updateStatus();
  if (currentEditor()) refreshDiagnostics(currentEditor().document, !currentEditor().document.isDirty);
  const structureProvider = new StructureProvider();
  const semanticTagProvider = new SemanticTagProvider();
  const selector = { scheme: "file", language: "separan" };
  const structureView = vscode.window.createTreeView("separan.structureExplorer", { treeDataProvider: structureProvider, showCollapseAll: true });
  const semanticTagView = vscode.window.createTreeView("separan.semanticTags", { treeDataProvider: semanticTagProvider, showCollapseAll: true });
  const refreshStructureSoon = (event) => {
    if (event && event.document && event.document.languageId !== "separan") return;
    clearTimeout(structureRefreshTimer); structureRefreshTimer = setTimeout(() => structureProvider.refresh(), 250);
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("separan.runFile", runFile),
    vscode.commands.registerCommand("separan.checkFile", checkFile),
    vscode.commands.registerCommand("separan.diagnoseRuntime", diagnoseRuntime),
    vscode.commands.registerCommand("separan.goToMatchingLabel", goToMatchingLabel),
    vscode.commands.registerCommand("separan.goToLabel", goToLabel),
    vscode.commands.registerCommand("separan.copyAiEditScope", copyAiScope),
    vscode.commands.registerCommand("separan.showStructuralDiff", showStructuralDiff),
    vscode.commands.registerCommand("separan.verifyAiEditScope", verifyAiEditScope),
    vscode.commands.registerCommand("separan.refreshStructureExplorer", () => structureProvider.refresh()),
    vscode.commands.registerCommand("separan.revealStructure", revealStructure),
    vscode.commands.registerCommand("separan.revealLocation", revealLocation),
    vscode.commands.registerCommand("separan.renameSemanticTag", renameSemanticTag),
    vscode.commands.registerCommand("separan.refreshSemanticTags", () => semanticTagProvider.refresh()),
    vscode.commands.registerCommand("separan.runFunction", runFunction),
    vscode.commands.registerCommand("separan.runTests", runTests),
    vscode.languages.registerCompletionItemProvider(selector, new SeparanCompletionProvider(), ":", ".", "\""),
    vscode.languages.registerSignatureHelpProvider(selector, new SeparanSignatureHelpProvider(), "(", ","),
    vscode.languages.registerHoverProvider(selector, new SeparanHoverProvider()),
    vscode.languages.registerDefinitionProvider(selector, new SeparanDefinitionProvider()),
    vscode.languages.registerReferenceProvider(selector, new SeparanReferenceProvider()),
    vscode.languages.registerRenameProvider(selector, new SeparanRenameProvider()),
    vscode.languages.registerDocumentSymbolProvider(selector, new SeparanDocumentSymbolProvider()),
    vscode.languages.registerDocumentFormattingEditProvider(selector, new SeparanFormattingProvider()),
    vscode.languages.registerWorkspaceSymbolProvider(new SeparanWorkspaceSymbolProvider()),
    vscode.languages.registerInlayHintsProvider(selector, new SeparanInlayHintsProvider()),
    vscode.languages.registerCallHierarchyProvider(selector, new SeparanCallHierarchyProvider()),
    vscode.languages.registerCodeLensProvider(selector, new SeparanCodeLensProvider()),
    reviewOutput,
    runtimeOutput,
    structureDiagnostics,
    nativeDiagnostics,
    analysisDiagnostics,
    runStatus,
    checkStatus,
    structureView,
    semanticTagView,
    vscode.workspace.onDidChangeTextDocument(autoClose),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId !== "separan") return;
      clearTimeout(diagnosticTimer);
      diagnosticTimer = setTimeout(() => refreshDiagnostics(event.document, false), 150);
    }),
    vscode.workspace.onDidChangeTextDocument(refreshStructureSoon),
    vscode.workspace.onDidSaveTextDocument((document) => { if (document.languageId === "separan") { structureProvider.refresh(); semanticTagProvider.refresh(); refreshDiagnostics(document, true); } }),
    vscode.workspace.onDidCloseTextDocument((document) => { structureDiagnostics.delete(document.uri); nativeDiagnostics.delete(document.uri); analysisDiagnostics.delete(document.uri); diagnosticVersions.delete(document.uri.toString()); }),
    vscode.window.onDidChangeActiveTextEditor((editor) => { structureProvider.refresh(); updateStatus(); if (editor) refreshDiagnostics(editor.document, !editor.document.isDirty); }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration("separan.executablePath") && !event.affectsConfiguration("separan.runtimeArguments") && !event.affectsConfiguration("separan.environment")) return;
      for (const document of vscode.workspace.textDocuments) refreshDiagnostics(document, !document.isDirty);
    }),
    vscode.tasks.onDidEndTaskProcess(async (event) => {
      const temporary = temporaryRuns.get(event.execution); if (!temporary) return;
      temporaryRuns.delete(event.execution); await fs.promises.rm(temporary, { force: true });
    }),
    vscode.window.onDidChangeTextEditorSelection(async (event) => {
      if (event.textEditor.document.languageId !== "separan" || !structureView.visible) return;
      const node = await structureProvider.activeNode(event.selections[0].active.line);
      if (node) structureView.reveal(node, { select: true, focus: false, expand: true });
    }),
  );
}

function deactivate() {
  for (const temporary of temporaryRuns.values()) { try { fs.rmSync(temporary, { force: true }); } catch (_) { /* Best-effort cleanup during shutdown. */ } }
  temporaryRuns.clear();
}
module.exports = { activate, deactivate };
