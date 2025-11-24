-- Initial database schema for VPN Bot
-- This migration creates all necessary tables for the application

-- Users table with authentication and language preferences
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    role TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fa',
    is_authenticated INTEGER NOT NULL DEFAULT 0,
    rate_limit_count INTEGER NOT NULL DEFAULT 0,
    rate_limit_reset TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Servers table for VPN panel connections
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    base_url TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Inbounds table for tracking panel inbound configurations
CREATE TABLE IF NOT EXISTS inbounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inbound_id INTEGER NOT NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    friendly_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(inbound_id, server_id)
);

-- Plans table for VPN subscription packages
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    inbound_id INTEGER NOT NULL,
    volume_gb INTEGER NOT NULL,
    duration_days INTEGER NOT NULL,
    multi_user INTEGER NOT NULL DEFAULT 1,
    price REAL NOT NULL DEFAULT 0,
    package_type TEXT NOT NULL DEFAULT 'prebuilt',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Plan-Server relationship (many-to-many)
CREATE TABLE IF NOT EXISTS plan_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plan_id, server_id)
);

-- Server pricing for per-GB pricing model
CREATE TABLE IF NOT EXISTS server_pricing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    price_per_gb REAL NOT NULL,
    min_months INTEGER NOT NULL DEFAULT 1,
    max_months INTEGER NOT NULL DEFAULT 6,
    extra_month_price_percent REAL,
    extra_month_price_absolute REAL,
    additional_user_price REAL NOT NULL DEFAULT 0,
    apply_to_all INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Orders table for tracking purchases
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    server_id INTEGER REFERENCES servers(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    receipt_file_id TEXT,
    receipt_path TEXT,
    config_id TEXT,
    expires_at TEXT,
    traffic_used REAL NOT NULL DEFAULT 0,
    volume_gb INTEGER,
    duration_days INTEGER,
    multi_user INTEGER,
    total_price REAL,
    custom_config TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    rejected_at TEXT,
    rejection_reason TEXT
);

-- Settings table for bot configuration
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Security events table for audit logging
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_id TEXT,
    event_type TEXT NOT NULL,
    description TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_plans_server_id ON plans(server_id);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_expires_at ON orders(expires_at);
CREATE INDEX IF NOT EXISTS idx_security_events_user_id ON security_events(user_id);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at ON security_events(created_at);
