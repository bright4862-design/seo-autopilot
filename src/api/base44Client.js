import { createClient } from '@base44/sdk';
import { appParams } from '@/lib/app-params';

const { appId, token, apiKey, functionsVersion, appBaseUrl } = appParams;

const headers = apiKey ? { api_key: apiKey } : undefined;

// Create a client with authentication required.
// API keys should come from environment variables or runtime params, never committed source.
export const base44 = createClient({
  appId,
  token,
  headers,
  functionsVersion,
  serverUrl: '',
  requiresAuth: false,
  appBaseUrl
});
