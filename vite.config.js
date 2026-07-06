import base44 from "@base44/vite-plugin"
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

function seoAutopilotScanBudgetPatch() {
  return {
    name: 'seo-autopilot-scan-budget-patch',
    enforce: 'pre',
    transform(code, id) {
      const normalizedId = id.replace(/\\/g, '/')

      if (!normalizedId.endsWith('/src/components/scan/ScanWebsiteForm.jsx')) {
        return null
      }

      return code
        .replace('description: "Fast first scan. Up to 25 pages."', 'description: "Fast first scan. Up to 40 pages."')
        .replace('description: "Best default scan. Up to 60 pages."', 'description: "Best default scan. Up to 85 pages."')
        .replace(
          'max_pages: 25,\n    max_competitors: 0,\n    max_browser_render_attempts: 1,\n    crawl_timeout_ms: 30000,',
          'max_pages: 40,\n    max_competitors: 0,\n    max_browser_render_attempts: 1,\n    crawl_timeout_ms: 45000,'
        )
        .replace(
          'max_pages: 60,\n      max_competitors: 0,\n      max_browser_render_attempts: 1,\n      crawl_timeout_ms: 50000,',
          'max_pages: 85,\n      max_competitors: 0,\n      max_browser_render_attempts: 1,\n      crawl_timeout_ms: 75000,'
        )
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    seoAutopilotScanBudgetPatch(),
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
