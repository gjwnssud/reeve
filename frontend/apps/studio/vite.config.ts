import path from "node:path";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

const BACKEND = process.env.STUDIO_BACKEND_URL ?? "http://studio:8000";

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
    port: 5173,
    strictPort: true,
    hmr: { clientPort: 5173 },
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/admin": { target: BACKEND, changeOrigin: true },
      "/finetune": { target: BACKEND, changeOrigin: true },
      "/data": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../../../static"),
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
          "router-vendor": ["react-router", "react-router-dom"],
          "query-vendor": ["@tanstack/react-query"],
        },
      },
    },
  },
});
