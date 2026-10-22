-- 実起動の試験で使うテーブル（PostgreSQL の初回起動時に作る）
create table todos (
    id serial primary key,
    title text not null,
    done boolean not null default false,
    created_at timestamptz not null default now()
);
