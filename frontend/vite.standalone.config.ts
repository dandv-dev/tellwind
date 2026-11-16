// Builds the downloadable brief: the Brief tab's components compiled into one
// self-contained HTML file. The backend fills in <!--BRIEF_DATA--> per run.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile({ removeViteModuleLoader: true })],
  publicDir: false,
  build: {
    outDir: "dist",
    emptyOutDir: false,
    rollupOptions: { input: "brief-template.html" },
    assetsInlineLimit: 100_000_000,
  },
});
