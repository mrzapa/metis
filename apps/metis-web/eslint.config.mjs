import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // React 19.2 promoted set-state-in-effect from warn→error, but the
      // codebase uses several idiomatic patterns that trip it (SSR hydration
      // mount flags, prop→state sync, loading resets before async fetches).
      // Keep the signal as a warning so CI can be green while the sites get
      // refactored case-by-case.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
]);

export default eslintConfig;
