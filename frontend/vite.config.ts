import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev/preview server binds inside the container; the host only exposes it on
// 127.0.0.1 via docker-compose. Port is overridable via FRONTEND_PORT.
const port = Number(process.env.FRONTEND_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
  server: { host: true, port },
  preview: { host: true, port },
});
