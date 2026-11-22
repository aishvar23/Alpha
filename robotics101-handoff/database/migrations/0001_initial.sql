-- Robotics 101 initial migration. Run in development before production review.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE curriculum_topics (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 slug TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL,
 prerequisite_slugs TEXT[] NOT NULL DEFAULT '{}',
 approved BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE episodes (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_number INTEGER UNIQUE NOT NULL CHECK (episode_number > 0),
 title TEXT NOT NULL, topic_id UUID REFERENCES curriculum_topics(id),
 audience TEXT NOT NULL DEFAULT 'beginner',
 target_duration_seconds INTEGER NOT NULL DEFAULT 300,
 status TEXT NOT NULL DEFAULT 'PLANNED',
 version INTEGER NOT NULL DEFAULT 1,
 workflow_instance_id TEXT UNIQUE,
 current_final_artifact_id UUID,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE episode_versions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 version INTEGER NOT NULL CHECK (version > 0),
 episode_spec JSONB NOT NULL,
 source_spec_sha256 CHAR(64) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(episode_id,version)
);
CREATE TABLE scenes (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
 status TEXT NOT NULL DEFAULT 'PENDING',
 current_version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(episode_id,sequence_number)
);
CREATE TABLE scene_versions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 scene_id UUID NOT NULL REFERENCES scenes(id),
 version INTEGER NOT NULL CHECK(version > 0),
 scene_spec JSONB NOT NULL,
 spec_sha256 CHAR(64) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(scene_id,version)
);
CREATE TABLE artifacts (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 scene_id UUID REFERENCES scenes(id),
 artifact_type TEXT NOT NULL,
 blob_key TEXT NOT NULL UNIQUE,
 sha256 CHAR(64) NOT NULL,
 bytes BIGINT NOT NULL CHECK(bytes >= 0),
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE episodes ADD CONSTRAINT fk_current_final_artifact FOREIGN KEY(current_final_artifact_id) REFERENCES artifacts(id);
CREATE TABLE artifact_dependencies (
 parent_artifact_id UUID NOT NULL REFERENCES artifacts(id),
 child_artifact_id UUID NOT NULL REFERENCES artifacts(id),
 PRIMARY KEY(parent_artifact_id,child_artifact_id),
 CHECK(parent_artifact_id <> child_artifact_id)
);
CREATE TABLE jobs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 scene_id UUID REFERENCES scenes(id),
 job_type TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'PENDING',
 attempt INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 3,
 error_code TEXT,
 error_details JSONB,
 started_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ
);
CREATE TABLE approvals (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 artifact_id UUID NOT NULL REFERENCES artifacts(id),
 approved_sha256 CHAR(64) NOT NULL,
 reviewer_subject TEXT NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED','REVISION_REQUESTED')),
 notes TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE publication_jobs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 approved_artifact_id UUID NOT NULL REFERENCES artifacts(id),
 approval_id UUID NOT NULL REFERENCES approvals(id),
 idempotency_key TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'PENDING',
 youtube_video_id TEXT UNIQUE,
 privacy_status TEXT NOT NULL DEFAULT 'private',
 scheduled_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE generation_runs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 episode_id UUID NOT NULL REFERENCES episodes(id),
 scene_id UUID REFERENCES scenes(id),
 provider TEXT NOT NULL,
 model TEXT,
 prompt_version TEXT,
 input_tokens INTEGER NOT NULL DEFAULT 0,
 output_tokens INTEGER NOT NULL DEFAULT 0,
 estimated_cost_usd NUMERIC(14,6) NOT NULL DEFAULT 0,
 started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 finished_at TIMESTAMPTZ
);
CREATE TABLE outbox (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 aggregate_id UUID NOT NULL,
 event_type TEXT NOT NULL,
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 published_at TIMESTAMPTZ
);
CREATE INDEX idx_jobs_status ON jobs(status, started_at);
CREATE INDEX idx_episodes_status ON episodes(status);
CREATE INDEX idx_outbox_unpublished ON outbox(created_at) WHERE published_at IS NULL;
CREATE INDEX idx_artifact_episode ON artifacts(episode_id);
-- NOTE: Add RLS/auth policies, invariant triggers, and production status constraints before rollout.
