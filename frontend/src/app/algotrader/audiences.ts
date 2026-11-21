export interface Audience { slug: string; who: string; headline: string; short: string; intro: string; bots: { name: string; idea: string; how: string }[]; tools: [string, string, string][]; title: string; description: string }

export const AUDIENCES: Audience[] = [
  {
    slug: "long-term-investors", who: "Long-term investors", headline: "Stay disciplined without watching the screen",
    short: "Rules for trend filters, drawdown guards and rebalancing, plus a full review of what you own.",
    title: "AlgoTrader for long-term investors: disciplined, rules-based investing",
    description: "Trend filters, drawdown guards and portfolio analysis for long-term investors. Test rules on years of data and run them on paper first.",
    intro: "Most long-term mistakes are behavioural: selling in a panic, or never trimming a winner. A bot that follows the rule you set in calm markets keeps you honest when markets aren't.",
    bots: [
      { name: "Trend filter", idea: "Hold SPY while the 50-day average is above the 200-day; step aside when it crosses below.", how: "Trend filter (50- vs 200-day) on SPY with a 15% stop-loss as a backstop." },
      { name: "Breakout on quality names", idea: "Buy MSFT, AAPL or COST on a 55-day high; exit on a 20-day low.", how: "Donchian breakout across three symbols, each capped at a third of the bot." },
    ],
    tools: [["Portfolio analysis", "/portfolio", "Import your holdings and see concentration, sector mix, drawdown risk and income."], ["ValueBot", "/valuebot", "A transparent DCF for any US company, with every assumption shown."], ["Monte Carlo", "/lab/montecarlo", "Thousands of simulated paths for your actual mix."]],
  },
  {
    slug: "income-investors", who: "Income investors", headline: "Protect the income, not just the price",
    short: "Track yield and payout safety across your holdings, and automate exits when a position breaks down.",
    title: "AlgoTrader for income investors: dividend portfolios with risk controls",
    description: "Dividend and income portfolios with yield, payout and drawdown analysis, plus paper-trading bots with stop-loss and take-profit controls.",
    intro: "Income portfolios fail slowly: a dividend cut usually follows months of warning signs. IRAI watches yield, payout ratios and price behaviour so you can see trouble early.",
    bots: [
      { name: "Dividend ETF trend guard", idea: "Hold SCHD and VYM while their 50-day average stays above the 200-day.", how: "Trend filter (50- vs 200-day) on two ETFs with a 12% stop-loss." },
      { name: "Oversold dividend payers", idea: "Buy KO, PEP or PG when RSI dips below 30; take profit at 10%.", how: "RSI mean reversion with a take-profit and a per-position cap." },
    ],
    tools: [["Portfolio analysis", "/portfolio", "Estimated annual income, yield by holding and payout flags."], ["Dividends tab", "/ticker/KO#dividends", "Payment history, growth streaks and payout ratios for any stock."], ["Themes", "/research", "Curated themes with breadth, valuation and news radar."]],
  },
  {
    slug: "active-traders", who: "Active traders", headline: "Execute your playbook the same way every time",
    short: "Send TradingView alerts to a bot, size every trade automatically and close out by the bell.",
    title: "AlgoTrader for active traders: TradingView webhooks, sizing and daily auto-close",
    description: "Route TradingView alerts to paper-trading bots with automatic position sizing, stop-loss, take-profit and daily auto-close.",
    intro: "Good setups are wasted by late entries, oversized positions and positions left open overnight. A webhook bot takes your alert, sizes it to your rules and flattens at 15:55 ET.",
    bots: [
      { name: "TradingView day bot", idea: "Trade NVDA and AMD on my TradingView alerts and close everything every day.", how: "Webhook bot with a 50% position cap, 3% stop, 6% target and daily auto-close." },
      { name: "Momentum swing", idea: "Buy when MACD crosses up on QQQ; exit on the cross down.", how: "MACD cross with a 7% stop-loss." },
    ],
    tools: [["Trading bots", "/bots", "Webhook URL, signal log and fills for every bot."], ["Strategy Lab", "/lab", "Backtest and optimise a rule before you automate it."], ["Analyst Bot", "/ticker/NVDA#analyst", "A sourced same-day read on any ticker in seconds."]],
  },
  {
    slug: "systematic-traders", who: "Systematic traders", headline: "Research, test and monitor rules at scale",
    short: "Stress-test ideas against overfitting, compare live paper results with the backtest, and spot drift early.",
    title: "AlgoTrader for systematic traders: tear sheets and live-vs-backtest tracking",
    description: "Backtests with realistic costs, a 57-metric tear sheet, Monte Carlo and live-vs-backtest tracking for systematic strategies.",
    intro: "The gap between a backtest and live trading is where systematic strategies die. Every IRAI bot keeps its backtest beside its live record, metric by metric, so you can tell bad luck from a broken edge.",
    bots: [
      { name: "Multi-asset trend", idea: "SMA 20/100 crossover across SPY, TLT, GLD and EFA, equal weight.", how: "One rule over four symbols, each capped at 25% of the bot." },
      { name: "Bollinger mean reversion", idea: "Buy IWM when it closes below the lower band; sell at the middle band.", how: "Bollinger reversion with a 10% stop-loss." },
    ],
    tools: [["Tear sheets", "/bots", "57 statistics, from Sharpe and Sortino to capture ratios and streaks."], ["Optimiser", "/lab", "Parameter grids with in-sample and out-of-sample splits."], ["Pattern Lab", "/patterns", "Six patterns stress-tested across six asset classes and four timeframes, with holdout, permutation and regime results."]],
  },
];
