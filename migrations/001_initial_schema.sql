-- Idempotent migration for groups, group_members, items with RLS and policies

-- 1) Create tables if missing
CREATE TABLE IF NOT EXISTS groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  owner_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS group_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  role TEXT DEFAULT 'member',
  joined_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  quantity TEXT,
  unit TEXT,
  category TEXT,
  checked BOOLEAN DEFAULT false,
  added_by TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2) Create indexes if missing
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'i'
      AND c.relname = 'idx_items_group_id'
      AND n.nspname = 'public'
  ) THEN
    EXECUTE 'CREATE INDEX idx_items_group_id ON items(group_id);';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'i'
      AND c.relname = 'idx_items_group_checked'
      AND n.nspname = 'public'
  ) THEN
    EXECUTE 'CREATE INDEX idx_items_group_checked ON items(group_id, checked);';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'i'
      AND c.relname = 'idx_group_members_group_id'
      AND n.nspname = 'public'
  ) THEN
    EXECUTE 'CREATE INDEX idx_group_members_group_id ON group_members(group_id);';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'i'
      AND c.relname = 'idx_group_members_user_id'
      AND n.nspname = 'public'
  ) THEN
    EXECUTE 'CREATE INDEX idx_group_members_user_id ON group_members(user_id);';
  END IF;
END
$$;

-- 3) Enable RLS on tables (idempotent)
ALTER TABLE IF EXISTS groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS items ENABLE ROW LEVEL SECURITY;

-- 4) Create policies only if they don't already exist
DO $$
BEGIN
  -- service_role_groups
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE policyname = 'service_role_groups' AND schemaname = 'public' AND tablename = 'groups'
  ) THEN
    EXECUTE $sql$
      CREATE POLICY service_role_groups ON groups FOR ALL
        USING (true) WITH CHECK (true);
    $sql$;
  END IF;

  -- service_role_group_members
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE policyname = 'service_role_group_members' AND schemaname = 'public' AND tablename = 'group_members'
  ) THEN
    EXECUTE $sql$
      CREATE POLICY service_role_group_members ON group_members FOR ALL
        USING (true) WITH CHECK (true);
    $sql$;
  END IF;

  -- service_role_items
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE policyname = 'service_role_items' AND schemaname = 'public' AND tablename = 'items'
  ) THEN
    EXECUTE $sql$
      CREATE POLICY service_role_items ON items FOR ALL
        USING (true) WITH CHECK (true);
    $sql$;
  END IF;
END
$$;

-- 5) Ensure replica identity for items (idempotent)
ALTER TABLE IF EXISTS items REPLICA IDENTITY FULL;
