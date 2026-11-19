import React, { useEffect, useRef, useState } from "react";
import { Check, ChevronsUpDown, Copy, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { loadSignInOptions } from "@/lib/authMfaFlow";
import { safeReturnTo } from "@/lib/authReturnTo";

// Building blocks shared by MfaFlow, MfaMethodSetup and MfaManage.

let appInfo;

// The app's name and sign-in settings, as login-info reports them.
export function useAppInfo() {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    appInfo ||= loadSignInOptions().catch(() => ({}));
    appInfo.then((value) => setInfo(value || {}));
  }, []);
  return info;
}

// A whole page holding one MFA card. MfaFlow and MfaManage are card content, so a page that
// shows them returns <MfaScreen> in place of its own layout instead of nesting them in its card.
export function MfaScreen({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-8">
      <div className="w-full max-w-md bg-card rounded-2xl shadow-sm border border-border p-8">{children}</div>
    </div>
  );
}

// An icon, a title and a description, then the step's controls. A title that waits for the app's
// name is null until it loads, so the right text appears once instead of replacing a placeholder.
export function MfaHeader({ title, description }) {
  return (
    <div className="flex flex-col items-center text-center mb-6">
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary mb-4">
        <ShieldCheck className="w-7 h-7 text-primary-foreground" aria-hidden="true" />
      </div>
      <h1 className="text-2xl font-bold tracking-tight text-foreground min-h-[2rem]">{title}</h1>
      {description && <p className="text-muted-foreground mt-2">{description}</p>}
    </div>
  );
}

// Six digits. Like the built-in code box, any change that leaves six digits, a paste over a full code
// included, and the Enter key both call onComplete with the code as it stands.
export function CodeField({ id, label = "Enter the 6-digit code", value, onChange, onComplete, hasError = false }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id} className="block text-center font-normal text-muted-foreground">{label}</Label>
      <InputOTP id={id} maxLength={6} value={value} autoFocus autoComplete="one-time-code" containerClassName="justify-center"
        onChange={(next) => { onChange(next); if (next.length === 6) onComplete?.(next); }}
        onKeyDown={(e) => { if (e.key === "Enter" && onComplete) { e.preventDefault(); onComplete(value); } }}>
        <InputOTPGroup>
          {[0, 1, 2, 3, 4, 5].map((index) => (
            <InputOTPSlot key={index} index={index} className={hasError ? "border-destructive" : undefined} />
          ))}
        </InputOTPGroup>
      </InputOTP>
    </div>
  );
}

