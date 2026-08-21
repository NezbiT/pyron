import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    origin: "http://127.0.0.1:5173",
  },
  build: {
    manifest: true,
    outDir: "dist",
    rollupOptions: { input: "src/main.js" },
  },
});
