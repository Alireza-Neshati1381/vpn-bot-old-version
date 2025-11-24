-- Migration 002: Add server_id column to plans table
-- This migration adds the missing server_id foreign key to the plans table

-- Add server_id column to plans table
ALTER TABLE plans ADD COLUMN server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_plans_server_id ON plans(server_id);
