import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Lock, Mail } from "lucide-react";
import GoogleIcon from "@/components/GoogleIcon";
import MfaFlow from "@/components/MfaFlow";
import MfaManage from "@/components/MfaManage";
import { MfaHeader, MfaNotice, MfaScreen, useAppInfo } from "@/components/MfaParts";
import { finishSignIn, resumeMfa, signInToManageMfa, signInWithProvider } from "@/lib/authMfaFlow";
import { safeReturnTo } from "@/lib/authReturnTo";

const PROVIDERS = [
  { id: "google", flag: "enable_google_login", name: "Google" },
  { id: "microsoft", flag: "enable_microsoft_login", name: "Microsoft" },
  { id: "facebook", flag: "enable_facebook_login", name: "Facebook" },
  { id: "apple", flag: "enable_apple_login", name: "Apple" },
];

// /mfa: finishes a Google, Microsoft, Facebook, Apple or SSO sign-in that needs a second step
// (?mfa_code=…), and opened directly it is the two-factor authentication settings page.
export default function Mfa() {
  const returnTo = safeReturnTo();
  const [challenge, setChallenge] = useState(null);
  const [managing, setManaging] = useState(null);
  const [resuming, setResuming] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    resumeMfa()
      .then((result) => {
        // A remembered device signs in straight away; otherwise continue the second step here.
        if (result?.access_token) return finishSignIn(result.access_token, returnTo);
        if (result) setChallenge(result);
        setResuming(false);
      })
      .catch((err) => { setError(err); setResuming(false); });
  }, []);

  if (resuming) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }
  return (
    <MfaScreen>
      {managing ? <MfaManage session={managing} returnTo={returnTo} />
        : challenge ? <MfaFlow challenge={challenge} returnTo={returnTo} onManage={setManaging} />
        : <ConfirmIdentity returnTo={returnTo} onChallenge={setChallenge} initialError={error} />}
    </MfaScreen>
  );
}

// Changing two-factor settings starts with a fresh sign-in, then a code from an enrolled method.
function ConfirmIdentity({ returnTo, onChallenge, initialError }) {
  const info = useAppInfo();
  const options = info ? info.auth_config || {} : null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      onChallenge(await signInToManageMfa(email, password));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  const withProvider = (provider) => signInWithProvider(provider, returnTo, { manage: true }).catch(setError);
  const providers = options ? PROVIDERS.filter((provider) => options[provider.flag] ?? provider.id === "google") : [];

  return (
    <>
      <MfaHeader title={info && `Welcome to ${info.name || "the app"}`} description="Sign in to continue" />
      <MfaNotice error={error} />
      {!options && !error && <Loader2 className="mx-auto w-6 h-6 animate-spin text-muted-foreground" />}
      {options && (
        <div className="space-y-4">
          {providers.map((provider) => (
            <Button key={provider.id} variant="outline" className="w-full h-12 text-sm font-medium" onClick={() => withProvider(provider.id)}>
              {provider.id === "google" && <GoogleIcon className="w-5 h-5 mr-2" />}
              Continue with {provider.name}
            </Button>
          ))}
          {(options.enable_sso_login || options.use_workspace_sso) && (
            <Button variant="outline" className="w-full h-12 text-sm font-medium" onClick={() => withProvider("sso")}>
              Continue with SSO
            </Button>
          )}
          {options.enable_username_password && (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="mfa-email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
                  <Input id="mfa-email" type="email" autoComplete="email" placeholder="you@example.com" value={email}
                    onChange={(e) => setEmail(e.target.value)} className="pl-10 h-12" required />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="mfa-password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
                  <Input id="mfa-password" type="password" autoComplete="current-password" placeholder="••••••••" value={password}
                    onChange={(e) => setPassword(e.target.value)} className="pl-10 h-12" required />
                </div>
              </div>
              <Button type="submit" className="w-full h-12 font-medium" disabled={busy}>
                {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Continue
              </Button>
            </form>
          )}
        </div>
      )}
    </>
  );
}
