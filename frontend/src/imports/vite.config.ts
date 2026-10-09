import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/process-incident": "http://127.0.0.1:8000",
      "/clarify": "http://127.0.0.1:8000",
      "/review": "http://127.0.0.1:8000",
      "/incident": "http://127.0.0.1:8000",
      "/pending-reviews": "http://127.0.0.1:8000",
      "/incidents": "http://127.0.0.1:8000",
      "/dashboard-summary": "http://127.0.0.1:8000"
    }
  },
  build: {
    outDir: path.resolve(__dirname, "../static"),
    emptyOutDir: true,
  }
})