// "Didn't receive a code? Resend", counting down while a resend isn't allowed yet.
export function ResendLine({ cooldown, disabled, onResend, error }) {
  return (
    <div className="space-y-1 text-center">
      <p className="text-sm text-muted-foreground">
        Didn't receive a code?{" "}
        {cooldown > 0 ? (
          <span>Resend in {cooldown}s</span>
        ) : (
          <button type="button" disabled={disabled} onClick={onResend} className="font-semibold text-foreground hover:underline disabled:opacity-50">
            Resend
          </button>
        )}
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

// ---- Phone number entry: the built-in screen's country picker and checks, without a phone-number library.

export const INVALID_PHONE = "Invalid phone number. Please check the number and try again.";

// Dial code of every country (iso2 + digits), from country-telephone-data, which the built-in picker lists.
const COUNTRY_DIAL_CODES = new Map(
  "af93 ax358 al355 dz213 as1684 ad376 ao244 ai1264 aq672 ag1268 ar54 am374 aw297 au61 at43 az994 bs1242 bh973 bd880 bb1246 by375 be32 bz501 bj229 bm1441 bt975 bo591 ba387 bw267 bv47 br55 io246 vg1284 bn673 bg359 bf226 bi257 kh855 cm237 ca1 cv238 bq599 ky1345 cf236 td235 cl56 cn86 cx61 cc61 co57 km269 cd243 cg242 ck682 cr506 ci225 hr385 cu53 cw599 cy357 cz420 dk45 dj253 dm1767 do1 ec593 eg20 sv503 gq240 er291 ee372 et251 fk500 fo298 fj679 fi358 fr33 gf594 pf689 tf262 ga241 gm220 ge995 de49 gh233 gi350 gr30 gl299 gd1473 gp590 gu1671 gt502 gg44 gn224 gw245 gy592 ht509 hm672 hn504 hk852 hu36 is354 in91 id62 ir98 iq964 ie353 im44 il972 it39 jm1876 jp81 je44 jo962 kz7 ke254 ki686 xk383 kw965 kg996 la856 lv371 lb961 ls266 lr231 ly218 li423 lt370 lu352 mo853 mk389 mg261 mw265 my60 mv960 ml223 mt356 mh692 mq596 mr222 mu230 yt262 mx52 fm691 md373 mc377 mn976 me382 ms1664 ma212 mz258 mm95 na264 nr674 np977 nl31 nc687 nz64 ni505 ne227 ng234 nu683 nf672 kp850 mp1670 no47 om968 pk92 pw680 ps970 pa507 pg675 py595 pe51 ph63 pn64 pl48 pt351 pr1 qa974 re262 ro40 ru7 rw250 bl590 sh290 kn1869 lc1758 mf590 pm508 vc1784 ws685 sm378 st239 sa966 sn221 rs381 sc248 sl232 sg65 sx1721 sk421 si386 sb677 so252 za27 gs500 kr82 ss211 es34 lk94 sd249 sr597 sj47 sz268 se46 ch41 sy963 tw886 tj992 tz255 th66 tl670 tg228 tk690 to676 tt1868 tn216 tr90 tm993 tc1649 tv688 vi1340 ug256 ua380 ae971 gb44 us1 um1 uy598 uz998 vu678 va39 ve58 vn84 wf681 eh212 ye967 zm260 zw263".split(" ").map((entry) => [entry.slice(0, 2), entry.slice(2)]),
);
const DIAL_CODES = [...new Set(COUNTRY_DIAL_CODES.values())].sort((a, b) => Number(a) - Number(b));

// The dial code of the browser's region (en-DE → +49), else +1.
export function defaultDialCode() {
  const region = typeof navigator === "undefined" ? undefined : navigator.language.split("-")[1]?.toLowerCase();
  const dialCode = region && COUNTRY_DIAL_CODES.get(region);
  return dialCode ? `+${dialCode}` : "+1";
}

// The built-in screen asks libphonenumber whether the number is valid for its country. Here only the
// length E.164 allows is checked (the shortest real numbers have 7 digits in all, the longest 15); the
// server runs the full per-country check before any text is sent, and answers with the same message.
export function isPlausiblePhone(fullPhone) {
  const digits = fullPhone.replace(/\D/g, "");
  return digits.length >= 7 && digits.length <= 15;
}

const matchesSearch = (code, search) => {
  const normalized = search.replace(/\+/g, "");
  return normalized === "" || code.startsWith(normalized);
};

// A searchable list of dial codes. Typing narrows it, and closing it with one match left picks that one.
function DialCodePicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const search = useRef("");

  const handleOpenChange = (next) => {
    if (!next && search.current) {
      const matches = DIAL_CODES.filter((code) => matchesSearch(code, search.current));
      if (matches.length === 1) onChange(`+${matches[0]}`);
      search.current = "";
    }
    setOpen(next);
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange} modal>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" role="combobox" aria-expanded={open} aria-label="Country code"
          className="h-10 w-[100px] justify-between px-2.5 font-normal shadow-none">
          {value}
          <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 opacity-50" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[140px] p-0" align="start" side="bottom" avoidCollisions={false}>
        <Command filter={(item, text) => (matchesSearch(item, text) ? 1 : 0)}>
          <CommandInput placeholder="Search..." className="h-9" onValueChange={(text) => { search.current = text; }} />
          <CommandList>
            <CommandEmpty>No match</CommandEmpty>
            <CommandGroup>
              {DIAL_CODES.map((code) => (
                <CommandItem key={code} value={code} onSelect={() => { onChange(`+${code}`); search.current = ""; setOpen(false); }}>
                  +{code}
                  <Check className={cn("ml-auto h-3.5 w-3.5", value === `+${code}` ? "opacity-100" : "opacity-0")} aria-hidden="true" />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

// Dial code picker plus the number (digits only, 15 at most). Once 4 digits are in, a number that can't
// be real is flagged as you type; `error` (from a failed send) takes the place of that message.
export function PhoneField({ countryCode, onCountryCodeChange, phoneNumber, onPhoneNumberChange, error, onSubmit }) {
  const [touched, setTouched] = useState(false);
  const invalid = touched && phoneNumber.length >= 4 && !isPlausiblePhone(`${countryCode}${phoneNumber}`);
  const message = error ?? (invalid ? INVALID_PHONE : null);
  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <DialCodePicker value={countryCode} onChange={onCountryCodeChange} />
        <Input id="mfa-phone" type="tel" autoComplete="tel-national" autoFocus value={phoneNumber} maxLength={15}
          placeholder="5551234567" aria-invalid={Boolean(message)}
          onChange={(e) => { onPhoneNumberChange(e.target.value.replace(/\D/g, "")); setTouched(true); }}
          onKeyDown={(e) => { if (e.key === "Enter" && onSubmit) { e.preventDefault(); onSubmit(); } }}
          className={cn("h-10 flex-1", message && "border-destructive focus-visible:ring-destructive")} />
      </div>
      {message
        ? <p className="text-sm text-destructive">{message}</p>
        : <p className="text-sm text-muted-foreground">Standard message and data rates may apply.</p>}
    </div>
  );
}

// Copies the setup key: an icon next to the key, or with `wide` the full-width "Copy key" button used on phones.
export function CopyKeyButton({ text, wide = false }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text.replace(/\s/g, ""));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  if (wide) {
    return (
      <Button type="button" variant="outline" className="w-full h-11" onClick={copy}>
        {copied ? "Copied" : "Copy key"}
      </Button>
    );
  }
  return (
    <button type="button" onClick={copy} title="Copy to clipboard" aria-label="Copy to clipboard"
      className="inline-flex items-center justify-center rounded-md p-2 text-muted-foreground hover:text-foreground hover:bg-muted">
      {copied ? <Check className="w-4 h-4" aria-hidden="true" /> : <Copy className="w-4 h-4" aria-hidden="true" />}
    </button>
  );
}

// An expired or used-up challenge can't be retried: send the user back through sign-in
// (signInPath "/mfa" for factor management, whose sign-in lives on that page). The server's
// wording for that case already says "sign in again", so it is replaced, not repeated.
export function MfaNotice({ error, signInPath = "/login" }) {
  if (!error) return null;
  const returnTo = safeReturnTo();
  return (
    <div role="alert" className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm text-center">
      {error.mustSignInAgain ? (
        <>
          Your sign-in expired.{" "}
          <a href={signInPath + (returnTo !== "/" ? "?returnTo=" + encodeURIComponent(returnTo) : "")} className="font-medium underline">
            Sign in again
          </a>
        </>
      ) : (error.message || "Verification failed. Please try again.")}
    </div>
  );
}

export function RememberDevice({ checked, onChange }) {
  return (
    <label className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
      <input type="checkbox" className="h-4 w-4 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      Remember this device for 30 days
    </label>
  );
}

// Seconds left before another text message can be sent.
export function useCooldown() {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (left <= 0) return undefined;
    const timer = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(timer);
  }, [left]);
  return [left, setLeft];
}

// Phones and tablets run the authenticator app on this device, so a QR code can't be scanned.
export function isTouchDevice() {
  return typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
}
