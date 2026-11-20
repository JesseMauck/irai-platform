-- IRAI PostgreSQL schema (generated from app/models.py; the app also creates it automatically on startup).

CREATE TABLE adr_pairs (
	id SERIAL NOT NULL, 
	adr_symbol VARCHAR(20) NOT NULL, 
	local_symbol VARCHAR(20) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	country VARCHAR(60) NOT NULL, 
	local_currency VARCHAR(8) NOT NULL, 
	ratio FLOAT NOT NULL, 
	shortable_local BOOLEAN NOT NULL, 
	round_trip_cost_bps FLOAT NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (adr_symbol)
);

CREATE TABLE articles (
	id SERIAL NOT NULL, 
	slug VARCHAR(160) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	category VARCHAR(20) NOT NULL, 
	tickers JSON NOT NULL, 
	summary TEXT NOT NULL, 
	body_md TEXT NOT NULL, 
	author VARCHAR(80) NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	read_minutes INTEGER NOT NULL, 
	premium BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_articles_slug ON articles (slug);
CREATE INDEX ix_articles_category ON articles (category);

CREATE TABLE communities (
	id SERIAL NOT NULL, 
	slug VARCHAR(60) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	description VARCHAR(300) NOT NULL, 
	member_count INTEGER NOT NULL, 
	pro_only BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);

CREATE TABLE etf_funds (
	symbol VARCHAR(20) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	category VARCHAR(60) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (symbol)
);

CREATE TABLE grade_snapshots (
	id SERIAL NOT NULL, 
	symbol VARCHAR(20) NOT NULL, 
	peer_group VARCHAR(80) NOT NULL, 
	as_of TIMESTAMP WITH TIME ZONE NOT NULL, 
	grade VARCHAR(3) NOT NULL, 
	rv_percentile FLOAT NOT NULL, 
	quality_percentile FLOAT NOT NULL, 
	multiple FLOAT, 
	multiple_name VARCHAR(20) NOT NULL, 
	residual FLOAT, 
	source VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_grade_snapshots_as_of ON grade_snapshots (as_of);
CREATE INDEX ix_grade_snapshots_symbol ON grade_snapshots (symbol);

CREATE TABLE instruments (
	symbol VARCHAR(20) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	kind VARCHAR(12) NOT NULL, 
	exchange VARCHAR(40), 
	currency VARCHAR(8), 
	country VARCHAR(60), 
	sector VARCHAR(60), 
	industry VARCHAR(80), 
	in_ticker_bar BOOLEAN NOT NULL, 
	ticker_bar_label VARCHAR(20), 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (symbol)
);

CREATE TABLE peer_groups (
	id SERIAL NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	sector VARCHAR(60) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE quotes (
	symbol VARCHAR(20) NOT NULL, 
	payload JSON NOT NULL, 
	fetched_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (symbol)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	handle VARCHAR(40) NOT NULL, 
	display_name VARCHAR(80) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	plan VARCHAR(20) NOT NULL, 
	is_admin BOOLEAN NOT NULL, 
	verified_trader BOOLEAN NOT NULL, 
	stripe_customer_id VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_handle ON users (handle);
CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE alerts (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	symbol VARCHAR(20) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	threshold FLOAT NOT NULL, 
	channel VARCHAR(10) NOT NULL, 
	webhook_url VARCHAR(500), 
	active BOOLEAN NOT NULL, 
	last_triggered_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_alerts_user_id ON alerts (user_id);

CREATE TABLE article_views (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	article_id INTEGER NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, article_id, month), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(article_id) REFERENCES articles (id) ON DELETE CASCADE
);
CREATE INDEX ix_article_views_user_id ON article_views (user_id);

CREATE TABLE peer_members (
	id SERIAL NOT NULL, 
	group_id INTEGER NOT NULL, 
	symbol VARCHAR(20) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (group_id, symbol), 
	FOREIGN KEY(group_id) REFERENCES peer_groups (id) ON DELETE CASCADE
);
CREATE INDEX ix_peer_members_group_id ON peer_members (group_id);
CREATE INDEX ix_peer_members_symbol ON peer_members (symbol);

CREATE TABLE subscriptions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	plan VARCHAR(20) NOT NULL, 
	interval VARCHAR(10) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	trial_ends_at TIMESTAMP WITH TIME ZONE, 
	current_period_end TIMESTAMP WITH TIME ZONE, 
	cancel_at_period_end BOOLEAN NOT NULL, 
	stripe_subscription_id VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (stripe_subscription_id)
);
CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);

CREATE TABLE threads (
	id SERIAL NOT NULL, 
	community_id INTEGER NOT NULL, 
	author_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body_md TEXT NOT NULL, 
	tickers JSON NOT NULL, 
	score INTEGER NOT NULL, 
	reply_count INTEGER NOT NULL, 
	last_activity_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(community_id) REFERENCES communities (id) ON DELETE CASCADE, 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_threads_author_id ON threads (author_id);
CREATE INDEX ix_threads_last_activity_at ON threads (last_activity_at);
CREATE INDEX ix_threads_community_id ON threads (community_id);

CREATE TABLE trade_posts (
	id SERIAL NOT NULL, 
	author_id INTEGER NOT NULL, 
	long_symbol VARCHAR(20) NOT NULL, 
	short_symbol VARCHAR(20), 
	thesis TEXT NOT NULL, 
	entry_long FLOAT NOT NULL, 
	entry_short FLOAT, 
	entry_source VARCHAR(10) NOT NULL, 
	verification VARCHAR(24) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	exit_long FLOAT, 
	exit_short FLOAT, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	return_pct FLOAT, 
	score INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_trade_posts_author_id ON trade_posts (author_id);

CREATE TABLE valuation_runs (
	id SERIAL NOT NULL, 
	job_id VARCHAR(40) NOT NULL, 
	user_id INTEGER, 
	ticker VARCHAR(20) NOT NULL, 
	stance VARCHAR(10) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	share_token VARCHAR(64), 
	value_per_share FLOAT, 
	price FLOAT, 
	upside FLOAT, 
	method VARCHAR(60), 
	prob_undervalued FLOAT, 
	error VARCHAR(500), 
	finished_at TIMESTAMP WITH TIME ZONE, 
	month VARCHAR(7) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_valuation_runs_ticker ON valuation_runs (ticker);
CREATE INDEX ix_valuation_runs_user_id ON valuation_runs (user_id);
CREATE INDEX ix_valuation_runs_month ON valuation_runs (month);
CREATE UNIQUE INDEX ix_valuation_runs_share_token ON valuation_runs (share_token);
CREATE UNIQUE INDEX ix_valuation_runs_job_id ON valuation_runs (job_id);

CREATE TABLE votes (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	target_type VARCHAR(10) NOT NULL, 
	target_id INTEGER NOT NULL, 
	value INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, target_type, target_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE watchlists (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_watchlists_user_id ON watchlists (user_id);

CREATE TABLE alert_events (
	id SERIAL NOT NULL, 
	alert_id INTEGER NOT NULL, 
	triggered_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	value FLOAT NOT NULL, 
	message VARCHAR(300) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(alert_id) REFERENCES alerts (id) ON DELETE CASCADE
);
CREATE INDEX ix_alert_events_alert_id ON alert_events (alert_id);

CREATE TABLE posts (
	id SERIAL NOT NULL, 
	thread_id INTEGER NOT NULL, 
	author_id INTEGER NOT NULL, 
	body_md TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(thread_id) REFERENCES threads (id) ON DELETE CASCADE, 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_posts_thread_id ON posts (thread_id);

CREATE TABLE watchlist_items (
	id SERIAL NOT NULL, 
	watchlist_id INTEGER NOT NULL, 
	symbol VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (watchlist_id, symbol), 
	FOREIGN KEY(watchlist_id) REFERENCES watchlists (id) ON DELETE CASCADE
);
CREATE INDEX ix_watchlist_items_watchlist_id ON watchlist_items (watchlist_id);
