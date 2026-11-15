"""Regression checks for repository release hardening and defense-in-depth."""
from pathlib import Path
import os
import sys
from uuid import uuid4

TEST_DB = Path(__file__).resolve().parent / 'portfolioiq_v4_test.sqlite3'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['DATABASE_URL'] = 'sqlite:///' + str(TEST_DB)
os.environ['COOKIE_SECURE'] = 'false'

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select
from server.app import app
from server.store import LoginFailure, SessionLocal


def test_security_headers_and_trusted_host():
    with TestClient(app) as c:
        response = c.get('/')
        assert response.status_code == 200
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['x-frame-options'] == 'DENY'
        assert 'frame-ancestors' in response.headers['content-security-policy']
        assert response.headers['referrer-policy'] == 'no-referrer'
        assert 'root' in response.text
        assert c.get('/api/v4/health', headers={'host': 'unexpected.attacker.example'}).status_code == 400


def test_auth_failure_throttle_is_server_enforced():
    # Clear only this test's shared test database counter, never user databases.
    with SessionLocal() as db:
        db.execute(delete(LoginFailure))
        db.commit()
    try:
        with TestClient(app) as c:
            email = f'{uuid4().hex}@portfolioiq.test'
            for attempt in range(10):
                r = c.post('/api/v4/auth/login', json={'email': email, 'password': 'wrong-password'})
                assert r.status_code == 401, (attempt, r.text)
            r = c.post('/api/v4/auth/login', json={'email': email, 'password': 'wrong-password'})
            assert r.status_code == 429
            assert r.headers['retry-after'] == '900'
            with SessionLocal() as db:
                entries = db.scalars(select(LoginFailure)).all()
                assert len(entries) == 10
                assert all(len(e.ip_hash) == 64 and 'testclient' not in e.ip_hash for e in entries)
    finally:
        with SessionLocal() as db:
            db.execute(delete(LoginFailure))
            db.commit()


def test_unsafe_production_configuration_refuses_startup(monkeypatch):
    monkeypatch.setenv('DEPLOYMENT_MODE', 'production')
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    with pytest.raises(RuntimeError, match='COOKIE_SECURE'):
        with TestClient(app):
            pass
