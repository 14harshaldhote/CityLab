-- CityLab records. One append-only event log is the source of truth; the other
-- tables are convenient views of it for queries and charts.
CREATE TABLE IF NOT EXISTS runs (
    id          BIGSERIAL PRIMARY KEY,
    seed        BIGINT NOT NULL,
    population  INTEGER NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    run_id   BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id       BIGINT NOT NULL,
    t        INTEGER NOT NULL,          -- simulation minute
    kind     TEXT NOT NULL,
    text     TEXT NOT NULL,             -- plain English, ready for search and RAG
    people   INTEGER[] NOT NULL DEFAULT '{}',
    place    INTEGER,
    data     JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, id)
);
CREATE INDEX IF NOT EXISTS events_kind_t ON events (run_id, kind, t);
CREATE INDEX IF NOT EXISTS events_people ON events USING GIN (people);

CREATE TABLE IF NOT EXISTS daily_stats (
    run_id  BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    day     INTEGER NOT NULL,
    row     JSONB NOT NULL,
    PRIMARY KEY (run_id, day)
);
