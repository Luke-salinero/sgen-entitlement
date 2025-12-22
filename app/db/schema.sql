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
    CHECK (tier in ('free', 'pro'))
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
    userID  INTEGER PRIMARY KEY,
    apiKeyID INTEGER NOT NULL UNIQUE,
    accountName TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,


);

CREATE TABLE subject_plan(
    subject_id  INTEGER PRIMARY KEY,
    plan_id   INTEGER NOT NULL,

    FOREIGN KEY (subject_id) REFERENCES subjects(userID) on DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES plans(id) on DELETE RESTRICT
);


