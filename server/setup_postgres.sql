-- Execute como administrador do PostgreSQL (ex.: usuário postgres).
-- ALTERE A SENHA antes de usar em produção.

CREATE ROLE technord_app WITH LOGIN PASSWORD 'ALTERE_ESTA_SENHA';

-- Execute o CREATE DATABASE conectado ao banco postgres (não dentro de uma transação).
CREATE DATABASE technord
    WITH OWNER = technord_app
         ENCODING = 'UTF8';

-- Depois conecte-se ao banco technord e conceda o schema ao usuário da aplicação.
-- Em instalações recentes do PostgreSQL, o proprietário já terá os privilégios necessários.
GRANT ALL ON SCHEMA public TO technord_app;
