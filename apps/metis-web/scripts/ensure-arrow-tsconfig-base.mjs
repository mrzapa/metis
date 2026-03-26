import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const basePath = path.resolve(process.cwd(), "node_modules", "tsconfig.base.json");
const coreTsconfigPath = path.resolve(
  process.cwd(),
  "node_modules",
  "@arrow-js",
  "core",
  "tsconfig.json",
);

const shimConfig = {
  compilerOptions: {
    module: "ESNext",
    target: "ES2020",
  },
};

async function ensureArrowTsconfigBase() {
  try {
    await access(basePath);
  } catch {
    await mkdir(path.dirname(basePath), { recursive: true });
    await writeFile(basePath, `${JSON.stringify(shimConfig, null, 2)}\n`, "utf8");
    console.log("[ensure-arrow-tsconfig-base] Created node_modules/tsconfig.base.json shim");
  }
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object";
}

async function patchArrowCoreTsconfig() {
  try {
    const raw = await readFile(coreTsconfigPath, "utf8");
    const parsed = JSON.parse(raw);
    const compilerOptions = isRecord(parsed.compilerOptions) ? parsed.compilerOptions : {};

    let changed = false;
    if ("extends" in parsed) {
      delete parsed.extends;
      changed = true;
    }

    if (compilerOptions.module !== "ESNext") {
      compilerOptions.module = "ESNext";
      changed = true;
    }

    if (parsed.compilerOptions !== compilerOptions) {
      parsed.compilerOptions = compilerOptions;
      changed = true;
    }

    if (!changed) {
      return;
    }

    await writeFile(coreTsconfigPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    console.log("[ensure-arrow-tsconfig-base] Patched @arrow-js/core tsconfig for editor diagnostics");
  } catch {
    // Skip patching when dependencies are not installed yet.
  }
}

ensureArrowTsconfigBase().catch((error) => {
  console.error("[ensure-arrow-tsconfig-base] Failed to create tsconfig shim", error);
  process.exitCode = 1;
});

patchArrowCoreTsconfig().catch((error) => {
  console.error("[ensure-arrow-tsconfig-base] Failed to patch @arrow-js/core tsconfig", error);
  process.exitCode = 1;
});
