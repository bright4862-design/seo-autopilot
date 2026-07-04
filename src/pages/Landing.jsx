import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Zap, Search, ArrowRight, CheckCircle2, Shield, BarChart3,
  ArrowRightLeft, Globe, Code, FileText, AlertTriangle, Star,
  ChevronDown, Users, TrendingUp
} from "lucide-react";

const features = [
  { icon: Zap, title: "AI Meta Titles", desc: "We write search-friendly titles for every page on your site." },
  { icon: FileText, title: "AI Meta Descriptions", desc: "Click-worthy descriptions that make people choose you in Google." },
  { icon: AlertTriangle, title: "404 Error Detection", desc: "Find and fix broken pages before they cost you customers." },
  { icon: ArrowRightLeft, title: "Redirect Recommendations", desc: "Smart redirect suggestions so no visitor hits a dead end." },
  { icon: Shield, title: "Canonical Tag Checks", desc: "Stop Google from getting confused about duplicate pages." },
  { icon: Globe, title: "Sitemap Cleanup", desc: "Keep your sitemap clean so Google finds your best pages." },
  { icon: Code, title: "JavaScript Page Checks", desc: "Make sure Google can see content loaded by JavaScript." },
  { icon: BarChart3, title: "Competitor Benchmarking", desc: "See exactly why competitors outrank you — and how to catch up." },
  { icon: TrendingUp, title: "Dev Recommendations", desc: "Clear instructions for web development work that boosts rankings." },
];

const plans = [
  { name: "Free Scan", price: "Free", period: "", desc: "See what's wrong", features: ["One-time homepage scan", "Top 5 issues found", "Competitor teaser", "Upgrade to fix everything"], cta: "Run Free Scan", highlighted: false },
  { name: "DIY SEO Autopilot", price: "$20", period: "/month", desc: "Fix it yourself", features: ["Monthly full-site crawl", "Up to 250 pages", "AI meta titles & descriptions", "404 detection & redirects", "Canonical & sitemap checks", "3 competitor benchmarks", "Monthly SEO report"], cta: "Start DIY Plan", highlighted: true },
  { name: "Growth", price: "$49", period: "/month", desc: "Grow faster", features: ["Weekly crawl", "Up to 1,000 pages", "100 JS-rendered pages", "5 competitor benchmarks", "Priority recommendations", "Google Search Console (coming soon)", "Everything in DIY"], cta: "Start Growth Plan", highlighted: false },
];

const faqs = [
  { q: "How does the crawler work?", a: "We scan your website just like Google does — checking every page for SEO issues, broken links, missing metadata, and more. We also render JavaScript pages to catch hidden problems." },
  { q: "Will this break my website?", a: "Absolutely not. We only scan and analyze your site. We never make changes to your website directly. All fixes are recommendations that you approve first." },
  { q: "Do I need to know SEO?", a: "Not at all. We explain everything in plain English. Our AI does the technical work and tells you exactly what to do in words anyone can understand." },
  { q: "What if I need a developer?", a: "We clearly separate 'easy fixes' from 'needs a developer.' For developer work, we provide clear instructions and offer implementation packages starting at $500." },
  { q: "Can I cancel anytime?", a: "Yes. No contracts, no commitments. Cancel your subscription anytime from your dashboard." },
];

