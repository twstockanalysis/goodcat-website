-- TW ETF AI Analyzer
-- SQLite database schema

CREATE TABLE IF NOT EXISTS etf_master (
    code TEXT PRIMARY KEY,

    name TEXT NOT NULL,

    is_active INTEGER NOT NULL DEFAULT 0
        CHECK (is_active IN (0, 1)),

    is_bond INTEGER NOT NULL DEFAULT 0
        CHECK (is_bond IN (0, 1)),

    listing_date TEXT,

    fund_size REAL
        CHECK (fund_size IS NULL OR fund_size >= 0),

    expense_ratio REAL
        CHECK (
            expense_ratio IS NULL
            OR (
                expense_ratio >= 0
                AND expense_ratio <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_etf_master_name
ON etf_master (name);

-- Immutable reviewed annual costs; do not collapse into undated master values.
CREATE TABLE IF NOT EXISTS etf_annual_expense_evidence (
    etf_code TEXT NOT NULL REFERENCES etf_master(code),
    reporting_year INTEGER NOT NULL CHECK (reporting_year BETWEEN 2000 AND 9998),
    publication_date TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY (etf_code, reporting_year)
);


CREATE TABLE IF NOT EXISTS import_batch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    pipeline_name TEXT NOT NULL,

    source_id TEXT NOT NULL,

    endpoint_id TEXT NOT NULL,

    started_at TEXT NOT NULL,

    completed_at TEXT,

    status TEXT NOT NULL
        CHECK (
            status IN (
                'running',
                'success',
                'failed'
            )
        ),

    raw_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (raw_record_count >= 0),

    accepted_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (accepted_record_count >= 0),

    rejected_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (rejected_record_count >= 0),

    inserted_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (inserted_record_count >= 0),

    updated_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (updated_record_count >= 0),

    deleted_development_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (deleted_development_record_count >= 0),

    checksum_sha256 TEXT,

    raw_snapshot_path TEXT,

    processed_snapshot_path TEXT,

    rejected_snapshot_path TEXT,

    quality_report_path TEXT,

    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_import_batch_status
ON import_batch (status);

CREATE INDEX IF NOT EXISTS idx_import_batch_started_at
ON import_batch (started_at);

-- ============================================================
-- ETF 績效資料
-- ============================================================

CREATE TABLE IF NOT EXISTS etf_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    etf_code TEXT NOT NULL,

    as_of_date TEXT NOT NULL,

    period_code TEXT NOT NULL
        CHECK (
            period_code IN (
                '1D',
                '1W',
                '1M',
                '3M',
                '6M',
                '1Y',
                '3Y',
                '5Y'
            )
        ),

    metric_code TEXT NOT NULL
        DEFAULT 'PRICE_RETURN'
        CHECK (
            metric_code IN (
                'PRICE_RETURN',
                'TOTAL_RETURN',
                'NAV_RETURN'
            )
        ),

    return_pct REAL NOT NULL
        CHECK (return_pct >= -100),

    source_id TEXT NOT NULL
        CHECK (length(trim(source_id)) > 0),

    import_batch_id INTEGER,

    source_updated_at TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (etf_code)
        REFERENCES etf_master (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    FOREIGN KEY (import_batch_id)
        REFERENCES import_batch (id)
        ON DELETE SET NULL,

    UNIQUE (
        etf_code,
        as_of_date,
        period_code,
        metric_code,
        source_id
    )
);


CREATE INDEX IF NOT EXISTS
idx_etf_performance_lookup
ON etf_performance (
    metric_code,
    period_code,
    as_of_date DESC,
    return_pct DESC
);


CREATE INDEX IF NOT EXISTS
idx_etf_performance_code_date
ON etf_performance (
    etf_code,
    metric_code,
    period_code,
    as_of_date DESC
);

-- ============================================================
-- ETF 官方每日收盤價（估值與本金風險分析共用）
-- ============================================================

CREATE TABLE IF NOT EXISTS etf_daily_close (
    etf_code TEXT NOT NULL,

    trade_date TEXT NOT NULL,

    close_price REAL NOT NULL
        CHECK (close_price > 0),

    source_id TEXT NOT NULL
        CHECK (length(trim(source_id)) > 0),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (etf_code, trade_date, source_id),

    FOREIGN KEY (etf_code)
        REFERENCES etf_master (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS
idx_etf_daily_close_latest
ON etf_daily_close (
    etf_code,
    trade_date DESC,
    source_id
);


-- ============================================================
-- ETF 配息事件
-- ============================================================

CREATE TABLE IF NOT EXISTS etf_dividend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    etf_code TEXT NOT NULL,

    source_event_id TEXT NOT NULL
        CHECK (
            length(trim(source_event_id)) > 0
        ),

    announcement_date TEXT,

    ex_dividend_date TEXT,

    record_date TEXT,

    payment_date TEXT,

    amount_per_unit REAL NOT NULL
        CHECK (amount_per_unit >= 0),

    currency TEXT NOT NULL
        DEFAULT 'TWD'
        CHECK (length(currency) = 3),

    source_id TEXT NOT NULL
        CHECK (length(trim(source_id)) > 0),

    import_batch_id INTEGER,

    source_updated_at TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        announcement_date IS NOT NULL
        OR ex_dividend_date IS NOT NULL
        OR record_date IS NOT NULL
        OR payment_date IS NOT NULL
    ),

    CHECK (
        ex_dividend_date IS NULL
        OR payment_date IS NULL
        OR payment_date >= ex_dividend_date
    ),

    FOREIGN KEY (etf_code)
        REFERENCES etf_master (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    FOREIGN KEY (import_batch_id)
        REFERENCES import_batch (id)
        ON DELETE SET NULL,

    UNIQUE (
        source_id,
        source_event_id
    )
);


CREATE INDEX IF NOT EXISTS
idx_etf_dividend_code_payment
ON etf_dividend (
    etf_code,
    payment_date DESC
);


CREATE INDEX IF NOT EXISTS
idx_etf_dividend_ex_date
ON etf_dividend (
    ex_dividend_date DESC
);


-- ============================================================
-- ETF 單次配息摘要補充資料
-- ============================================================

CREATE TABLE IF NOT EXISTS
etf_dividend_summary_metric (
    dividend_id INTEGER PRIMARY KEY,

    distribution_period TEXT
        CHECK (
            distribution_period IS NULL
            OR (
                length(distribution_period) = 6
                AND substr(
                    distribution_period,
                    5,
                    1
                ) = 'Q'
                AND substr(
                    distribution_period,
                    6,
                    1
                ) IN ('1', '2', '3', '4')
            )
        ),

    distribution_period_source_id TEXT,

    yield_pct REAL
        CHECK (
            yield_pct IS NULL
            OR yield_pct >= 0
        ),

    yield_basis TEXT
        CHECK (
            yield_basis IS NULL
            OR yield_basis IN (
                'OFFICIAL',
                'CALCULATED'
            )
        ),

    yield_source_id TEXT,

    reference_trade_date TEXT,

    reference_close_price REAL
        CHECK (
            reference_close_price IS NULL
            OR reference_close_price > 0
        ),

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (
            distribution_period IS NULL
            AND distribution_period_source_id IS NULL
        )
        OR (
            distribution_period IS NOT NULL
            AND distribution_period_source_id
                IS NOT NULL
            AND length(
                trim(
                    distribution_period_source_id
                )
            ) > 0
        )
    ),

    CHECK (
        (
            yield_pct IS NULL
            AND yield_basis IS NULL
            AND yield_source_id IS NULL
            AND reference_trade_date IS NULL
            AND reference_close_price IS NULL
        )
        OR (
            yield_pct IS NOT NULL
            AND yield_basis IS NOT NULL
            AND yield_source_id IS NOT NULL
            AND length(
                trim(yield_source_id)
            ) > 0
        )
    ),

    CHECK (
        yield_basis IS NULL
        OR yield_basis = 'OFFICIAL'
        OR (
            reference_trade_date IS NOT NULL
            AND reference_close_price IS NOT NULL
        )
    ),

    CHECK (
        yield_basis IS NULL
        OR yield_basis = 'CALCULATED'
        OR (
            reference_trade_date IS NULL
            AND reference_close_price IS NULL
        )
    ),

    FOREIGN KEY (dividend_id)
        REFERENCES etf_dividend (id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS
idx_etf_dividend_summary_yield_basis
ON etf_dividend_summary_metric (
    yield_basis,
    dividend_id
);


-- ============================================================
-- ETF 每期配息組成
-- ============================================================

CREATE TABLE IF NOT EXISTS etf_dividend_component (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    dividend_id INTEGER NOT NULL,

    component_code TEXT NOT NULL
        CHECK (
            length(trim(component_code)) > 0
        ),

    component_basis TEXT NOT NULL
        DEFAULT 'ACTUAL'
        CHECK (
            component_basis IN (
                'ESTIMATED',
                'ACTUAL'
            )
        ),

    component_name TEXT,

    amount_per_unit REAL,

    ratio_pct REAL,

    source_id TEXT NOT NULL
        CHECK (length(trim(source_id)) > 0),

    import_batch_id INTEGER,

    source_updated_at TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        amount_per_unit IS NOT NULL
        OR ratio_pct IS NOT NULL
    ),

    CHECK (
        amount_per_unit IS NULL
        OR amount_per_unit >= 0
    ),

    CHECK (
        ratio_pct IS NULL
        OR (
            ratio_pct >= 0
            AND ratio_pct <= 100
        )
    ),

    FOREIGN KEY (dividend_id)
        REFERENCES etf_dividend (id)
        ON DELETE CASCADE,

    FOREIGN KEY (import_batch_id)
        REFERENCES import_batch (id)
        ON DELETE SET NULL,

    UNIQUE (
        dividend_id,
        component_basis,
        component_code,
        source_id
    )
);


CREATE INDEX IF NOT EXISTS
idx_etf_dividend_component_code
ON etf_dividend_component (
    component_code,
    ratio_pct DESC
);

-- ============================================================
-- 正式配息來源文件
-- ============================================================

CREATE TABLE IF NOT EXISTS
dividend_source_document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_id TEXT NOT NULL
        CHECK (length(trim(source_id)) > 0),

    source_document_id TEXT NOT NULL
        CHECK (
            length(trim(source_document_id)) > 0
        ),

    version_number INTEGER NOT NULL
        CHECK (version_number >= 1),

    source_url TEXT NOT NULL
        CHECK (length(trim(source_url)) > 0),

    source_document_date TEXT,

    downloaded_at TEXT NOT NULL,

    content_type TEXT NOT NULL
        CHECK (length(trim(content_type)) > 0),

    information_basis TEXT NOT NULL
        DEFAULT 'UNKNOWN'
        CHECK (
            information_basis IN (
                'UNKNOWN',
                'ACTUAL',
                'ESTIMATED'
            )
        ),

    checksum_sha256 TEXT NOT NULL
        CHECK (length(checksum_sha256) = 64),

    snapshot_path TEXT NOT NULL
        CHECK (
            length(trim(snapshot_path)) > 0
        ),

    metadata_path TEXT NOT NULL
        CHECK (
            length(trim(metadata_path)) > 0
        ),

    parse_status TEXT NOT NULL
        DEFAULT 'downloaded'
        CHECK (
            parse_status IN (
                'downloaded',
                'parsed',
                'rejected',
                'failed'
            )
        ),

    parse_error TEXT,

    import_batch_id INTEGER,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (import_batch_id)
        REFERENCES import_batch (id)
        ON DELETE SET NULL,

    UNIQUE (
        source_id,
        source_document_id,
        version_number
    ),

    UNIQUE (
        source_id,
        source_document_id,
        checksum_sha256
    )
);


CREATE INDEX IF NOT EXISTS
idx_dividend_source_document_lookup
ON dividend_source_document (
    source_id,
    source_document_id,
    version_number DESC
);


CREATE INDEX IF NOT EXISTS
idx_dividend_source_document_status
ON dividend_source_document (
    parse_status,
    downloaded_at DESC
);

-- ============================================================
-- 正式配息來源審核佇列
-- ============================================================

CREATE TABLE IF NOT EXISTS
dividend_source_review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    dividend_id INTEGER NOT NULL,

    issue_type TEXT NOT NULL
        CHECK (
            issue_type IN (
                'MISSING_ACTUAL_COMPONENTS',
                'MISSING_SOURCE_DOCUMENT'
            )
        ),

    suggested_source_id TEXT,

    priority INTEGER NOT NULL
        DEFAULT 50
        CHECK (
            priority >= 1
            AND priority <= 100
        ),

    status TEXT NOT NULL
        DEFAULT 'PENDING'
        CHECK (
            status IN (
                'PENDING',
                'IN_REVIEW',
                'RESOLVED',
                'SKIPPED'
            )
        ),

    notes TEXT,

    resolution_document_id INTEGER,

    last_evaluated_at TEXT NOT NULL,

    resolved_at TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dividend_id)
        REFERENCES etf_dividend (id)
        ON DELETE CASCADE,

    FOREIGN KEY (resolution_document_id)
        REFERENCES dividend_source_document (id)
        ON DELETE SET NULL,

    UNIQUE (
        dividend_id,
        issue_type
    )
);


CREATE INDEX IF NOT EXISTS
idx_dividend_review_queue_status
ON dividend_source_review_queue (
    status,
    priority,
    updated_at DESC
);


CREATE INDEX IF NOT EXISTS
idx_dividend_review_queue_issue
ON dividend_source_review_queue (
    issue_type,
    status,
    priority
);


CREATE INDEX IF NOT EXISTS
idx_dividend_review_queue_dividend
ON dividend_source_review_queue (
    dividend_id,
    issue_type
);

-- ============================================================
-- M11 單一使用者決策條件
-- ============================================================

CREATE TABLE IF NOT EXISTS decision_profile (
    id INTEGER PRIMARY KEY
        CHECK (id = 1),

    monthly_after_tax_target REAL NOT NULL
        CHECK (monthly_after_tax_target >= 0),

    analysis_years INTEGER NOT NULL
        CHECK (analysis_years >= 1 AND analysis_years <= 50),

    history_years INTEGER NOT NULL
        CHECK (history_years >= 1 AND history_years <= 10),

    cash_deduction_rate_pct REAL
        CHECK (
            cash_deduction_rate_pct IS NULL
            OR (
                cash_deduction_rate_pct >= 0
                AND cash_deduction_rate_pct <= 100
            )
        ),

    currency TEXT NOT NULL DEFAULT 'TWD'
        CHECK (currency = 'TWD'),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- M11 手動持有部位（無券商連線）
-- ============================================================

CREATE TABLE IF NOT EXISTS manual_holding (
    etf_code TEXT PRIMARY KEY,

    held_units INTEGER NOT NULL
        CHECK (held_units > 0),

    unit_price REAL
        CHECK (unit_price IS NULL OR unit_price > 0),

    price_as_of_date TEXT,

    price_source_id TEXT,

    currency TEXT NOT NULL DEFAULT 'TWD'
        CHECK (currency = 'TWD'),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (unit_price IS NULL
            AND price_as_of_date IS NULL
            AND price_source_id IS NULL)
        OR
        unit_price IS NOT NULL
    ),

    FOREIGN KEY (etf_code)
        REFERENCES etf_master (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS
idx_manual_holding_updated
ON manual_holding (
    updated_at DESC,
    etf_code
);

-- ============================================================
-- M11-4 不可變候選分析決策快照
-- ============================================================

CREATE TABLE IF NOT EXISTS decision_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    record_type TEXT NOT NULL
        CHECK (record_type = 'CANDIDATE_HOLDING_ANALYSIS'),

    candidate_etf_code TEXT NOT NULL
        CHECK (length(trim(candidate_etf_code)) > 0),

    candidate_name TEXT NOT NULL
        CHECK (length(trim(candidate_name)) > 0),

    analysis_status TEXT NOT NULL
        CHECK (analysis_status IN ('AVAILABLE', 'PARTIAL', 'UNAVAILABLE')),

    outcome TEXT NOT NULL
        CHECK (
            outcome IN (
                'ELIGIBLE',
                'INELIGIBLE',
                'NOT_EVALUATED',
                'UNAVAILABLE'
            )
        ),

    request_json TEXT NOT NULL
        CHECK (length(trim(request_json)) > 0),

    analysis_json TEXT NOT NULL
        CHECK (length(trim(analysis_json)) > 0),

    rationale_json TEXT NOT NULL
        CHECK (length(trim(rationale_json)) > 0),

    exclusions_json TEXT NOT NULL
        CHECK (length(trim(exclusions_json)) > 0),

    alternatives_json TEXT NOT NULL
        CHECK (length(trim(alternatives_json)) > 0),

    risk_notes_json TEXT NOT NULL
        CHECK (length(trim(risk_notes_json)) > 0),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS
idx_decision_record_created
ON decision_record (
    created_at DESC,
    id DESC
);

-- ============================================================
-- V2 ETF 成分股不可變快照
-- ============================================================

CREATE TABLE IF NOT EXISTS etf_constituent_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etf_code TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
    source_url TEXT CHECK (
        source_url IS NULL OR length(trim(source_url)) > 0
    ),
    fetched_at TEXT NOT NULL,
    total_weight_pct REAL NOT NULL CHECK (
        total_weight_pct >= 0 AND total_weight_pct <= 100.5
    ),
    constituent_count INTEGER NOT NULL CHECK (constituent_count >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (etf_code, as_of_date, source_id),
    FOREIGN KEY (etf_code)
        REFERENCES etf_master (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_constituent_snapshot_latest
ON etf_constituent_snapshot (etf_code, as_of_date DESC, id DESC);

CREATE TABLE IF NOT EXISTS etf_constituent_position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    constituent_id TEXT NOT NULL CHECK (length(trim(constituent_id)) > 0),
    constituent_name TEXT NOT NULL CHECK (length(trim(constituent_name)) > 0),
    weight_pct REAL NOT NULL CHECK (weight_pct >= 0 AND weight_pct <= 100),
    rank INTEGER CHECK (rank IS NULL OR rank > 0),
    UNIQUE (snapshot_id, constituent_id),
    FOREIGN KEY (snapshot_id)
        REFERENCES etf_constituent_snapshot (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_constituent_position_security
ON etf_constituent_position (constituent_id, snapshot_id);

-- Additive provenance for the existing etf_master.fund_size projection.
CREATE TABLE IF NOT EXISTS etf_fund_size_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etf_code TEXT NOT NULL REFERENCES etf_master(code),
    fund_code TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency = 'TWD'),
    total_net_assets_twd TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    UNIQUE(etf_code, as_of_date, source_id)
);
