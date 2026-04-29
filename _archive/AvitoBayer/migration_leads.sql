-- AvitoBayer: полная миграция
-- Применять в Supabase SQL Editor или через psql

-- 1. Правила обработки поисковых запросов
CREATE TABLE IF NOT EXISTS search_processing_rules (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL,
    search_type             TEXT NOT NULL CHECK (search_type IN ('buy', 'competitors', 'price_monitor')),
    price_min               INTEGER,
    price_max               INTEGER,
    score_threshold         REAL DEFAULT 5.0,
    auto_questions          TEXT[],
    check_interval_minutes  INTEGER DEFAULT 60,
    max_leads_per_run       INTEGER DEFAULT 10,
    alert_on_new            BOOLEAN DEFAULT true,
    alert_on_price_change   BOOLEAN DEFAULT false,
    alert_on_price_drop_pct REAL,
    custom_rules            JSONB DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ
);
ALTER TABLE search_processing_rules DISABLE ROW LEVEL SECURITY;

-- 2. Сохранённые поисковые запросы
CREATE TABLE IF NOT EXISTS saved_searches (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL,
    avito_url               TEXT NOT NULL,
    search_type             TEXT NOT NULL DEFAULT 'buy' CHECK (search_type IN ('buy', 'competitors', 'price_monitor')),
    description             TEXT,
    processing_rules_id     UUID REFERENCES search_processing_rules(id),
    is_active               BOOLEAN NOT NULL DEFAULT true,
    last_run_at             TIMESTAMPTZ,
    last_results_count      INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_saved_searches_active ON saved_searches(is_active);
CREATE INDEX IF NOT EXISTS idx_saved_searches_type ON saved_searches(search_type);
ALTER TABLE saved_searches DISABLE ROW LEVEL SECURITY;

-- 3. История запусков поиска
CREATE TABLE IF NOT EXISTS search_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id               UUID NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
    results_count           INTEGER NOT NULL DEFAULT 0,
    avg_price               REAL,
    min_price               REAL,
    max_price               REAL,
    median_price            REAL,
    new_items_count         INTEGER DEFAULT 0,
    leads_created           INTEGER DEFAULT 0,
    run_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_search_runs_search_id ON search_runs(search_id);
CREATE INDEX IF NOT EXISTS idx_search_runs_run_at ON search_runs(run_at DESC);
ALTER TABLE search_runs DISABLE ROW LEVEL SECURITY;

-- 4. Лиды (pipeline)
CREATE TABLE IF NOT EXISTS leads (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    price       INTEGER,
    score       REAL,
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN (
                    'new', 'selected', 'auto_questions_sent', 'waiting_reply',
                    'operator_needed', 'negotiation', 'rejected', 'deal_candidate', 'closed'
                )),
    notes       TEXT,
    seller_id   TEXT,
    channel_id  TEXT,
    url         TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_item_id ON leads(item_id);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC NULLS LAST);
ALTER TABLE leads DISABLE ROW LEVEL SECURITY;

-- 5. Дефолтные правила
INSERT INTO search_processing_rules (name, search_type, score_threshold, auto_questions, check_interval_minutes, max_leads_per_run, alert_on_new, alert_on_price_change, alert_on_price_drop_pct)
SELECT * FROM (VALUES
    ('Покупка iPhone (дефолт)', 'buy', 6.0::REAL,
     ARRAY['Здравствуйте! Телефон ещё актуален?', 'Face ID работает?', 'Телефон ремонтировался или вскрывался?', 'True Tone на месте?'],
     30, 10, true, false, NULL::REAL),
    ('Мониторинг конкурентов (дефолт)', 'competitors', 0::REAL,
     NULL::TEXT[], 360, 0, false, true, NULL::REAL),
    ('Мониторинг цен (дефолт)', 'price_monitor', 0::REAL,
     NULL::TEXT[], 120, 0, false, true, 10.0::REAL)
) AS v(name, search_type, score_threshold, auto_questions, check_interval_minutes, max_leads_per_run, alert_on_new, alert_on_price_change, alert_on_price_drop_pct)
WHERE NOT EXISTS (SELECT 1 FROM search_processing_rules LIMIT 1);
