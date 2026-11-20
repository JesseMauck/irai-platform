"""IRAI Strategy Lab — a Python port of the StockSharp (S#) algo model.

Ported from JesseMauck/stocksharp-algo-trade-platform (StockSharp, Apache License 2.0; see NOTICE):
  Algo/Indicators/*            → indicators.py   (SMA, EMA, SMMA, RSI, Bollinger, MACD, Highest/Lowest, ROC)
  Algo/Strategies/Strategy.cs  → strategies.py   (candle-driven strategies with Position / Volume semantics;
  Samples/.../SmaStrategy.cs                        SmaCrossover reproduces the sample's reversal logic)
  Algo/Testing/HistoryEmulationConnector / MarketEmulator → emulator.py (history emulation, fills, commissions)
  Algo/Statistics/*            → statistics.py   (NetProfit, MaxDrawdown, RecoveryFactor, Win/Loss trades …)
  Algo/Strategies/Testing/BatchEmulation → optimizer.py (parameter grid search)

Research and education only: the Lab backtests and paper-tests strategies on historical data. It does not
route orders to brokers.
"""
