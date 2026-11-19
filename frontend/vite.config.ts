import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5180,
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8010",
        changeOrigin: false,
        // API desligada: responde 502 como a Vercel faz em produção (o padrão do Vite seria 500).
        configure: (proxy) => {
          proxy.on("error", (_err, _req, res) => {
            if ("writeHead" in res && !res.headersSent) {
              res.writeHead(502, { "Content-Type": "text/plain" });
              res.end("Bad Gateway");
            }
          });
        },
      },
    },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "wouter"],
          data: ["@tanstack/react-query", "react-hook-form", "zod", "@hookform/resolvers"],
        },
      },
    },
  },
});
