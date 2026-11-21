"""IRAI database schema.

Domains
  accounts      users, subscriptions, usage counters
  coverage      instruments, adr_pairs, etf_funds, peer_groups (+ members)
  market cache  quotes (latest quote + history per symbol, refreshed from the live source)
  research      articles, article_views (for the free-tier monthly quota)
  personal      watchlists, watchlist_items, alerts, alert_events
  community     communities, threads, posts, votes, trade_posts (immutable once published)
  valuebot      valuation_runs (one row per ValueBot job, linked to the user who ran it)
  platform      email_outbox (transactional email queue), password_resets, api_keys, saved_screens
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
                        func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


# ── accounts ──────────────────────────────────────────────────────────────────────────────────────
class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | essential | pro
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_trader: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_customer_id: Mapped[str | None] = mapped_column(String(64))  # Square customer id
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Sessions issued before this moment are rejected (set on password reset / "sign out everywhere").
    tokens_valid_after: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # UI customization, validated in routers/me.py

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user", cascade="all, delete-orphan")
    watchlists: Mapped[list[Watchlist]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    interval: Mapped[str] = mapped_column(String(10), default="monthly")  # monthly | annual
    status: Mapped[str] = mapped_column(String(20), default="trialing")  # pending|trialing|active|past_due|canceled
    trial_ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(12), default="internal", server_default="internal")  # internal | square
    provider_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_ref: Mapped[str | None] = mapped_column(String(64), index=True)  # e.g. Square payment link order id
    trial_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    user: Mapped[User] = relationship(back_populates="subscriptions")


# ── coverage ──────────────────────────────────────────────────────────────────────────────────────
class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(12), default="equity")  # equity | etf | index | fx | rate
    exchange: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(60))
    sector: Mapped[str | None] = mapped_column(String(60))
    industry: Mapped[str | None] = mapped_column(String(80))
    in_ticker_bar: Mapped[bool] = mapped_column(Boolean, default=False)
    ticker_bar_label: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class AdrPair(TimestampMixin, Base):
    __tablename__ = "adr_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    adr_symbol: Mapped[str] = mapped_column(String(20), unique=True)
    local_symbol: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(60))
    local_currency: Mapped[str] = mapped_column(String(8))
    # Local ordinary shares represented by ONE ADR (e.g. 10 for Toyota, 0.5 for AstraZeneca).
    ratio: Mapped[float] = mapped_column(Float)
    shortable_local: Mapped[bool] = mapped_column(Boolean, default=True)
    round_trip_cost_bps: Mapped[float] = mapped_column(Float, default=35.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sector: Mapped[str | None] = mapped_column(String(60))


class EtfFund(TimestampMixin, Base):
    __tablename__ = "etf_funds"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PeerGroup(TimestampMixin, Base):
    __tablename__ = "peer_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    sector: Mapped[str] = mapped_column(String(60))
    members: Mapped[list[PeerMember]] = relationship(back_populates="group", cascade="all, delete-orphan")


class PeerMember(Base):
    __tablename__ = "peer_members"
    __table_args__ = (UniqueConstraint("group_id", "symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("peer_groups.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(160))
    group: Mapped[PeerGroup] = relationship(back_populates="members")


class GradeSnapshot(Base):
    """Point-in-time Relative Value grades: written once per computation, never restated."""
    __tablename__ = "grade_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    peer_group: Mapped[str] = mapped_column(String(80))
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    grade: Mapped[str] = mapped_column(String(3))
    rv_percentile: Mapped[float] = mapped_column(Float)
    quality_percentile: Mapped[float] = mapped_column(Float)
    multiple: Mapped[float | None] = mapped_column(Float)
    multiple_name: Mapped[str] = mapped_column(String(20))
    residual: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(10))


# ── market cache ──────────────────────────────────────────────────────────────────────────────────
class QuoteCache(Base):
    __tablename__ = "quotes"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── research ──────────────────────────────────────────────────────────────────────────────────────
class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), index=True)  # ADR | ETF | Fundamental | Methodology
    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    body_md: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(80))
    published_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    read_minutes: Mapped[int] = mapped_column(Integer, default=5)
    premium: Mapped[bool] = mapped_column(Boolean, default=False)


class ArticleView(Base):
    __tablename__ = "article_views"
    __table_args__ = (UniqueConstraint("user_id", "article_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7))  # YYYY-MM


# ── personal ──────────────────────────────────────────────────────────────────────────────────────
class Watchlist(TimestampMixin, Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    user: Mapped[User] = relationship(back_populates="watchlists")
    items: Mapped[list[WatchlistItem]] = relationship(back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    # price_above | price_below | change_pct_abs | adr_z_abs
    kind: Mapped[str] = mapped_column(String(20))
    threshold: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(10), default="email")  # email | webhook | push
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    triggered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    value: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(String(300))


# ── community ─────────────────────────────────────────────────────────────────────────────────────
class Community(TimestampMixin, Base):
    __tablename__ = "communities"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    pro_only: Mapped[bool] = mapped_column(Boolean, default=False)


class Thread(TimestampMixin, Base):
    __tablename__ = "threads"
    id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    # discussion | analysis (long-form, Seeking Alpha style) | strategy (shares a Lab backtest)
    kind: Mapped[str] = mapped_column(String(12), default="discussion", server_default="discussion", index=True)
    outlook: Mapped[str | None] = mapped_column(String(10))  # bullish | neutral | bearish (analysis only)
    primary_ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    backtest_run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id", ondelete="SET NULL"), index=True)
    valuation_job_id: Mapped[str | None] = mapped_column(String(40))
    score: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    community: Mapped[Community] = relationship()
    author: Mapped[User] = relationship()


class Post(TimestampMixin, Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body_md: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    author: Mapped[User] = relationship()


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(String(10))  # thread | trade
    target_id: Mapped[int] = mapped_column(Integer)
    value: Mapped[int] = mapped_column(Integer)  # +1 / -1


class TradePost(TimestampMixin, Base):
    """A structured trade idea. Entry price is captured from market data at posting time and the
    thesis/entry can never be edited; only closing is allowed (exit price also captured)."""
    __tablename__ = "trade_posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    long_symbol: Mapped[str] = mapped_column(String(20))
    short_symbol: Mapped[str | None] = mapped_column(String(20))
    thesis: Mapped[str] = mapped_column(Text)
    entry_long: Mapped[float] = mapped_column(Float)
    entry_short: Mapped[float | None] = mapped_column(Float)
    entry_source: Mapped[str] = mapped_column(String(10))  # LIVE | DEMO | USER
    verification: Mapped[str] = mapped_column(String(24))  # timestamp-verified | broker-verified | self-reported
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | closed
    exit_long: Mapped[float | None] = mapped_column(Float)
    exit_short: Mapped[float | None] = mapped_column(Float)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    return_pct: Mapped[float | None] = mapped_column(Float)
    score: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    author: Mapped[User] = relationship()


class ModerationLog(Base):
    """Every moderation action is logged (community rule: actions are logged and can be appealed)."""
    __tablename__ = "moderation_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))  # hide | unhide
    reason: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── valuebot ──────────────────────────────────────────────────────────────────────────────────────
class ValuationRun(TimestampMixin, Base):
    __tablename__ = "valuation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    stance: Mapped[str] = mapped_column(String(10), default="neutral")
    status: Mapped[str] = mapped_column(String(10), default="queued")
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    value_per_share: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    upside: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(60))
    prob_undervalued: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(500))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    month: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM, for plan quotas
    # Report library: the member's own title, notes (markdown) and organisation.
    title: Mapped[str | None] = mapped_column(String(200))
    notes_md: Mapped[str | None] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Saved what-if scenarios: [{"name", "assumptions": {...}, "value_per_share", "upside", "saved_at"}]
    scenarios: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, server_default="[]")


# ── platform ──────────────────────────────────────────────────────────────────────────────────────
class EmailOutbox(Base):
    """Transactional email queue (outbox pattern): requests write a row, the worker sends it. A failed send
    is retried with backoff; a row is never sent twice once marked sent."""
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    to_addr: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(200))
    body_text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))  # welcome | password_reset | alert | valuebot_done
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    next_attempt_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of the emailed token
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    """Read-only API keys for Pro members. Only a SHA-256 hash is stored; the key is shown once."""
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(12))  # first characters, for display
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SavedScreen(TimestampMixin, Base):
    __tablename__ = "saved_screens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    universe: Mapped[str] = mapped_column(String(12))  # fundamental | adr | etf
    filters: Mapped[dict[str, Any]] = mapped_column(JSON)
    alert_on_new: Mapped[bool] = mapped_column(Boolean, default=False)
    last_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)


class BacktestRun(Base):
    """One Strategy Lab backtest (or optimisation) — stored so members can revisit and share results."""
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="backtest")  # backtest | optimize
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    strategy: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON)
    range: Mapped[str] = mapped_column(String(4))
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON)
    data_source: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BuzzSnapshot(Base):
    """Latest media/market attention reading per symbol (refreshed by the worker)."""
    __tablename__ = "buzz_snapshots"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str | None] = mapped_column(String(12))  # equity | etf | cef | bond | adr | index | fx | crypto
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(10))
    components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AdrSignal(Base):
    """One scan of one ADR pair by the continuous scanner; the latest row per pair drives 'opportunities'."""
    __tablename__ = "adr_signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    adr_symbol: Mapped[str] = mapped_column(String(20), index=True)
    scanned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    premium: Mapped[float | None] = mapped_column(Float)
    deviation: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float | None] = mapped_column(Float)
    tradable: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ResearchTheme(TimestampMixin, Base):
    """An investment theme: curated (owner_id NULL) or a member's own custom research workspace."""
    __tablename__ = "research_themes"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)       # news query terms
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{name, why, symbol?}]
    notes_md: Mapped[str | None] = mapped_column(Text)
    public: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    pestel: Mapped[dict[str, Any] | None] = mapped_column(JSON)          # cached PESTEL radar (GDELT is slow/throttled)
    pestel_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Pin(Base):
    """Something a member pinned to their research workspace."""
    __tablename__ = "pins"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # theme | watchlist | ticker | report | screen
    ref: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalystReport(Base):
    """One Analyst Bot run: staged progress while it gathers data, then the AI-written analysis."""
    __tablename__ = "analyst_reports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued | running | done | error
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))
    engine: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class WaitlistEntry(Base):
    """Interest in an upcoming product (e.g. the IRAI AlgoTrader add-on), with the brokers the person uses."""
    __tablename__ = "waitlist_entries"
    __table_args__ = (UniqueConstraint("email", "product", name="uq_waitlist_email_product"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product: Mapped[str] = mapped_column(String(30), index=True)
    email: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    brokers: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Portfolio(TimestampMixin, Base):
    """A member's portfolio: entered by hand, imported from CSV, or (later) synced from a broker connection."""
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | csv | broker
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark: Mapped[str] = mapped_column(String(10), default="SPY")
    holdings: Mapped[list[Holding]] = relationship(back_populates="portfolio", cascade="all, delete-orphan", order_by="Holding.id")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("portfolio_id", "symbol", name="uq_holding_portfolio_symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    cost_basis: Mapped[float | None] = mapped_column(Float)  # per share, in the security's currency
    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")


class CalibrationRun(Base):
    """Nightly ValueBot benchmark: value/price for a fixed ticker set, to catch data or model regressions."""
    __tablename__ = "calibration_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | done | error
    trigger: Mapped[str] = mapped_column(String(12), default="schedule")  # schedule | manual
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)


# ── Paper trading (IRAI AlgoTrader) ──────────────────────────────────────────────────────────────
class PaperAccount(TimestampMixin, Base):
    """Simulated brokerage account. `cash` is unallocated cash; capital given to bots lives in their sleeves."""
    __tablename__ = "paper_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    starting_cash: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)


class Bot(TimestampMixin, Base):
    __tablename__ = "bots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)  # the plain-English idea it was built from
    mode: Mapped[str] = mapped_column(String(12), default="strategy")  # strategy | webhook
    strategy: Mapped[str | None] = mapped_column(String(30))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_position_pct: Mapped[float] = mapped_column(Float, default=1.0)  # of the sleeve, per symbol
    stop_loss_pct: Mapped[float | None] = mapped_column(Float)
    take_profit_pct: Mapped[float | None] = mapped_column(Float)
    daily_auto_close: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default="running", index=True)  # running | paused
    webhook_token: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    backtest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_eval_on: Mapped[str | None] = mapped_column(String(10))
    last_autoclose_on: Mapped[str | None] = mapped_column(String(10))
    last_risk_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    sleeves: Mapped[list[BotSleeve]] = relationship(back_populates="bot", cascade="all, delete-orphan", order_by="BotSleeve.id")


class BotSleeve(TimestampMixin, Base):
    """A bot's capital inside one paper account. One bot can feed many accounts."""
    __tablename__ = "bot_sleeves"
    __table_args__ = (UniqueConstraint("bot_id", "account_id", name="uq_sleeve_bot_account"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True)
    capital: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    bot: Mapped[Bot] = relationship(back_populates="sleeves")
    positions: Mapped[list[PaperPosition]] = relationship(back_populates="sleeve", cascade="all, delete-orphan")


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("sleeve_id", "symbol", name="uq_position_sleeve_symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sleeve_id: Mapped[int] = mapped_column(ForeignKey("bot_sleeves.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sleeve: Mapped[BotSleeve] = relationship(back_populates="positions")


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    sleeve_id: Mapped[int] = mapped_column(ForeignKey("bot_sleeves.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(20))  # signal | stop_loss | take_profit | auto_close | webhook | manual | close_bot
    price_source: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BotSignal(Base):
    __tablename__ = "bot_signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(12))  # schedule | webhook | manual | risk
    action: Mapped[str] = mapped_column(String(12))
    symbol: Mapped[str | None] = mapped_column(String(20))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12))  # executed | ignored | error
    detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SleeveEquity(Base):
    """End-of-day equity per sleeve: the live track record."""
    __tablename__ = "sleeve_equity"
    __table_args__ = (UniqueConstraint("sleeve_id", "date", name="uq_sleeve_equity_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sleeve_id: Mapped[int] = mapped_column(ForeignKey("bot_sleeves.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String(10))
    equity: Mapped[float] = mapped_column(Float)


class AssistantUsage(Base):
    """Messages sent to the Ask IRAI assistant per user per UTC day (plan quota)."""
    __tablename__ = "assistant_usage"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_assistant_usage_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)
