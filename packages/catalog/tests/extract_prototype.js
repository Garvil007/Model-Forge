"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const htmlPath = path.join(__dirname, "..", "..", "..", "docs", "ui-prototype.html");
const html = fs.readFileSync(htmlPath, "utf8");
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) {
  throw new Error("No <script> tag found in ui-prototype.html");
}
// vm.runInContext only exposes top-level `var` bindings as properties of the context
// object; `const`/`let` stay in an invisible lexical scope. Downgrade them so TECHS,
// METHODS and CONVERTS land on `sandbox`.
const code = match[1].replace(/\bconst\b/g, "var").replace(/\blet\b/g, "var");

function makeFakeElement() {
  const el = {
    classList: { add() {}, remove() {}, toggle() {} },
    dataset: {},
    style: {},
    addEventListener() {},
    removeEventListener() {},
    appendChild() {},
    querySelector() {
      return makeFakeElement();
    },
    querySelectorAll() {
      return [];
    },
    closest() {
      return null;
    },
    focus() {},
    setAttribute() {},
    getAttribute() {
      return null;
    },
  };
  return new Proxy(el, {
    get(target, prop) {
      if (prop in target) return target[prop];
      if (prop === "innerHTML" || prop === "textContent" || prop === "value") return "";
      return undefined;
    },
    set() {
      return true;
    },
  });
}

const fakeDocument = {
  querySelector() {
    return makeFakeElement();
  },
  querySelectorAll() {
    return [];
  },
  addEventListener() {},
  createElement() {
    return makeFakeElement();
  },
};

const sandbox = {
  document: fakeDocument,
  window: undefined,
  console,
  requestAnimationFrame() {},
  setTimeout,
  Promise,
};
sandbox.window = sandbox;
vm.createContext(sandbox);

try {
  vm.runInContext(code, sandbox, { filename: "ui-prototype.html" });
} catch (e) {
  // Expected: DOM-dependent code at the bottom of the script throws against our stubs.
  // TECHS/METHODS/CONVERTS are assigned before that point and survive regardless.
}

function stripFns(value) {
  if (typeof value === "function") return undefined;
  if (Array.isArray(value)) return value.map(stripFns);
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      if (typeof v === "function") continue;
      out[k] = stripFns(v);
    }
    return out;
  }
  return value;
}

process.stdout.write(
  JSON.stringify({
    techs: stripFns(sandbox.TECHS),
    methods: stripFns(sandbox.METHODS),
    converts: stripFns(sandbox.CONVERTS),
  })
);
