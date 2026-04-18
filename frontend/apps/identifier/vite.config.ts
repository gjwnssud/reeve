import path from "node:path";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

const BACKEND = process.env.IDENTIFIER_BACKEND_URL ?? "http://identifier:8001";

export default defineConfig({
  base: "/static/",
  plugins: [react(), tsconfigPaths()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5174,
    strictPort: true,
    hmr: { clientPort: 5174 },
    proxy: {
      "/detect": { target: BACKEND, changeOrigin: true },
      "/identify": { target: BACKEND, changeOrigin: true },
      "/async": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
      "/admin": { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../../../identifier/static"),
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
          "query-vendor": ["@tanstack/react-query"],
        },
      },
    },
  },
});
