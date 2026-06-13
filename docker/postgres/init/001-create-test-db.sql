SELECT 'CREATE DATABASE workstream_test'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'workstream_test'
)\gexec
