const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const vscode = require("vscode");

async function executeTaskCommand(taskName, command, ...arguments_) {
  let subscription; let timer;
  const ended = new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error("Timed out waiting for task " + taskName)), 10000);
    subscription = vscode.tasks.onDidEndTaskProcess((event) => {
      if (event.execution.task.source === "Separan" && event.execution.task.name === taskName) {
        clearTimeout(timer); subscription.dispose();
        if (event.exitCode === 0) resolve(); else reject(new Error(taskName + " exited with " + event.exitCode));
      }
    });
  });
  await vscode.commands.executeCommand(command, ...arguments_);
  await ended;
}

suite("Separan extension", () => {
  let directory;
  setup(async () => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), "separan-vscode-"));
    fs.writeFileSync(path.join(directory, "sample.sep"), "SEP:helper(value)\nreturn string(value)\nEND_SEP:helper\nSEP:main\n@smoke\nprint helper(1)\nEND_SEP:main\n");
    fs.writeFileSync(path.join(directory, "module.sep"), "SEP:wrapper(value)\nreturn message(value)\nEND_SEP:wrapper\nSEP:message(value)\ntemporary = string(value)\nreturn temporary\nEND_SEP:message\n");
  });
  teardown(async () => {
    await vscode.commands.executeCommand("workbench.action.closeAllEditors");
    for (let attempt = 0; attempt < 10; attempt += 1) {
      try { fs.rmSync(directory, { recursive: true, force: true }); return; }
      catch (error) { if (attempt === 9) throw error; await new Promise((resolve) => setTimeout(resolve, 50)); }
    }
  });

  test("activates and provides symbols, completion, hover, and definitions", async () => {
    const document = await vscode.workspace.openTextDocument(path.join(directory, "sample.sep"));
    await vscode.window.showTextDocument(document);
    const extension = vscode.extensions.getExtension("separan.separan-language");
    assert.ok(extension); await extension.activate();
    const symbols = await vscode.commands.executeCommand("vscode.executeDocumentSymbolProvider", document.uri);
    assert.ok(symbols.some((symbol) => symbol.name === "SEP:helper"));
    const completions = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", document.uri, new vscode.Position(5, 6));
    assert.ok(completions.items.some((item) => item.label === "helper"));
    assert.ok(completions.items.some((item) => item.label === "http_get"));
    const hover = await vscode.commands.executeCommand("vscode.executeHoverProvider", document.uri, new vscode.Position(5, 8));
    assert.ok(hover.length > 0);
    const definitions = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", document.uri, new vscode.Position(5, 8));
    assert.ok(definitions.length > 0);
  });

  test("renames semantic tags without a language server", async () => {
    const document = await vscode.workspace.openTextDocument(path.join(directory, "sample.sep"));
    const edit = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", document.uri, new vscode.Position(4, 2), "renamed");
    assert.ok(edit); assert.ok(await vscode.workspace.applyEdit(edit));
    assert.match(document.getText(), /@renamed/u);
  });

  test("covers all built-ins and resolves imported functions", async () => {
    const source = 'import "module" as mod\nSEP:main\ntext = mod.wrapper(1)\nhttp_get(\nEND_SEP:main\n';
    const file = path.join(directory, "imports.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file);
    await vscode.window.showTextDocument(document);
    const imported = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", document.uri, new vscode.Position(2, 11), ".");
    assert.ok(imported.items.some((item) => item.label === "wrapper"));
    const definition = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", document.uri, new vscode.Position(2, 14));
    const target = Array.isArray(definition) ? definition[0] : definition;
    assert.ok(target && (target.uri || target.targetUri).fsPath.endsWith("module.sep"));
    const importDefinition = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", document.uri, new vscode.Position(0, 9));
    const importTarget = Array.isArray(importDefinition) ? importDefinition[0] : importDefinition;
    assert.ok(importTarget && (importTarget.uri || importTarget.targetUri).fsPath.endsWith("module.sep"));
    const signature = await vscode.commands.executeCommand("vscode.executeSignatureHelpProvider", document.uri, new vscode.Position(3, 9), "(");
    assert.ok(signature && signature.signatures[0].label.startsWith("http_get("));
    const allBuiltins = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", document.uri, new vscode.Position(3, 0));
    const builtinNames = require("../../data/builtins.json");
    for (const name of Object.keys(builtinNames)) assert.ok(allBuiltins.items.some((item) => item.label === name), "missing built-in " + name);
    const hints = await vscode.commands.executeCommand("vscode.executeInlayHintProvider", document.uri, new vscode.Range(0, 0, document.lineCount - 1, 0));
    assert.ok(hints.some((hint) => String(hint.label).includes("string")));
    const references = await vscode.commands.executeCommand("vscode.executeReferenceProvider", document.uri, new vscode.Position(2, 14));
    assert.strictEqual(references.length, 2);
    const importedHierarchy = await vscode.commands.executeCommand("vscode.prepareCallHierarchy", document.uri, new vscode.Position(2, 14));
    assert.ok(importedHierarchy && importedHierarchy[0].uri.fsPath.endsWith("module.sep"));
    const importedIncoming = await vscode.commands.executeCommand("vscode.provideIncomingCalls", importedHierarchy[0]);
    assert.ok(importedIncoming.some((call) => call.from.name === "main"));
    const mainHierarchy = await vscode.commands.executeCommand("vscode.prepareCallHierarchy", document.uri, new vscode.Position(1, 5));
    const importedOutgoing = await vscode.commands.executeCommand("vscode.provideOutgoingCalls", mainHierarchy[0]);
    assert.ok(importedOutgoing.some((call) => call.to.name === "wrapper" && call.to.uri.fsPath.endsWith("module.sep")));
    const rename = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", document.uri, new vscode.Position(2, 14), "renamed_wrapper");
    assert.ok(rename && await vscode.workspace.applyEdit(rename));
    assert.match(document.getText(), /mod\.renamed_wrapper\(1\)/u);
    const moduleDocument = await vscode.workspace.openTextDocument(path.join(directory, "module.sep"));
    assert.match(moduleDocument.getText(), /SEP:renamed_wrapper/u);
  });

  test("reports invalid imports and imported members", async () => {
    const source = 'import "module" as mod\nimport "module" as mod\nimport "missing" as absent\nSEP:helper(value)\nreturn value\nEND_SEP:helper\nSEP:main\nnumber count = "wrong"\nabs()\nmod.wrapper()\nmod.unknown()\nhelper(other = 1)\nmissing_local()\nEND_SEP:main\n';
    const file = path.join(directory, "invalid-imports.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    let diagnostics = [];
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      diagnostics = vscode.languages.getDiagnostics(document.uri).filter((item) => item.source === "Separan Analysis");
      if (diagnostics.length >= 8) break;
    }
    const codes = new Set(diagnostics.map((item) => item.code));
    assert.ok(codes.has("duplicate-import-alias"));
    assert.ok(codes.has("missing-import"));
    assert.ok(codes.has("unknown-import-member"));
    assert.ok(codes.has("type-mismatch"));
    assert.ok(codes.has("argument-count"));
    assert.ok(codes.has("undefined-function"));
    assert.ok(codes.has("unknown-named-argument"));
    assert.ok(codes.has("unused-import"));
  });

  test("infers homogeneous list and typed parameter returns", async () => {
    const source = 'object:user\nstring name = "Ada"\nend_object:user\nSEP:double(value: number)\nreturn value * 2\nEND_SEP:double\nSEP:main\nnumbers = [1, 2, 3]\nresult = double(2)\nfor item in numbers :items\ncopy = item\nendfor:items\nfield = user.name\nEND_SEP:main\n';
    const file = path.join(directory, "types.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file);
    const hints = await vscode.commands.executeCommand("vscode.executeInlayHintProvider", document.uri, new vscode.Range(0, 0, document.lineCount - 1, 0));
    const labels = hints.map((hint) => String(hint.label));
    assert.ok(labels.includes(": list<number>"));
    assert.ok(labels.includes(": number"));
    assert.ok(labels.includes(": string"));
  });

  test("completes import paths and reports import cycles", async () => {
    const completionFile = path.join(directory, "complete.sep"); fs.writeFileSync(completionFile, 'import "mo');
    const completionDocument = await vscode.workspace.openTextDocument(completionFile);
    const completions = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", completionDocument.uri, new vscode.Position(0, 10));
    assert.ok(completions.items.some((item) => item.label === "module"));

    const first = path.join(directory, "cycle-a.sep"); const second = path.join(directory, "cycle-b.sep");
    fs.writeFileSync(first, 'import "cycle-b" as second\nSEP:first\nsecond.second()\nEND_SEP:first\n');
    fs.writeFileSync(second, 'import "cycle-a" as first\nSEP:second\nfirst.first()\nEND_SEP:second\n');
    const document = await vscode.workspace.openTextDocument(first); await vscode.window.showTextDocument(document);
    let diagnostics = [];
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      diagnostics = vscode.languages.getDiagnostics(document.uri);
      if (diagnostics.some((item) => item.code === "cyclic-import")) break;
    }
    assert.ok(diagnostics.some((item) => item.code === "cyclic-import"));
  });

  test("provides call hierarchy, CodeLens, and workspace symbols", async () => {
    const document = await vscode.workspace.openTextDocument(path.join(directory, "sample.sep"));
    const prepared = await vscode.commands.executeCommand("vscode.prepareCallHierarchy", document.uri, new vscode.Position(0, 5));
    assert.ok(prepared && prepared.length === 1);
    const incoming = await vscode.commands.executeCommand("vscode.provideIncomingCalls", prepared[0]);
    assert.ok(incoming.some((call) => call.from.name === "main"));
    const main = await vscode.commands.executeCommand("vscode.prepareCallHierarchy", document.uri, new vscode.Position(3, 5));
    const outgoing = await vscode.commands.executeCommand("vscode.provideOutgoingCalls", main[0]);
    assert.ok(outgoing.some((call) => call.to.name === "helper"));
    const lenses = await vscode.commands.executeCommand("vscode.executeCodeLensProvider", document.uri);
    assert.ok(lenses.some((lens) => String(lens.command && lens.command.title).includes("reference")));
    const symbols = await vscode.commands.executeCommand("vscode.executeWorkspaceSymbolProvider", "workspace_fixture");
    assert.ok(symbols.some((symbol) => symbol.name === "SEP:workspace_fixture"));
  });

  test("formats indentation without changing structure", async () => {
    const source = 'SEP:main\nif true :choice\nprint "yes"\nelse:choice\n##note\nif true :decorative\nendif:decorative\n##note\nprint "no"\nendif:choice\nEND_SEP:main\n';
    const file = path.join(directory, "format.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file);
    const before = await vscode.commands.executeCommand("vscode.executeDocumentSymbolProvider", document.uri);
    const editor = await vscode.window.showTextDocument(document);
    editor.options = { ...editor.options, insertSpaces: true, tabSize: 4 };
    await vscode.commands.executeCommand("editor.action.formatDocument");
    assert.match(document.getText(), /^ {8}print "yes"$/mu);
    const after = await vscode.commands.executeCommand("vscode.executeDocumentSymbolProvider", document.uri);
    assert.deepStrictEqual(after.map((symbol) => symbol.name), before.map((symbol) => symbol.name));
  });

  test("runs files, functions, and test functions through native tasks", async () => {
    const source = 'SEP:alpha\nprint "alpha"\nEND_SEP:alpha\nSEP:test_one\nprint "one"\nEND_SEP:test_one\nSEP:test_two\nprint "two"\nEND_SEP:test_two\nSEP:main\nprint "main"\nEND_SEP:main\n';
    const file = path.join(directory, "run.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    const output = path.join(directory, "runtime-result.json"); const probe = path.resolve(__dirname, "..", "runtime-probe.js");
    const configuration = vscode.workspace.getConfiguration("separan", document.uri);
    await configuration.update("executablePath", "node", vscode.ConfigurationTarget.Global);
    await configuration.update("runtimeArguments", [probe], vscode.ConfigurationTarget.Global);
    await configuration.update("environment", { SEPARAN_TEST_OUTPUT: output }, vscode.ConfigurationTarget.Global);

    await executeTaskCommand("Run File", "separan.runFile");
    let result = JSON.parse(fs.readFileSync(output, "utf8"));
    assert.strictEqual(path.resolve(result.sourcePath).toLocaleLowerCase(), path.resolve(file).toLocaleLowerCase());

    await executeTaskCommand("Check Current File", "separan.checkFile");
    result = JSON.parse(fs.readFileSync(output, "utf8"));
    assert.ok(result.arguments.includes("--check"));
    assert.strictEqual(path.resolve(result.sourcePath).toLocaleLowerCase(), path.resolve(file).toLocaleLowerCase());

    await executeTaskCommand("Run alpha", "separan.runFunction", document.uri, "alpha");
    result = JSON.parse(fs.readFileSync(output, "utf8"));
    assert.match(result.source, /alpha\(\)/u);
    assert.doesNotMatch(result.source, /print "main"/u);

    await executeTaskCommand("Run 2 Separan Tests", "separan.runTests");
    result = JSON.parse(fs.readFileSync(output, "utf8"));
    assert.match(result.source, /test_one\(\)/u);
    assert.match(result.source, /test_two\(\)/u);
    assert.doesNotMatch(result.source, /print "main"/u);
    for (let attempt = 0; attempt < 20 && fs.readdirSync(directory).some((name) => name.startsWith(".separan-vscode-run-")); attempt += 1)
      await new Promise((resolve) => setTimeout(resolve, 25));
    assert.ok(!fs.readdirSync(directory).some((name) => name.startsWith(".separan-vscode-run-")));
  });
});
