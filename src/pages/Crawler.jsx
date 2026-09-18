import React from "react";

export default function Crawler() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-16 text-slate-900">
      <a href="/" className="text-blue-700 underline">FixList</a>
      <h1 className="text-3xl font-bold">About the FixList crawler</h1>
      <p>FixList checks public website pages to produce an evidence-based SEO repair list. Standard 150 checks up to 150 pages; discovery and validation can make additional bounded requests.</p>
      <h2 className="text-xl font-semibold">Crawler identity</h2>
      <p>Our published crawler identity is:</p>
      <code className="block break-all rounded bg-slate-100 p-4">FixListBot/1.0 (+https://getfixlist.com/crawler)</code>
      <h2 className="text-xl font-semibold">Robots and access protection</h2>
      <p>FixList respects robots.txt by default. Only a customer who attests that they own or manage the site can authorize an override for their scan. Search-engine indexability evidence still reflects the actual robots directives.</p>
      <p>The robots token is FixListBot. Restrictions for the previous FixListPythonScanner identity are also preserved. FixList does not solve CAPTCHAs, impersonate search engines or browsers, or bypass login and firewall protection. Challenged content is not treated as a successful SEO result.</p>
      <h2 className="text-xl font-semibold">If your security service blocks a scan</h2>
      <p>Ask your hosting or security provider to inspect the blocked requests using the scan time, domain, and crawler identity. Request a narrowly scoped, temporary exception only after verifying the request source. Do not disable your firewall or allow all Google Cloud addresses.</p>
      <p>A user-agent is not authentication: anyone can copy it. FixList does not currently publish a verified static outbound-IP allowlist. Ask your provider what source verification they require before creating an exception, then run a new scan after access is confirmed.</p>
    </main>
  );
}