export default function Landing() {
  const [openFaq, setOpenFaq] = useState(null);

  return (
    <div className="min-h-screen bg-white">
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-white/80 backdrop-blur-xl border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">SEO Autopilot</span>
          </Link>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-600">
            <a href="#features" className="hover:text-gray-900 transition-colors">Features</a>
            <a href="#pricing" className="hover:text-gray-900 transition-colors">Pricing</a>
            <a href="#faq" className="hover:text-gray-900 transition-colors">FAQ</a>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login">
              <Button variant="ghost" size="sm">Log in</Button>
            </Link>
            <Link to="/register">
              <Button size="sm" className="gradient-primary text-white border-0">Get Started</Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 text-xs font-medium mb-6">
            <Zap className="w-3.5 h-3.5" />
            AI-Powered SEO for Small Business
          </div>
          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-gray-900 leading-tight mb-6">
            AI SEO fixes for<br />
            <span className="gradient-text">small business websites</span>
          </h1>
          <p className="text-lg md:text-xl text-gray-500 max-w-2xl mx-auto mb-10 leading-relaxed">
            We crawl your site, fix the easy SEO issues, recommend redirects, clean up sitemap problems, and show what web-development work would help you compete.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/register">
              <Button size="lg" className="gradient-primary text-white border-0 text-base px-8 h-12 w-full sm:w-auto">
                Run My First Scan
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <Link to="/register">
              <Button size="lg" variant="outline" className="text-base px-8 h-12 w-full sm:w-auto">
                See Demo Report
              </Button>
            </Link>
          </div>
          <div className="flex items-center justify-center gap-6 mt-8 text-sm text-gray-400">
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> Free scan included</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> No credit card needed</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> Results in minutes</span>
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="py-12 border-y border-gray-100 bg-gray-50/50">
        <div className="max-w-5xl mx-auto px-4">
          <p className="text-center text-sm text-gray-400 mb-6">Trusted by small businesses across the country</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 items-center justify-items-center">
            {["850+ sites scanned", "12,000+ issues fixed", "4.9★ average rating", "93% renewal rate"].map(stat => (
              <div key={stat} className="text-center">
                <p className="text-lg font-bold text-gray-900">{stat.split(" ")[0]}</p>
                <p className="text-xs text-gray-500">{stat.split(" ").slice(1).join(" ")}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Everything your site needs to rank</h2>
            <p className="text-gray-500 text-lg max-w-2xl mx-auto">We handle the technical SEO work so you can focus on running your business.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map(f => (
              <div key={f.title} className="p-6 rounded-2xl border border-gray-100 hover:border-blue-100 hover:shadow-lg hover:shadow-blue-50 transition-all duration-300 group">
                <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center mb-4 group-hover:bg-blue-100 transition-colors">
                  <f.icon className="w-5 h-5 text-blue-600" />
                </div>
                <h3 className="font-semibold text-gray-900 mb-2">{f.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-20 px-4 bg-gray-50/50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">How it works</h2>
            <p className="text-gray-500 text-lg">Three steps to better SEO. No expertise required.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "1", title: "Connect your site", desc: "Enter your website URL and basic business info. Takes about 2 minutes." },
              { step: "2", title: "We scan & fix", desc: "Our AI crawls your site, finds issues, and automatically fixes the easy ones." },
              { step: "3", title: "Approve & grow", desc: "Review recommendations, approve fixes, and get clear developer instructions for the rest." },
            ].map(s => (
              <div key={s.step} className="text-center">
                <div className="w-12 h-12 rounded-2xl gradient-primary text-white font-bold text-lg flex items-center justify-center mx-auto mb-4">{s.step}</div>
                <h3 className="font-semibold text-gray-900 mb-2">{s.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">What business owners say</h2>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { name: "Sarah M.", biz: "Denver Dental Care", quote: "I had no idea my site had so many broken links. SEO Autopilot found and fixed them in minutes. My traffic is up 30% in two months." },
              { name: "James K.", biz: "Peak Roofing Co", quote: "The competitor analysis alone was worth the subscription. I could see exactly why other roofers were outranking me." },
              { name: "Maria L.", biz: "Sunrise Bakery", quote: "Finally an SEO tool that speaks my language. No jargon, no confusion — just clear steps to improve my Google rankings." },
            ].map(t => (
              <div key={t.name} className="p-6 rounded-2xl bg-white border border-gray-100 shadow-sm">
                <div className="flex gap-1 mb-3">
                  {[1,2,3,4,5].map(i => <Star key={i} className="w-4 h-4 fill-amber-400 text-amber-400" />)}
                </div>
                <p className="text-sm text-gray-600 mb-4 leading-relaxed">"{t.quote}"</p>
                <div>
                  <p className="font-semibold text-sm text-gray-900">{t.name}</p>
                  <p className="text-xs text-gray-400">{t.biz}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20 px-4 bg-gray-50/50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Simple, transparent pricing</h2>
            <p className="text-gray-500 text-lg">Start free. Upgrade when you're ready.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {plans.map(p => (
              <div key={p.name} className={`p-6 rounded-2xl border ${p.highlighted ? "border-blue-200 bg-white shadow-xl shadow-blue-50 ring-2 ring-blue-100" : "border-gray-100 bg-white"} flex flex-col`}>
                {p.highlighted && <span className="text-xs font-semibold text-blue-600 mb-2">Most Popular</span>}
                <h3 className="font-bold text-lg text-gray-900">{p.name}</h3>
                <p className="text-sm text-gray-500 mb-4">{p.desc}</p>
                <div className="mb-6">
                  <span className="text-3xl font-extrabold text-gray-900">{p.price}</span>
                  <span className="text-sm text-gray-400">{p.period}</span>
                </div>
                <ul className="space-y-2.5 mb-8 flex-1">
                  {p.features.map(f => (
                    <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                      <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link to="/register">
                  <Button className={`w-full ${p.highlighted ? "gradient-primary text-white border-0" : ""}`} variant={p.highlighted ? "default" : "outline"}>
                    {p.cta}
                  </Button>
                </Link>
              </div>
            ))}
          </div>
          <div className="mt-8 text-center">
            <p className="text-sm text-gray-400">Need more? We offer Done-for-You SEO cleanup from $500 and custom website rebuilds. <Link to="/billing" className="text-blue-600 hover:underline">See all plans</Link></p>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-20 px-4">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Frequently asked questions</h2>
          </div>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div key={i} className="border border-gray-100 rounded-xl overflow-hidden">
                <button onClick={() => setOpenFaq(openFaq === i ? null : i)} className="w-full flex items-center justify-between p-4 text-left text-sm font-medium text-gray-900 hover:bg-gray-50 transition-colors">
                  {faq.q}
                  <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${openFaq === i ? "rotate-180" : ""}`} />
                </button>
                {openFaq === i && (
                  <div className="px-4 pb-4 text-sm text-gray-500 leading-relaxed">{faq.a}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4 bg-gray-900">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Ready to fix your SEO?</h2>
          <p className="text-gray-400 text-lg mb-8">Start with a free scan. See what's holding your site back in minutes.</p>
          <Link to="/register">
            <Button size="lg" className="gradient-primary text-white border-0 text-base px-8 h-12">
              Run My First Scan — It's Free
              <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 border-t border-gray-100">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md gradient-primary flex items-center justify-center">
              <Zap className="w-3 h-3 text-white" />
            </div>
            <span className="font-semibold text-sm">SEO Autopilot</span>
          </div>
          <p className="text-xs text-gray-400">© 2026 SEO Autopilot. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}