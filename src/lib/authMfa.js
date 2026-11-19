import { appParams } from '@/lib/app-params';
import { base44 } from '@/api/base44Client';

function authPath(suffix) {
  if (!/^[a-f0-9]{24}$/i.test(appParams.appId)) throw new Error('Invalid app ID');
  return `/api/apps/${appParams.appId}/auth/${suffix}`;
}

async function post(suffix, body, token) {
  const response = await fetch(authPath(suffix), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || result.detail || 'Unable to sign in');
  return result;
}

export async function loginWithMfa(email, password) {
  const result = await post('login', { email, password });
  if (result.access_token) base44.auth.setToken(result.access_token);
  return result;
}

export async function continueMfa(result, returnTo) {
  const encode = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const verifier = encode(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = encode(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  const { code } = await post('mfa/handoff', { code_challenge: challenge }, result.mfa_session_token);
  sessionStorage.setItem(`app-mfa-pkce:${appParams.appId}`, verifier);
  const url = new URL('/auth/mfa', window.location.origin);
  url.search = new URLSearchParams({ app_id: appParams.appId, mfa_code: code, from_url: returnTo });
  window.location.assign(url.href);
}

// provider: 'google' | 'microsoft' | 'facebook' | 'apple'
export async function loginWithSocial(provider, returnTo) {
  const response = await fetch(`/api/apps/public/login-info/by-id/${appParams.appId}`);
  if (!response.ok) throw new Error('Unable to load sign-in options');
  const info = await response.json();
  if (info.auth_config?.mfa_policy !== 'required') return base44.auth.loginWithProvider(provider, returnTo);
  const url = new URL('/auth/mfa', window.location.origin);
  url.search = new URLSearchParams({ app_id: appParams.appId, oauth_start: provider, from_url: returnTo });
  window.location.assign(url.href);
}

export function loginWithGoogle(returnTo) {
  return loginWithSocial('google', returnTo);
}
