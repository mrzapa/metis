import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

const TOKENS_JSON_PATH = resolve(__dirname, "../tokens.json");
const TOKENS_CSS_PATH = resolve(__dirname, "../tokens.css");

describe("tokens.json", () => {
  const raw = readFileSync(TOKENS_JSON_PATH, "utf-8");
  const tokens = JSON.parse(raw);

  it("is valid JSON", () => {
    expect(tokens).toBeDefined();
    expect(typeof tokens).toBe("object");
  });

  it("has a color group", () => {
    expect(tokens.color).toBeDefined();
    expect(typeof tokens.color).toBe("object");
  });

  it("has a radius group", () => {
    expect(tokens.radius).toBeDefined();
    expect(tokens.radius.base).toBeDefined();
    expect(tokens.radius.base.$type).toBe("dimension");
  });

  it("all color tokens have $value and $type", () => {
    for (const [name, token] of Object.entries(tokens.color) as [
      string,
      Record<string, unknown>,
    ][]) {
      expect(token.$value, `${name} missing $value`).toBeDefined();
      expect(token.$type, `${name} missing $type`).toBe("color");
    }
  });

  it("all color tokens have dark mode extensions", () => {
    for (const [name, token] of Object.entries(tokens.color) as [
      string,
      Record<string, unknown>,
    ][]) {
      const ext = token.$extensions as Record<string, unknown> | undefined;
      expect(ext?.dark, `${name} missing dark extension`).toBeDefined();
    }
  });
});

describe("tokens.css", () => {
  const css = readFileSync(TOKENS_CSS_PATH, "utf-8");

  it("contains :root block", () => {
    expect(css).toContain(":root");
  });

  it("contains .dark block", () => {
    expect(css).toContain(".dark");
  });

  it("defines all color tokens from tokens.json", () => {
    const raw = readFileSync(TOKENS_JSON_PATH, "utf-8");
    const tokens = JSON.parse(raw);
    for (const name of Object.keys(tokens.color)) {
      expect(css, `--${name} missing from tokens.css`).toContain(`--${name}:`);
    }
  });
});
