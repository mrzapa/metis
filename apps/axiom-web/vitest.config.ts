import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/__tests__/**/*.test.{ts,tsx}", "**/*.test.{ts,tsx}"],
    // arrow-artifact-boundary.test.tsx: excluded because React 19 concurrent act()
    // creates unbounded V8 heap growth (>4-8 GB) during component rendering in
    // Node.js.  The component and its logic are covered by the build + the
    // extract-arrow-artifacts.test.ts suite.  Re-enable once @testing-library/react
    // or React 19 resolves the act() memory issue, or once browser-mode vitest is
    // configured.
    exclude: [
      "**/node_modules/**",
      "**/arrow-artifact-boundary.test.tsx",
    ],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // Alias @arrow-js/sandbox to a local stub so it NEVER loads the real
      // package in tests (belt-and-suspenders on top of server.deps.external).
      "@arrow-js/sandbox": path.resolve(__dirname, "./__stubs__/arrow-sandbox.ts"),
    },
  },
});
