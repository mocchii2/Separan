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

  test("finds and renames matching labels across open workspace documents", async () => {
    const firstFile = path.join(directory, "label-first.sep"); const secondFile = path.join(directory, "label-second.sep");
    fs.writeFileSync(firstFile, 'SEP:main\nif true :shared\nendif:shared\nEND_SEP:main\n');
    fs.writeFileSync(secondFile, 'SEP:helper\nwhile true :shared\nendwhile:shared\nEND_SEP:helper\n');
    const first = await vscode.workspace.openTextDocument(firstFile); const second = await vscode.workspace.openTextDocument(secondFile);
    await vscode.window.showTextDocument(first);
    const position = new vscode.Position(1, 10);
    const references = await vscode.commands.executeCommand("vscode.executeReferenceProvider", first.uri, position);
    assert.strictEqual(references.length, 4);
    const edit = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", first.uri, position, "workspace_label");
    assert.ok(edit && await vscode.workspace.applyEdit(edit));
    assert.doesNotMatch(first.getText(), /:shared/u); assert.doesNotMatch(second.getText(), /:shared/u);
    assert.match(first.getText(), /:workspace_label/u); assert.match(second.getText(), /:workspace_label/u);
  });

  test("keeps local variable definition, references, and rename inside its function", async () => {
    const source = 'SEP:first(value: number)\ncopy = value\nprint copy\nEND_SEP:first\nSEP:second(value: number)\ncopy = value\nprint copy\nEND_SEP:second\n';
    const file = path.join(directory, "local-shadowing.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    const position = new vscode.Position(2, 7);
    const definition = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", document.uri, position);
    const target = Array.isArray(definition) ? definition[0] : definition;
    assert.strictEqual((target.targetRange || target.range).start.line, 1);
    const references = await vscode.commands.executeCommand("vscode.executeReferenceProvider", document.uri, position);
    assert.strictEqual(references.length, 2);
    const edit = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", document.uri, position, "first_copy");
    assert.ok(edit && await vscode.workspace.applyEdit(edit));
    assert.match(document.getText(), /first_copy = value\nprint first_copy/u);
    assert.match(document.getText(), /SEP:second[\s\S]*copy = value\nprint copy/u);
  });

  test("keeps same-named functions isolated by their imported module", async () => {
    const firstModule = path.join(directory, "first-module.sep"); const secondModule = path.join(directory, "second-module.sep");
    const firstCaller = path.join(directory, "first-caller.sep"); const secondCaller = path.join(directory, "second-caller.sep");
    fs.writeFileSync(firstModule, 'SEP:shared\nshared()\nEND_SEP:shared\n');
    fs.writeFileSync(secondModule, 'SEP:shared\nEND_SEP:shared\n');
    fs.writeFileSync(firstCaller, 'import "first-module" as first\nSEP:main\nfirst.shared()\nEND_SEP:main\n');
    fs.writeFileSync(secondCaller, 'import "second-module" as second\nSEP:main\nsecond.shared()\nEND_SEP:main\n');
    const first = await vscode.workspace.openTextDocument(firstModule); const second = await vscode.workspace.openTextDocument(secondModule);
    const caller = await vscode.workspace.openTextDocument(firstCaller); await vscode.workspace.openTextDocument(secondCaller);
    await vscode.window.showTextDocument(first);
    const references = await vscode.commands.executeCommand("vscode.executeReferenceProvider", first.uri, new vscode.Position(0, 5));
    assert.ok(references.length >= 4);
    const referencePaths = references.map((location) => path.normalize(location.uri.fsPath).toLocaleLowerCase());
    assert.ok(referencePaths.includes(path.normalize(firstCaller).toLocaleLowerCase()), JSON.stringify(referencePaths));
    assert.ok(references.every((location) => location.uri.fsPath !== secondCaller && location.uri.fsPath !== secondModule));
    const edit = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", first.uri, new vscode.Position(0, 5), "first_shared");
    assert.ok(edit && await vscode.workspace.applyEdit(edit));
    assert.match(first.getText(), /SEP:first_shared\nfirst_shared\(\)\nEND_SEP:first_shared/u);
    assert.match(caller.getText(), /first\.first_shared\(\)/u);
    assert.match(second.getText(), /SEP:shared\nEND_SEP:shared/u);
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
    for (const item of allBuiltins.items.filter((item) => Object.hasOwn(builtinNames, item.label)))
      assert.doesNotMatch(String(item.detail), /\barg\d+\b/u, "generic parameter remained in " + item.label);
    const hints = await vscode.commands.executeCommand("vscode.executeInlayHintProvider", document.uri, new vscode.Range(0, 0, document.lineCount - 1, 0));
    assert.ok(hints.some((hint) => String(hint.label).includes("string")));
    const references = await vscode.commands.executeCommand("vscode.executeReferenceProvider", document.uri, new vscode.Position(2, 14));
    assert.strictEqual(references.length, 3);
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

  test("provides precise core built-in signatures and return hints", async () => {
    const source = 'SEP:main\nabsolute = abs(-2)\nexists = file_exists("sample.sep")\nlines = read_lines("sample.sep")\nindexes = range(1, 4)\nnumbers = [1, 2]\nadded = append(numbers, 3)\nfirst_number = first(numbers)\ndigest = sha256_hash("value")\nmatch = regex_find("v", "value")\nyaml_text = object_to_yaml({})\nmessage = mail_create_message()\nEND_SEP:main\n';
    const file = path.join(directory, "core-builtins.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    const completions = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", document.uri, new vscode.Position(1, 0));
    const byName = new Map(completions.items.map((item) => [item.label, item]));
    assert.match(String(byName.get("abs").detail), /value: number/u);
    assert.match(String(byName.get("read_lines").detail), /list<string>/u);
    assert.match(String(byName.get("sha256_hash").detail), /-> bytes/u);
    assert.match(String(byName.get("runtime_error").detail), /message: string/u);
    assert.match(String(byName.get("db_query_one").detail), /object \| EMPTY/u);
    assert.match(String(byName.get("object_to_yaml").detail), /-> string/u);
    assert.match(String(byName.get("mail_send_message").detail), /mail_send_result/u);
    const hints = await vscode.commands.executeCommand("vscode.executeInlayHintProvider", document.uri, new vscode.Range(0, 0, document.lineCount - 1, 0));
    const labels = hints.map((hint) => String(hint.label));
    assert.ok(labels.includes(": number"));
    assert.ok(labels.includes(": boolean"));
    assert.ok(labels.includes(": list<string>"));
    assert.ok(labels.includes(": list<number>"));
    assert.ok(labels.includes(": bytes"));
    assert.ok(labels.includes(": regex_match_result | EMPTY"));
    assert.ok(labels.includes(": mail_message"));
    assert.ok(labels.filter((label) => label === ": list<number>").length >= 3);
    assert.ok(labels.filter((label) => label === ": number").length >= 2);
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

  test("validates built-in named arguments without counting them as positional", async () => {
    const file = path.join(directory, "named-arguments.sep");
    fs.writeFileSync(file, 'SEP:main\nresponse = http_get("https://example.test", timeout = 5)\nbad = http_get("https://example.test", unknown = 5)\nEND_SEP:main\n');
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    let diagnostics = [];
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      diagnostics = vscode.languages.getDiagnostics(document.uri);
      if (diagnostics.some((item) => item.code === "unknown-named-argument")) break;
    }
    const argumentCounts = diagnostics.filter((item) => item.code === "argument-count");
    const unknownNamed = diagnostics.filter((item) => item.code === "unknown-named-argument");
    assert.strictEqual(argumentCounts.length, 0);
    assert.strictEqual(unknownNamed.length, 1);
    assert.match(unknownNamed[0].message, /unknown/u);
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

  test("merges EMPTY return types and reports static code issues", async () => {
    const source = 'SEP:maybe(flag: boolean)\nif flag :choice\nreturn "yes"\nelse:choice\nreturn EMPTY\nendif:choice\nEND_SEP:maybe\nSEP:unused\nEND_SEP:unused\nSEP:duplicate\nEND_SEP:duplicate\nSEP:duplicate\nEND_SEP:duplicate\nSEP:main\nanswer = maybe(true)\nunused_value = 1\nreturn answer\nprint "never"\nEND_SEP:main\n';
    const file = path.join(directory, "static-analysis.sep"); fs.writeFileSync(file, source);
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    const hints = await vscode.commands.executeCommand("vscode.executeInlayHintProvider", document.uri, new vscode.Range(0, 0, document.lineCount - 1, 0));
    assert.ok(hints.some((hint) => String(hint.label) === ": string | EMPTY"));
    let diagnostics = [];
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      diagnostics = vscode.languages.getDiagnostics(document.uri);
      if (diagnostics.some((item) => item.code === "unreachable-code")) break;
    }
    const codes = new Set(diagnostics.map((item) => item.code));
    assert.ok(codes.has("unused-function"));
    assert.ok(codes.has("unused-variable"));
    assert.ok(codes.has("duplicate-function"));
    assert.ok(codes.has("unreachable-code"));
  });

  test("provides quick fixes for labels, unused imports, and undefined functions", async () => {
    const file = path.join(directory, "quick-fixes.sep");
    fs.writeFileSync(file, 'import "module" as unused\nSEP:main\nmissing_helper()\nif true :choice\nendif:wrong\nEND_SEP:main\n');
    const document = await vscode.workspace.openTextDocument(file); await vscode.window.showTextDocument(document);
    let diagnostics = [];
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50)); diagnostics = vscode.languages.getDiagnostics(document.uri);
      if (diagnostics.some((item) => item.code === "undefined-function")) break;
    }
    const actions = [];
    for (const diagnostic of diagnostics) {
      const found = await vscode.commands.executeCommand("vscode.executeCodeActionProvider", document.uri, diagnostic.range, vscode.CodeActionKind.QuickFix.value);
      actions.push(...found);
    }
    const titles = new Set(actions.map((action) => action.title));
    assert.ok(titles.has("Replace with endif:choice"));
    assert.ok(titles.has("Remove unused import"));
    assert.ok(titles.has("Create function 'missing_helper'"));
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

  test("updates import paths when Separan files are renamed", async () => {
    const importer = path.join(directory, "imports-module.sep");
    const renamed = path.join(directory, "nested", "renamed-module.sep");
    fs.writeFileSync(importer, 'import "module" as mod\nSEP:main\nmod.wrapper(1)\nEND_SEP:main\n');
    fs.mkdirSync(path.dirname(renamed));
    const document = await vscode.workspace.openTextDocument(importer);
    await vscode.window.showTextDocument(document);

    const edit = new vscode.WorkspaceEdit();
    edit.renameFile(vscode.Uri.file(path.join(directory, "module.sep")), vscode.Uri.file(renamed));
    assert.strictEqual(await vscode.workspace.applyEdit(edit), true);
    assert.match(document.getText(), /import "\.\/nested\/renamed-module" as mod/u);
    await document.save();
    assert.match(fs.readFileSync(importer, "utf8"), /import "\.\/nested\/renamed-module" as mod/u);
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
