// Read fetch() calls under one application root, using that app's typescript.
// Prints one JSON object. Python treats a failure as a skipped TypeScript scan.

import { readdir, readFile, stat } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const SKIP = new Set([
  "node_modules",
  ".venv",
  ".next",
  "__pycache__",
  "site-packages",
]);

const rootArgument = process.argv[2];
if (!rootArgument) {
  report({ skipped: true, edges: [] });
}

const root = path.resolve(rootArgument);

try {
  const typescript = loadTypeScript(root);
  if (!typescript) {
    report({ skipped: true, edges: [] });
  }
  const edges = await walk(root, typescript);
  report({ skipped: false, edges });
} catch {
  report({ skipped: true, edges: [] });
}

function report(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
  process.exit(0);
}

function loadTypeScript(appRoot) {
  const manifest = path.join(appRoot, "package.json");
  try {
    return createRequire(manifest)("typescript");
  } catch {
    return null;
  }
}

async function walk(appRoot, typescript) {
  const edges = [];
  await visit(appRoot, appRoot, typescript, edges);
  return edges;
}

async function visit(directory, appRoot, typescript, edges) {
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    if (SKIP.has(entry.name) || entry.isSymbolicLink()) {
      continue;
    }
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await visit(full, appRoot, typescript, edges);
      continue;
    }
    if (!entry.name.endsWith(".ts") && !entry.name.endsWith(".tsx")) {
      continue;
    }
    const info = await stat(full);
    if (!info.isFile()) {
      continue;
    }
    const text = await readFile(full, "utf8");
    edges.push(...fetchEdges(typescript, appRoot, full, text));
  }
}

function fetchEdges(typescript, appRoot, file, text) {
  const kind = file.endsWith(".tsx")
    ? typescript.ScriptKind.TSX
    : typescript.ScriptKind.TS;
  const source = typescript.createSourceFile(
    file,
    text,
    typescript.ScriptTarget.Latest,
    true,
    kind,
  );
  const found = [];
  const visitNode = (node) => {
    const edge = edgeFromCall(typescript, source, appRoot, file, node);
    if (edge) {
      found.push(edge);
    }
    typescript.forEachChild(node, visitNode);
  };
  visitNode(source);
  return found;
}

function edgeFromCall(typescript, source, appRoot, file, node) {
  if (
    !typescript.isCallExpression(node) ||
    !typescript.isIdentifier(node.expression)
  ) {
    return null;
  }
  if (node.expression.text !== "fetch") {
    return null;
  }
  const requestPath = pathFrom(typescript, node.arguments[0]);
  const method = methodFrom(typescript, node.arguments[1]);
  if (!requestPath || !method) {
    return null;
  }
  const position = source.getLineAndCharacterOfPosition(node.getStart(source));
  const at = `${path.relative(appRoot, file)}:${position.line + 1}`;
  return {
    from: `browser:request:${requestPath}`,
    to: `api:request:${method} ${requestPath}`,
    originAt: at,
    targetAt: at,
  };
}

function pathFrom(typescript, node) {
  if (!node) {
    return "";
  }
  if (
    typescript.isStringLiteral(node) ||
    typescript.isNoSubstitutionTemplateLiteral(node)
  ) {
    return requestPath(node.text);
  }
  if (!typescript.isTemplateExpression(node)) {
    return "";
  }
  const tail = node.templateSpans.at(-1)?.literal.text ?? "";
  if (!tail.startsWith("/")) {
    return "";
  }
  return requestPath(tail);
}

function requestPath(value) {
  const literal = value.trim();
  if (
    !literal.startsWith("/") &&
    !literal.startsWith("http://") &&
    !literal.startsWith("https://")
  ) {
    return "";
  }
  try {
    return new URL(literal, "http://stack-inspect.local").pathname;
  } catch {
    return "";
  }
}

function methodFrom(typescript, node) {
  if (!node) {
    return "GET";
  }
  if (!typescript.isObjectLiteralExpression(node)) {
    return "";
  }
  for (const property of node.properties) {
    if (
      !typescript.isPropertyAssignment(property) ||
      propertyName(typescript, property.name) !== "method"
    ) {
      continue;
    }
    const value = property.initializer;
    if (
      typescript.isStringLiteral(value) ||
      typescript.isNoSubstitutionTemplateLiteral(value)
    ) {
      return value.text.toUpperCase();
    }
    return "";
  }
  return "GET";
}

function propertyName(typescript, name) {
  if (typescript.isIdentifier(name) || typescript.isStringLiteral(name)) {
    return name.text;
  }
  return "";
}
