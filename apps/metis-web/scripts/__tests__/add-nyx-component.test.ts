import path from "node:path";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

const nyxModulePromise = import("../add-nyx-component.mjs");
const testFilePath = fileURLToPath(import.meta.url);
const testDir = path.dirname(testFilePath);
const appRoot = path.resolve(testDir, "../..");
const packageJsonPath = path.resolve(testDir, "../../package.json");

interface PackageManifest {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
}

describe("add-nyx-component", () => {
  it("normalizes and deduplicates supported NyxUI specifiers", async () => {
    const { resolveNyxComponents } = await nyxModulePromise;

    expect(
      resolveNyxComponents([
        "@nyx/glow-card",
        "https://nyxui.com/r/music-player.json",
        "glow-card",
        "unknown-card",
        "   ",
      ]),
    ).toEqual({
      rejected: ["unknown-card"],
      selected: ["glow-card", "music-player"],
    });
  });

  it("derives the install allowlist from the packaged Nyx snapshot", async () => {
    const { CURATED_NYX_COMPONENTS, PREVIEWABLE_NYX_COMPONENTS, resolveNyxComponents } =
      await nyxModulePromise;

    expect(CURATED_NYX_COMPONENTS).toHaveProperty("glow-card");
    expect(CURATED_NYX_COMPONENTS).not.toHaveProperty("marquee");
    expect(PREVIEWABLE_NYX_COMPONENTS).toHaveProperty("marquee");
    expect(PREVIEWABLE_NYX_COMPONENTS.marquee.installable).toBe(false);
    expect(resolveNyxComponents(["marquee"])).toEqual({
      rejected: ["marquee"],
      selected: [],
    });
  });

  it("validates components.json with the same registry constraints the installed shadcn CLI enforces", async () => {
    const { validateInstalledShadcnConfig } = await nyxModulePromise;
    const { registries } = await validateInstalledShadcnConfig(appRoot);
    const nyxRegistry = registries["@nyx"];

    expect(registries).toHaveProperty("@shadcn");
    expect(nyxRegistry).toBeTruthy();
    expect(typeof nyxRegistry === "string" ? nyxRegistry : nyxRegistry.url).toBe(
      "https://nyxui.com/r/{name}.json",
    );
  });

  it("keeps the reviewed installable NyxUI subset aligned with the app dependency surface", async () => {
    const { CURATED_NYX_COMPONENTS, findMissingDependencies } = await nyxModulePromise;
    const packageManifest = JSON.parse(
      await readFile(packageJsonPath, "utf8"),
    ) as PackageManifest;

    expect(findMissingDependencies(Object.keys(CURATED_NYX_COMPONENTS), packageManifest)).toEqual([]);
  });

  it("rejects obviously broken upstream dependency metadata before invoking shadcn add", async () => {
    const { auditNyxRegistryItem } = await nyxModulePromise;

    expect(
      auditNyxRegistryItem("marquee", {
        dependencies: ["motion", "..", "   "],
        devDependencies: ["@types/node", "./local-package"],
        files: [
          {
            path: "registry/ui/marquee.tsx",
            target: "components/ui/marquee.tsx",
            type: "registry:ui",
          },
        ],
        name: "marquee",
        registryDependencies: ["button", ""],
      }),
    ).toEqual(
      expect.arrayContaining([
        "marquee: dependencies contains invalid package specifiers: ..,    ",
        "marquee: devDependencies contains invalid package specifiers: ./local-package",
        "marquee: registryDependencies contains blank or non-string entries",
      ]),
    );
  });

  it("accepts clean upstream dependency metadata", async () => {
    const { auditNyxRegistryItem } = await nyxModulePromise;

    expect(
      auditNyxRegistryItem("glow-card", {
        dependencies: ["clsx", "tailwind-merge"],
        files: [
          {
            path: "registry/ui/glow-card.tsx",
            target: "components/ui/glow-card.tsx",
            type: "registry:ui",
          },
        ],
        name: "glow-card",
      }),
    ).toEqual([]);
  });

  it("rejects reviewed installable components when live targets drift outside the allowed policy", async () => {
    const { auditCuratedNyxComponents } = await nyxModulePromise;
    const fetchImplementation = vi.fn(async () => ({
      json: async () => ({
        files: [
          {
            path: "registry/ui/glow-card.tsx",
            target: "../outside/glow-card.tsx",
            type: "registry:ui",
          },
        ],
        name: "glow-card",
      }),
      ok: true,
      status: 200,
      statusText: "OK",
    }));

    vi.stubGlobal("fetch", fetchImplementation);

    try {
      const auditResult = await auditCuratedNyxComponents(
        ["glow-card"],
        "https://nyxui.com/r/{name}.json",
      );

      expect(auditResult.invalidComponents).toEqual(["glow-card"]);
      expect(auditResult.issuesByComponent["glow-card"]).toEqual(
        expect.arrayContaining([
          "glow-card: ../outside/glow-card.tsx cannot traverse parent directories",
        ]),
      );
      expect(fetchImplementation).toHaveBeenCalledWith(
        "https://nyxui.com/r/glow-card.json",
        {
          headers: {
            accept: "application/json",
          },
        },
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("forwards shadcn args as literal argv entries without shell execution", async () => {
    const { runShadcnCommand } = await nyxModulePromise;
    const spawnImplementation = vi.fn(() => ({ status: 0 }));
    const forwardedArg = "--path=foo&ver";

    expect(
      runShadcnCommand("add", ["@nyx/glow-card"], [forwardedArg], {
        cwd: appRoot,
        spawnImplementation,
        stdio: "pipe",
      }),
    ).toBe(0);

    expect(spawnImplementation).toHaveBeenCalledOnce();

    const [command, args, options] = spawnImplementation.mock.calls[0];

    expect(command).toBe(process.execPath);
    expect(args[0]).toContain(path.join("node_modules", "shadcn", "dist", "index.js"));
    expect(args.slice(1)).toEqual(["add", forwardedArg, "@nyx/glow-card"]);
    expect(options).toEqual({
      cwd: appRoot,
      stdio: "pipe",
    });
  });
});