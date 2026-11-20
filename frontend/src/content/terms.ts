// Terms of Service. Keep "updated" in sync with any change; the page shows it at the top.
export const TERMS_UPDATED = "November 20, 2026";

// Fill these in before relying on the Terms (shown on the page until set).
export const GOVERNING_LAW: string | null = null; // e.g. "the State of Delaware"
export const VENUE: string | null = null;         // e.g. "New Castle County, Delaware"
export const LEGAL_EMAIL = "support@irradiance.ai";

export interface Section { id: string; title: string; blocks: (string | { list: string[] } | { caps: string })[] }

export const TERMS: Section[] = [
  { id: "agreement", title: "Agreement to these Terms", blocks: [
    "These Terms of Service (\"Terms\") govern your access to and use of irradiance.ai and the Irradiance.AI apps, research, data, tools and related services (the \"Services\"). By creating an account or using the Services you agree to these Terms, our Privacy Policy, Disclaimer and Community Guidelines, which are part of these Terms. If you do not agree, do not use the Services.",
  ] },
  { id: "no-advice", title: "1. Informational and educational purpose only (no investment advice)", blocks: [
    "Not financial advice. All content, market data, analytics, AI-generated outputs (including ValueBot valuations, quant ratings, buzz scores, screens, backtests and Monte Carlo simulations) and research provided through the Services are strictly for informational, research and educational purposes.",
    "No fiduciary relationship. Irradiance is not a registered broker-dealer, investment adviser, financial planner or tax adviser, and using the Services does not create an advisory, fiduciary or client relationship. Nothing on the Services is a solicitation, recommendation, endorsement or offer to buy or sell any security, cryptocurrency, commodity or other financial instrument, and nothing is tailored to your personal circumstances.",
    "Assumption of risk. Financial markets involve substantial risk, including the possible loss of principal. Past performance, backtests and simulations do not guarantee future results. You are solely responsible for evaluating the merits and risks of any information before making financial or investment decisions, and you should consult a licensed financial professional before doing so.",
  ] },
  { id: "eligibility", title: "2. Eligibility and accounts", blocks: [
    "You must be at least 18 years old (or the age of legal majority where you live) to use the Services.",
    "You agree to provide accurate, current and complete registration information, keep it up to date, and keep your password and any API keys confidential. You are responsible for all activity under your account. Tell us promptly at " + LEGAL_EMAIL + " if you believe your account has been compromised.",
    "Accounts are for one individual. You may not share, sell or transfer your account or membership.",
  ] },
  { id: "billing", title: "3. Subscriptions, free trials and billing", blocks: [
    "Payment processing. Paid memberships are processed by our third-party payment processor, Square. By subscribing you agree to Square's terms of service and privacy policy and authorize us, through Square, to charge your chosen payment method. We never see or store your full card number.",
    "Automatic renewal. Paid memberships renew automatically for the billing cycle you chose (monthly or annual) until cancelled. To avoid being charged for the next cycle, cancel from your account settings before your renewal date. Cancellation takes effect at the end of the current paid period, and you keep access until then.",
    "Free trials. Free trials do not convert to paid plans automatically. When a trial ends, your account returns to the Free plan unless you choose to subscribe. Each member may use one free trial.",
    "Refunds and price changes. Except where required by law, fees are non-refundable and we do not give prorated refunds for partial billing periods. We may change prices with reasonable advance notice; a new price applies from your next renewal after the notice.",
    "Taxes. Prices exclude any applicable sales, use or similar taxes, which are added where required.",
  ] },
  { id: "ip", title: "4. Intellectual property and market-data restrictions", blocks: [
    "Ownership. The software, algorithms, AI models, text, graphics, interfaces and proprietary research on the Services belong to Irradiance or its licensors and are protected by copyright, trademark and other laws.",
    "Limited personal licence. Subject to these Terms, we grant you a limited, non-exclusive, non-transferable, revocable licence to access and use the Services and the market data shown in them for your own personal, non-commercial research and education. Downloads such as ValueBot PDF reports and Excel models are covered by the same licence.",
    "Without our prior written permission, you may not:",
    { list: [
      "redistribute, resell, sublicense, publish, broadcast or commercially exploit any market data, analytics or research obtained from the Services;",
      "use bots, scrapers, spiders or other automated tools to extract data from the Services (the read-only API keys offered to Pro members, used within their documented limits, are permitted);",
      "use content or outputs from the Services to train, fine-tune or develop competing artificial-intelligence or machine-learning models; or",
      "remove or obscure source labels, disclaimers or proprietary notices.",
    ] },
    "Market data is supplied by third parties and may be subject to their own terms, including exchange rules on professional and non-professional use. If you use the Services for a business or as a market professional, contact us before doing so.",
  ] },
  { id: "your-content", title: "5. Content you post", blocks: [
    "You keep ownership of the analysis, comments, trade ideas and other content you post. You grant Irradiance a worldwide, non-exclusive, royalty-free licence to host, display, reproduce and distribute that content in connection with operating and promoting the Services.",
    "You are responsible for your content. It must be your own or used with permission, must disclose any position you hold in securities you discuss, and must not be promotional material you have been paid to publish without disclosure. Trade posts record platform prices at the time of posting and cannot be edited after publication.",
    "We may remove content and act on accounts that breach these Terms or the Community Guidelines. Moderation actions are logged and can be appealed by writing to " + LEGAL_EMAIL + ".",
  ] },
  { id: "acceptable-use", title: "6. Acceptable use, suspension and termination", blocks: [
    "You agree to follow the Community Guidelines and all applicable laws. You may not use the Services to harass others, distribute malware, manipulate markets (including pump-and-dump schemes or coordinated campaigns), impersonate anyone, or attempt to bypass security, rate limits or access controls.",
    "We may suspend, restrict or terminate your account, with or without notice, if you breach these Terms or the Community Guidelines, or if your conduct harms Irradiance, our data providers or other members. You may close your account at any time from your account settings or by contacting us.",
  ] },
  { id: "third-party", title: "7. Third-party data and AI output disclaimers", blocks: [
    "Data accuracy. Market data, filings and news come from sources believed to be reliable, but we do not guarantee their accuracy, completeness, timeliness or availability. Data may be delayed, interrupted or wrong. Every figure is labelled with its source (for example LIVE, EOD, STALE or DEMO); placeholder DEMO data is never real market data.",
    "AI limitations. Features that use artificial intelligence or statistical models are probabilistic and may produce inaccurate, incomplete or outdated outputs. Independently verify any AI-generated research before relying on it.",
    "Third-party services and links (for example TradingView charts, SEC EDGAR and news sources) are provided for convenience and governed by their own terms; we are not responsible for them.",
  ] },
  { id: "warranties", title: "8. Disclaimer of warranties", blocks: [
    { caps: "THE SERVICES AND ALL CONTENT ARE PROVIDED \"AS IS\" AND \"AS AVAILABLE\" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED. TO THE FULLEST EXTENT PERMITTED BY LAW, IRRADIANCE DISCLAIMS ALL WARRANTIES, INCLUDING IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT AND ACCURACY. WE DO NOT WARRANT THAT THE SERVICES WILL BE UNINTERRUPTED, SECURE OR ERROR-FREE." },
  ] },
  { id: "liability", title: "9. Limitation of liability", blocks: [
    { caps: "TO THE MAXIMUM EXTENT PERMITTED BY LAW, IN NO EVENT WILL IRRADIANCE, ITS FOUNDERS, DIRECTORS, EMPLOYEES, AFFILIATES OR DATA PROVIDERS BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL OR PUNITIVE DAMAGES, INCLUDING LOSS OF PROFITS, TRADING LOSSES, LOSS OF DATA OR GOODWILL, ARISING OUT OF OR RELATING TO YOUR USE OF, OR INABILITY TO USE, THE SERVICES." },
    { caps: "IRRADIANCE'S TOTAL AGGREGATE LIABILITY FOR ALL CLAIMS RELATING TO THE SERVICES WILL NOT EXCEED THE GREATER OF (A) THE AMOUNT YOU PAID IRRADIANCE IN THE TWELVE (12) MONTHS BEFORE THE EVENT GIVING RISE TO LIABILITY, OR (B) ONE HUNDRED U.S. DOLLARS (US$100)." },
    "Some jurisdictions do not allow certain exclusions or limitations, so some of the above may not apply to you.",
  ] },
  { id: "indemnity", title: "10. Indemnification", blocks: [
    "You agree to defend, indemnify and hold harmless Irradiance and its affiliates, officers, agents and licensors from any claims, liabilities, damages, losses and expenses (including reasonable attorneys' fees) arising from: (a) your access to or use of the Services; (b) your breach of these Terms or the Community Guidelines; (c) content you post; or (d) your unauthorized redistribution of market data or infringement of anyone else's rights.",
  ] },
  { id: "changes", title: "11. Changes to the Services and these Terms", blocks: [
    "We may modify, suspend or discontinue any part of the Services at any time. We may update these Terms by posting the revised version on this page and changing the \"Last updated\" date; for material changes we will also notify members by email or in the app. Continued use after changes take effect means you accept the revised Terms.",
  ] },
  { id: "law", title: "12. Governing law and disputes", blocks: [
    "These Terms are governed by the laws of {LAW}, without regard to conflict-of-law principles. Any dispute arising under these Terms will be resolved exclusively in the state or federal courts located in {VENUE}, and you consent to the personal jurisdiction of those courts.",
    "If any provision is found unenforceable, the rest remains in effect. Our failure to enforce a provision is not a waiver. You may not assign these Terms; we may assign them in connection with a merger, acquisition or sale of assets. These Terms are the entire agreement between you and Irradiance about the Services.",
  ] },
  { id: "contact", title: "13. Contact", blocks: [
    "Questions about these Terms, or requests for written permission for commercial data use: " + LEGAL_EMAIL + " · irradiance.ai",
  ] },
];
