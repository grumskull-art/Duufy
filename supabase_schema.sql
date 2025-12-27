-- Duufy Database Schema for Supabase
-- Copy/paste this into Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============ USERS PROFILE (extends auth.users) ============
CREATE TABLE IF NOT EXISTS profiles (
    id UUID REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, name)
    VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data->>'name');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ============ AUTO-UPDATE TIMESTAMPS ============
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============ RLS HELPER FUNCTION ============
CREATE OR REPLACE FUNCTION is_group_member(check_group_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM group_members 
        WHERE group_id = check_group_id 
        AND user_id = auth.uid()
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

CREATE OR REPLACE FUNCTION is_list_member(check_list_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM shopping_lists sl
        JOIN group_members gm ON sl.group_id = gm.group_id
        WHERE sl.id = check_list_id
        AND gm.user_id = auth.uid()
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;


-- ============ GROUPS ============
CREATE TABLE IF NOT EXISTS groups (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    invite_code TEXT UNIQUE DEFAULT substring(md5(random()::text) from 1 for 8),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============ GROUP MEMBERS ============
CREATE TABLE IF NOT EXISTS group_members (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);


-- ============ SHOPPING LISTS ============
CREATE TABLE IF NOT EXISTS shopping_lists (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Indkøbsliste',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============ LIST ITEMS ============
CREATE TABLE IF NOT EXISTS list_items (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    list_id UUID REFERENCES shopping_lists(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity TEXT,
    unit TEXT,
    category TEXT,
    image_url TEXT,
    checked BOOLEAN DEFAULT FALSE,
    checked_by UUID REFERENCES profiles(id),
    added_by UUID REFERENCES profiles(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Apply update triggers to tables with updated_at
CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_groups_updated_at BEFORE UPDATE ON groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_shopping_lists_updated_at BEFORE UPDATE ON shopping_lists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_list_items_updated_at BEFORE UPDATE ON list_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============ INVITATIONS ============
CREATE TABLE IF NOT EXISTS invitations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    inviter_id UUID REFERENCES profiles(id),
    token TEXT UNIQUE DEFAULT substring(md5(random()::text || now()::text) from 1 for 32),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);


-- ============ ANALYTICS EVENTS ============
CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES profiles(id),
    event_name TEXT NOT NULL,
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============ ERROR LOGS ============
CREATE TABLE IF NOT EXISTS error_logs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES profiles(id),
    error_type TEXT NOT NULL,
    message TEXT,
    stack_trace TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============ ROW LEVEL SECURITY ============

-- Enable RLS on all tables
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE shopping_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE list_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_logs ENABLE ROW LEVEL SECURITY;

-- Profiles: Users can read all, update own
CREATE POLICY "Public profiles are viewable by everyone" ON profiles FOR SELECT USING (true);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

-- Groups: Members can read their groups (using helper function)
CREATE POLICY "Group members can view groups" ON groups FOR SELECT 
    USING (is_group_member(id));
CREATE POLICY "Users can create groups" ON groups FOR INSERT WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Owners can update groups" ON groups FOR UPDATE USING (owner_id = auth.uid());
CREATE POLICY "Owners can delete groups" ON groups FOR DELETE USING (owner_id = auth.uid());

-- Group Members: Members can see other members (using helper function)
CREATE POLICY "Group members can view memberships" ON group_members FOR SELECT 
    USING (is_group_member(group_id));
CREATE POLICY "Group admins can add members" ON group_members FOR INSERT 
    WITH CHECK (EXISTS (
        SELECT 1 FROM group_members 
        WHERE group_id = group_members.group_id 
        AND user_id = auth.uid() 
        AND role IN ('owner', 'admin')
    ));

-- Shopping Lists: Group members can CRUD (using helper function)
CREATE POLICY "Group members can view lists" ON shopping_lists FOR SELECT 
    USING (is_group_member(group_id));
CREATE POLICY "Group members can create lists" ON shopping_lists FOR INSERT 
    WITH CHECK (is_group_member(group_id));
CREATE POLICY "Group members can update lists" ON shopping_lists FOR UPDATE 
    USING (is_group_member(group_id));
CREATE POLICY "Group members can delete lists" ON shopping_lists FOR DELETE 
    USING (is_group_member(group_id));

-- List Items: Group members can CRUD (using helper function)
CREATE POLICY "Group members can view items" ON list_items FOR SELECT 
    USING (is_list_member(list_id));
CREATE POLICY "Group members can create items" ON list_items FOR INSERT 
    WITH CHECK (is_list_member(list_id));
CREATE POLICY "Group members can update items" ON list_items FOR UPDATE 
    USING (is_list_member(list_id));
CREATE POLICY "Group members can delete items" ON list_items FOR DELETE 
    USING (is_list_member(list_id));

-- Invitations: Inviters can manage, anyone can view by token
CREATE POLICY "Users can create invitations" ON invitations FOR INSERT 
    WITH CHECK (inviter_id = auth.uid());
CREATE POLICY "Users can view their invitations" ON invitations FOR SELECT 
    USING (inviter_id = auth.uid() OR email = (SELECT email FROM profiles WHERE id = auth.uid()));

-- Analytics: Users can only see their own
CREATE POLICY "Users can insert analytics" ON analytics_events FOR INSERT WITH CHECK (true);
CREATE POLICY "Users can view own analytics" ON analytics_events FOR SELECT USING (user_id = auth.uid());

-- Error logs: Anyone can insert, admins can view
CREATE POLICY "Anyone can log errors" ON error_logs FOR INSERT WITH CHECK (true);


-- ============ INDEXES FOR PERFORMANCE ============
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_shopping_lists_group ON shopping_lists(group_id);
CREATE INDEX IF NOT EXISTS idx_list_items_list ON list_items(list_id);
CREATE INDEX IF NOT EXISTS idx_list_items_list_checked ON list_items(list_id, checked);  -- Kombinationsindeks for "vis ikke-afkrydsede varer"
CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);
CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_event ON analytics_events(event_name);
CREATE INDEX IF NOT EXISTS idx_error_logs_type ON error_logs(error_type);
