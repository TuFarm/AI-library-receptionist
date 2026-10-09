import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // Extra hostnames the dev server accepts (e.g. a Cloudflare tunnel), comma-separated in .env.
  const allowedHosts = (loadEnv(mode, process.cwd(), "").DEV_ALLOWED_HOSTS ?? "")
    .split(",").map((host) => host.trim()).filter(Boolean);
  return {
    plugins: [react()],
    base: "/",
    server: {
      host: "0.0.0.0",
      port: 5173,
      allowedHosts,
      proxy: {
        "/api": "http://localhost:8000",
      },
    },
  };
});
