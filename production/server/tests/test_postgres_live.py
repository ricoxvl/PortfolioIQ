"""Runs only in GitHub CI against the real PostgreSQL service, not a SQLite mock."""
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

if not os.getenv('TEST_POSTGRES_URL'):
    pytest.skip('Set TEST_POSTGRES_URL to exercise an actual PostgreSQL server', allow_module_level=True)

os.environ['DATABASE_URL'] = os.environ['TEST_POSTGRES_URL']
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import inspect
from fastapi.testclient import TestClient
from server.app import app
from server.store import engine


def test_postgres_migrated_schema_and_private_portfolios():
    assert engine.dialect.name == 'postgresql'
    inspector = inspect(engine)
    assert {'accounts', 'portfolios', 'transactions', 'prices', 'login_failures', 'market_benchmark_bars', 'market_fetch_attempts', 'issuer_verified_snapshots', 'price_import_audits'} <= set(inspector.get_table_names())
    with TestClient(app) as alice, TestClient(app) as bob:
        for client in (alice, bob):
            response = client.post('/api/v4/auth/register', json={
                'email': f'{uuid4().hex}@example.test', 'password': 'long-github-ci-test-password'})
            assert response.status_code == 201, response.text
        pid = alice.get('/api/v4/portfolios').json()[0]['id']
        assert alice.get(f'/api/v4/portfolios/{pid}/overview').status_code == 200
        assert alice.get(f'/api/v4/portfolios/{pid}/market').status_code == 200
        assert bob.get(f'/api/v4/portfolios/{pid}/market').status_code == 404
        assert bob.get(f'/api/v4/portfolios/{pid}/data-integrity').status_code == 404
        assert alice.get(f'/api/v4/portfolios/{pid}/data-integrity').status_code == 200
        assert bob.get(f'/api/v4/portfolios/{pid}/overview').status_code == 404
        headers = {'X-CSRF-Token': alice.cookies['piq_csrf']}
        resp = alice.post('/api/v4/portfolios', json={'name': 'PG ledger', 'kind': 'ledger'}, headers=headers)
        assert resp.status_code == 201, resp.text
        ledger_id = resp.json()['id']
        resp = alice.post(f'/api/v4/portfolios/{ledger_id}/transactions', json={
            'occurred_on': '2026-01-02', 'kind': 'DEPOSIT', 'amount': 1000}, headers=headers)
        assert resp.status_code == 201, resp.text
        assert bob.get(f'/api/v4/portfolios/{ledger_id}/transactions').status_code == 404
        assert alice.get(f'/api/v4/portfolios/{ledger_id}/overview').json()['summary']['total_value'] == 1000