// Lightweight stub for @arrow-js/sandbox used in tests.
// Prevents loading quickjs-emscripten (2MB WASM) + TypeScript compiler.
export const sandbox = () => (parent: ParentNode): ParentNode => parent;
