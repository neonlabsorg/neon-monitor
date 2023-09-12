CREATE TABLE IF NOT EXISTS solana_clusters (
    version TEXT NOT NULL,
    cluster TEXT NOT NULL,
    notified BOOLEAN DEFAULT FALSE,
    UNIQUE (version, cluster)
);

CREATE TABLE IF NOT EXISTS github_versions (
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    notified BOOLEAN DEFAULT FALSE,
    UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS programs (
    name TEXT NOT NULL,
    cluster TEXT NOT NULL,
    last_slot INT NOT NULL,
    notified BOOLEAN DEFAULT FALSE,
    UNIQUE (name, cluster)
);