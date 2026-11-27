import base44 from "@base44/vite-plugin"
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// This private preview rebuilds the named pilot frontend from merged source.
const pilotBuild = {
  VITE_BASE44_APP_ID: "6a498732ec779dfaaeab0e53",
  VITE_FIXLIST_SOURCE_SHA: "bba9570b9047b1a109ac6a52a630eaf2f4335514",
  VITE_SCAN_FUNCTION_GENERATION: "PUBLISHED_PILOT",
}
for (const [name, value] of Object.entries(pilotBuild)) {
  if (process.env[name] && process.env[name] !== value) throw new Error("Conflicting pilot build identity: " + name)
  process.env[name] = value
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    base44({
      // Support for legacy code that imports the base44 SDK with @/integrations, @/entities, etc.
      // can be removed if the code has been updated to use the new SDK imports from @base44/sdk
      legacySDKImports: process.env.BASE44_LEGACY_SDK_IMPORTS === 'true',
      hmrNotifier: true,
      navigationNotifier: true,
      analyticsTracker: true,
      visualEditAgent: true
    }),
    react(),
  ]
});
