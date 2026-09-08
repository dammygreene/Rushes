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
      // Third-party thumbnails are hotlinked with a plain <img> on purpose:
      // routing them through next/image would cache other people's media on
      // our servers, which is exactly what this project promises not to do.
      "@next/next/no-img-element": "off",
    },
  },
]);

export default eslintConfig;
