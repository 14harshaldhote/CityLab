import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.CITYLAB_API ?? "http://127.0.0.1:8000", ws: true } },
  },
  test: { environment: "node" },
});
