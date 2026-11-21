import type { Section } from "./terms";

export const PRIVACY_EFFECTIVE = "November 20, 2026";
export const PRIVACY_UPDATED = "November 20, 2026";
const EMAIL = "support@irradiance.ai";

export const PRIVACY: Section[] = [
  { id: "intro", title: "About this policy", blocks: [
    "Irradiance.AI (irradiance.ai; \"Irradiance\", \"we\", \"us\") respects your privacy. This Privacy Policy explains what personal data we collect, how we use and share it, and the choices you have when you visit the website, create an account, or use our research tools, data and AI-powered features (the \"Services\").",
    "By using the Services you acknowledge the practices described here. If you do not agree, please do not use the Services.",
  ] },
  { id: "collect", title: "1. Information we collect", blocks: [
    "A. Information you give us",
    { list: [
      "Account and profile: your email address, username (handle), display name, an optional bio, your password (stored only as a one-way bcrypt hash; we cannot read it) and your account preferences.",
      "Billing: payments are handled by Square. We never receive or store your full card number, CVV or bank credentials. We keep the subscription details Square sends us (your Square customer and subscription identifiers, plan, status and billing dates) for account management and records.",
      "Research and content: what you create on the platform, such as watchlists, alerts, saved screens, ValueBot inputs (ticker, thesis and story settings), report titles, notes and saved scenarios, Strategy Lab and Monte Carlo runs, and the posts, comments, trade ideas and votes you publish in the community.",
      "Messages: emails you send to support and any feedback you give us.",
    ] },
    "B. Information collected automatically",
    { list: [
      "Usage and request logs: the pages and API endpoints you use, timestamps, response times and errors, used to run, secure and improve the Services.",
      "Device and network data: your IP address and browser/user-agent string. We use IP addresses for security, rate limiting and preventing unauthorized scraping of market data. We do not run third-party advertising trackers.",
      "Cookies and local storage: an essential, HTTP-only sign-in cookie and a sign-in token in your browser's local storage keep you logged in; local storage also remembers your light/dark theme. We do not use advertising cookies. If we add analytics in future we will update this policy first. Third-party embeds such as TradingView charts may set their own cookies under their own policies.",
    ] },
  ] },
  { id: "use", title: "2. How we use your information", blocks: [
    { list: [
      "Provide and maintain the Services: authenticate you, manage free trials and paid memberships, deliver market data, and generate and store your research outputs.",
      "Process payments: create Square checkout links, apply subscription updates, handle cancellations and keep billing records.",
      "Improve the Services: analyze aggregate, de-identified usage to make the platform faster and more useful. We do not sell your research inputs, and we do not use your private notes, reports or portfolios to train AI models.",
      "AI features: when ValueBot's AI drafting is enabled, the ticker, thesis and story text you submit are sent to our AI provider (Anthropic) solely to generate your report. Our provider is not permitted to use that data to train its models under its commercial terms.",
      "Security and enforcement: detect and prevent fraud, abuse, automated scraping, market manipulation and breaches of our Terms or Community Guidelines.",
      "Communicate with you: send account and security notices, trial reminders (48 hours before a trial ends), alert emails you set up, valuation-ready notices and policy updates. You can turn off non-essential emails at any time.",
    ] },
  ] },
  { id: "share", title: "3. How we share information", blocks: [
    "We do not sell or rent your personal information. We share it only as follows:",
    { list: [
      "Payment processor: Square, to process subscriptions, renewals and refunds and to prevent payment fraud. Square's handling of your data is governed by Square's privacy policy.",
      "Service providers that run the platform for us under confidentiality and data-protection obligations: Vercel (website hosting), Railway (application servers), Supabase (database), Namecheap Private Email (email delivery) and, when AI drafting is on, Anthropic (AI processing).",
      "Public content: your handle, display name and anything you post publicly in the community (analysis, comments, trade ideas, leaderboard results) are visible to other users and may be indexed by search engines. Reports you share by link are visible to anyone with the link.",
      "Market-data licensors: if our data agreements require it, limited subscriber status or usage logs to verify compliance with personal or non-professional use rules.",
      "Legal and safety: when required by law, subpoena or court order, or when we believe disclosure is necessary to protect the rights, property or safety of Irradiance, our users or the public.",
      "Business transfers: in connection with a merger, acquisition, financing or sale of assets, subject to confidentiality protections; this policy will continue to apply to your data.",
    ] },
    "Public data sources we query, such as SEC EDGAR, GDELT, the ECB and market-data feeds, receive only ticker symbols or company names, never your personal information.",
  ] },
  { id: "retention", title: "4. Data retention", blocks: [
    "We keep your personal information while your account is active or as needed to provide the Services. When you delete your account (Account → Delete account), we delete your profile and private data (watchlists, alerts, saved screens, reports, notes, API keys and sessions) immediately, and remove remaining copies from backups within 30 days. Posts you made publicly are removed with your account.",
    "We keep billing and transaction records for as long as tax, accounting or fraud-prevention laws require, and may keep information needed to enforce our Terms. Request logs are kept for up to 30 days.",
  ] },
  { id: "security", title: "5. Data security", blocks: [
    "We use industry-standard safeguards, including encryption in transit (TLS), hashed passwords, hashed API keys and password-reset tokens, database row-level security, least-privilege access and rate limiting. No method of transmission or storage is 100% secure, so we cannot guarantee absolute security. If a breach affects your personal data we will notify you as the law requires.",
  ] },
  { id: "rights", title: "6. Your privacy rights and choices", blocks: [
    "Depending on where you live (including the European Economic Area, the UK, California and other U.S. states with comprehensive privacy laws), you may have the right to:",
    { list: [
      "Access and portability: get a copy of your data in a machine-readable format. You can download it yourself any time from Account → Export my data.",
      "Correction: update inaccurate account information, directly in your account or by asking us.",
      "Deletion: delete your account and personal data from Account → Delete account, or by asking us.",
      "Restriction and objection: object to or restrict certain processing, including opting out of marketing emails.",
      "Non-discrimination: we will not treat you differently for exercising your rights. We do not sell or \"share\" personal information for cross-context behavioral advertising.",
    ] },
    "To exercise a right that isn't available in your account, email " + EMAIL + ". We may verify your identity first and will respond within the time the law requires (generally 30 days, or 45 days in California). You may also complain to your local data-protection authority.",
  ] },
  { id: "transfers", title: "7. International data transfers", blocks: [
    "Irradiance is operated from the United States, and our service providers store and process data in the United States. If you use the Services from elsewhere, your information will be transferred to and processed in the United States, where data-protection laws may differ from those where you live. Where the law requires, we rely on appropriate safeguards such as standard contractual clauses.",
  ] },
  { id: "children", title: "8. Children's privacy", blocks: [
    "The Services are only for people who are at least 18 (or the age of majority where they live). We do not knowingly collect personal information from anyone under 18; if we learn we have, we will delete it promptly.",
  ] },
  { id: "links", title: "9. Third-party links and embeds", blocks: [
    "The Services link to or embed third-party sites and tools, such as Square checkout, TradingView charts, SEC filings and news articles. We are not responsible for their privacy practices; please review their policies.",
  ] },
  { id: "changes", title: "10. Changes to this policy", blocks: [
    "We may update this policy to reflect changes in our practices, technology or the law. We will post the updated policy on this page with a new \"Last updated\" date and, for material changes, notify you by email or in the app before they take effect.",
  ] },
  { id: "contact", title: "11. Contact us", blocks: [
    "Questions, concerns or requests about this policy or our data practices: " + EMAIL + " · irradiance.ai",
  ] },
];
