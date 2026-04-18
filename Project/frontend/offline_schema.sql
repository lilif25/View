PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

------------------------------------------------------------
-- 1) 用户表（业务字段对齐 app_users）
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offline_app_users (
    local_user_id      TEXT PRIMARY KEY,                      -- 本地主键（UUID字符串）
    cloud_user_id      TEXT UNIQUE,                           -- 在线 app_users.id

    email              TEXT,
    display_name       TEXT,
    metadata           TEXT DEFAULT '{}',                     -- JSON字符串

    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

    sync_status        TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending','synced','failed')),
    sync_error         TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    synced_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_offline_app_users_sync_status
ON offline_app_users(sync_status);


------------------------------------------------------------
-- 2) 运行批次表（业务字段对齐 analysis_runs）
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offline_analysis_runs (
    local_run_id       TEXT PRIMARY KEY,                      -- 本地主键（UUID字符串）
    cloud_run_id       TEXT UNIQUE,                           -- 在线 analysis_runs.id

    local_user_id      TEXT NOT NULL,                         -- FK -> offline_app_users.local_user_id
    cloud_user_id      TEXT,                                  -- 在线 user_id 冗余字段

    source_filename    TEXT NOT NULL,
    row_count          INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'processing',
    is_current         INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0,1)),
    metadata           TEXT DEFAULT '{}',                     -- JSON字符串

    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at       TEXT,
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

    -- 与你当前重置归档逻辑对齐
    history_reason     TEXT,                                  -- 例如 reset
    archived_at        TEXT,

    sync_status        TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending','synced','failed')),
    sync_error         TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    synced_at          TEXT,

    FOREIGN KEY (local_user_id) REFERENCES offline_app_users(local_user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_offline_runs_user_created
ON offline_analysis_runs(local_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_offline_runs_sync_status
ON offline_analysis_runs(sync_status);

CREATE INDEX IF NOT EXISTS idx_offline_runs_current
ON offline_analysis_runs(local_user_id, is_current);


------------------------------------------------------------
-- 3) 评论明细表（业务字段对齐 analyzed_reviews）
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offline_analyzed_reviews (
    local_review_id    TEXT PRIMARY KEY,                      -- 本地主键（UUID字符串）
    cloud_review_id    TEXT UNIQUE,                           -- 在线 analyzed_reviews.id

    local_run_id       TEXT NOT NULL,                         -- FK -> offline_analysis_runs.local_run_id
    cloud_run_id       TEXT,                                  -- 在线 run_id 冗余字段
    local_user_id      TEXT NOT NULL,                         -- FK -> offline_app_users.local_user_id
    cloud_user_id      TEXT,                                  -- 在线 user_id 冗余字段

    product_id         TEXT,
    product_name       TEXT,
    rating             REAL,
    review_content     TEXT,
    sentiment_score    REAL,
    product_category   TEXT,
    sentiment_label    TEXT CHECK (sentiment_label IN ('正面','负面','中性')),
    solution           TEXT,
    review_date        TEXT,
    review_hash        TEXT,

    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

    sync_status        TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending','synced','failed')),
    sync_error         TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    synced_at          TEXT,

    FOREIGN KEY (local_run_id) REFERENCES offline_analysis_runs(local_run_id) ON DELETE CASCADE,
    FOREIGN KEY (local_user_id) REFERENCES offline_app_users(local_user_id) ON DELETE CASCADE,

    -- 防止同一批次内重复行（可按你的真实数据调整）
    UNIQUE (local_run_id, review_hash)
);

CREATE INDEX IF NOT EXISTS idx_offline_reviews_run
ON offline_analyzed_reviews(local_run_id);

CREATE INDEX IF NOT EXISTS idx_offline_reviews_sync_status
ON offline_analyzed_reviews(sync_status);

CREATE INDEX IF NOT EXISTS idx_offline_reviews_user_created
ON offline_analyzed_reviews(local_user_id, created_at DESC);


------------------------------------------------------------
-- 4) 反馈事件表（业务字段对齐 feedback_events）
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offline_feedback_events (
    local_feedback_id  TEXT PRIMARY KEY,                      -- 本地主键（UUID字符串）
    cloud_feedback_id  TEXT UNIQUE,                           -- 在线 feedback_events.id

    local_user_id      TEXT NOT NULL,
    cloud_user_id      TEXT,

    feedback_type      TEXT NOT NULL,
    content            TEXT NOT NULL,
    metadata           TEXT DEFAULT '{}',
    status             TEXT NOT NULL DEFAULT 'submitted',

    analysis           TEXT,                                  -- JSON字符串（兼容你现有 backend 结构）
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

    sync_status        TEXT NOT NULL DEFAULT 'pending' CHECK (sync_status IN ('pending','synced','failed')),
    sync_error         TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    synced_at          TEXT,

    FOREIGN KEY (local_user_id) REFERENCES offline_app_users(local_user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_offline_feedback_user_created
ON offline_feedback_events(local_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_offline_feedback_sync_status
ON offline_feedback_events(sync_status);


------------------------------------------------------------
-- 5) 同步队列表（离线 -> 在线）
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offline_sync_queue (
    queue_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type        TEXT NOT NULL CHECK (entity_type IN ('app_users','analysis_runs','analyzed_reviews','feedback_events')),
    local_entity_id    TEXT NOT NULL,
    action_type        TEXT NOT NULL CHECK (action_type IN ('insert','update','delete')),
    priority           INTEGER NOT NULL DEFAULT 100,
    status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
    retry_count        INTEGER NOT NULL DEFAULT 0,
    next_retry_at      TEXT,
    last_error         TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE (entity_type, local_entity_id, action_type, status)
);

CREATE INDEX IF NOT EXISTS idx_sync_queue_status_priority
ON offline_sync_queue(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_sync_queue_next_retry
ON offline_sync_queue(next_retry_at);


------------------------------------------------------------
-- 6) 同步日志表
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offline_sync_log (
    log_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_batch_id      TEXT,
    entity_type        TEXT NOT NULL,
    local_entity_id    TEXT NOT NULL,
    cloud_entity_id    TEXT,
    result             TEXT NOT NULL CHECK (result IN ('success','failed','skipped')),
    detail             TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sync_log_batch
ON offline_sync_log(sync_batch_id);

CREATE INDEX IF NOT EXISTS idx_sync_log_entity
ON offline_sync_log(entity_type, local_entity_id);


------------------------------------------------------------
-- 7) 常用视图
------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_offline_current_runs AS
SELECT *
FROM offline_analysis_runs
WHERE is_current = 1;

CREATE VIEW IF NOT EXISTS v_offline_pending_sync AS
SELECT 'app_users' AS entity_type, local_user_id AS local_id, sync_status, retry_count, updated_at
FROM offline_app_users
WHERE sync_status <> 'synced'
UNION ALL
SELECT 'analysis_runs', local_run_id, sync_status, retry_count, updated_at
FROM offline_analysis_runs
WHERE sync_status <> 'synced'
UNION ALL
SELECT 'analyzed_reviews', local_review_id, sync_status, retry_count, updated_at
FROM offline_analyzed_reviews
WHERE sync_status <> 'synced'
UNION ALL
SELECT 'feedback_events', local_feedback_id, sync_status, retry_count, updated_at
FROM offline_feedback_events
WHERE sync_status <> 'synced';


------------------------------------------------------------
-- 8) 可选触发器：自动更新 updated_at
------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_offline_app_users_updated_at
AFTER UPDATE ON offline_app_users
FOR EACH ROW
BEGIN
    UPDATE offline_app_users SET updated_at = datetime('now') WHERE local_user_id = OLD.local_user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_offline_runs_updated_at
AFTER UPDATE ON offline_analysis_runs
FOR EACH ROW
BEGIN
    UPDATE offline_analysis_runs SET updated_at = datetime('now') WHERE local_run_id = OLD.local_run_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_offline_reviews_updated_at
AFTER UPDATE ON offline_analyzed_reviews
FOR EACH ROW
BEGIN
    UPDATE offline_analyzed_reviews SET updated_at = datetime('now') WHERE local_review_id = OLD.local_review_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_offline_feedback_updated_at
AFTER UPDATE ON offline_feedback_events
FOR EACH ROW
BEGIN
    UPDATE offline_feedback_events SET updated_at = datetime('now') WHERE local_feedback_id = OLD.local_feedback_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sync_queue_updated_at
AFTER UPDATE ON offline_sync_queue
FOR EACH ROW
BEGIN
    UPDATE offline_sync_queue SET updated_at = datetime('now') WHERE queue_id = OLD.queue_id;
END;

COMMIT;