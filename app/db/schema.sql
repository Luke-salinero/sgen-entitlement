-- Defines available subscription plans and their high-level access flags.
CREATE TABLE plans(
    id          INTEGER PRIMARY KEY,
    tier        TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL,
    allow_live  INTEGER NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (allow_live IN (0, 1)),
    CHECK (tier in ('free', 'pro','custom'))
);

-- Defines enforceable limits and constraints for each plan (1:1 with plans).
CREATE TABLE plan_limits(
    plan_id     INTEGER NOT NULL UNIQUE,
    max_n       INTEGER NOT NULL,
    max_k       INTEGER NOT NULL,
    existential_only INTEGER NOT NULL,
    rate_limit  INTEGER NOT NULL,
    rate_window INTEGER NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (existential_only in (0,1)),
    CHECK (max_n >= 1),
    CHECK (max_n <= 2048),
    CHECK (max_k <= max_n),
    CHECK (max_k >= 1),
    CHECK (rate_limit >=1),
    CHECK (rate_window >=1),

    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE TABLE subjects(
    userID      INTEGER PRIMARY KEY,
    apiKeyID    INTEGER NOT NULL UNIQUE,
    accountName TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP 
);

CREATE TABLE subject_plan(
    subject_id  INTEGER PRIMARY KEY,
    plan_id     INTEGER NOT NULL,

    FOREIGN KEY (subject_id) REFERENCES subjects(userID) on DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES plans(id) on DELETE RESTRICT
);


CREATE TABLE subject_plan_limits (
    subject_id      INTEGER PRIMARY KEY,
    max_n           INTEGER NOT NULL,
    max_k           INTEGER NOT NULL,
    existential_only INTEGER NOT NULL,
    rate_limit      INTEGER NOT NULL,
    rate_window     INTEGER NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (existential_only in (0,1)),
    CHECK (max_n >= 1),
    CHECK (max_n <= 2048),
    CHECK (max_k <= max_n),
    CHECK (max_k >= 1),
    CHECK (rate_limit >= 1),
    CHECK (rate_window >= 1),

    FOREIGN KEY (subject_id) REFERENCES subjects(userID) ON DELETE CASCADE
);

CREATE TRIGGER subject_plan_limits_custom 
BEFORE INSERT ON subject_plan_limits
FOR EACH ROW
BEGIN
    SELECT
        CASE 
            WHEN COALESCE((
                SELECT p.tier
                FROM subject_plan sp 
                JOIN plans p ON p.id = sp.plan_id
                WHERE sp.subject_id = NEW.subject_id
            ),'') <> 'custom'
            THEN RAISE(ABORT, 'subject_plan_limits allowed only for custom tier')
        END;
END;

CREATE TRIGGER subject_plan_limits_customUpdates
BEFORE UPDATE ON subject_plan_limits
FOR EACH ROW
BEGIN
    SELECT
        CASE 
            WHEN COALESCE((
                SELECT p.tier
                FROM subject_plan sp 
                JOIN plans p ON p.id = sp.plan_id
                WHERE sp.subject_id = NEW.subject_id
            ),'') <> 'custom'
            THEN RAISE(ABORT, 'subject_plan_limits allowed only for custom tier')
        END;
END;

CREATE TRIGGER delete_subject_limits_no_custom
AFTER UPDATE OF plan_id ON subject_plan
FOR EACH ROW
BEGIN
    DELETE FROM subject_plan_limits
    WHERE subject_id = NEW.subject_id
      AND (
          SELECT tier FROM plans WHERE id = NEW.plan_id
      ) <> 'custom';
END;

CREATE TRIGGER delete_subject_limits_no_custom_after_insert
AFTER INSERT ON subject_plan
FOR EACH ROW
BEGIN
    DELETE FROM subject_plan_limits
    WHERE subject_id = NEW.subject_id
      AND (
          SELECT tier FROM plans WHERE id = NEW.plan_id
      ) <> 'custom';
END;

--SELECT
--  s.userID,
--  p.id AS plan_id,
--  p.tier,
--
--  COALESCE(spl.max_n, pl.max_n) AS max_n,
--  COALESCE(spl.max_k, pl.max_k) AS max_k,
--  COALESCE(spl.existential_only, pl.existential_only) AS existential_only,
--  COALESCE(spl.rate_limit, pl.rate_limit) AS rate_limit,
--  COALESCE(spl.rate_window, pl.rate_window) AS rate_window
--
--FROM subjects s
--JOIN subject_plan sp ON sp.subject_id = s.userID
--JOIN plans p ON p.id = sp.plan_id
--JOIN plan_limits pl ON pl.plan_id = p.id
--LEFT JOIN subject_plan_limits spl ON spl.subject_id = s.userID
--WHERE s.userID = ?;
