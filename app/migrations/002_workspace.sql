ALTER TABLE conversations ADD COLUMN custom_title TEXT;
ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
CREATE TABLE provider_usage (
    owner TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL,
    PRIMARY KEY(owner, day)
);
