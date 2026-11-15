"""Phase 5: private-beta gate, user-owned export/deletion and privacy defenses."""
from __future__ import annotations
import os
import sys
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

TEST_DB=Path(__file__).resolve().parent/'portfolioiq_v4_test.sqlite3'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['DATABASE_URL']='sqlite:///'+str(TEST_DB)
os.environ['COOKIE_SECURE']='false'
from server.app import app
from server.store import Account, LoginSession, Portfolio, Holding, SessionLocal

PASSWORD='LongStrongPassword!123'

def signup(c,code=None):
    data={'email':f'{uuid4().hex}@portfolioiq.test','password':PASSWORD}
    if code is not None:data['invite_code']=code
    return c.post('/api/v4/auth/register',json=data)

def authpost(c,url,data):
    return c.post('/api/v4'+url,json=data,headers={'x-csrf-token':c.cookies.get('piq_csrf','')})


def test_invite_is_required_and_not_exposed(monkeypatch):
    invite='An-Example-Long-Random-Invite-Code'
    monkeypatch.setenv('BETA_INVITE_CODE',invite)
    with TestClient(app) as c:
        bad=signup(c)
        assert bad.status_code==403
        assert invite not in bad.text
        bad=signup(c,'incorrect')
        assert bad.status_code==403
        good=signup(c,invite)
        assert good.status_code==201, good.text
        assert invite not in good.text
        assert good.headers['cache-control']=='no-store'


def test_demo_only_policy_rejects_user_mutation(monkeypatch):
    with TestClient(app) as c:
        assert signup(c).status_code==201
        pid=c.get('/api/v4/portfolios').json()[0]['id']
        monkeypatch.setenv('BETA_DEMO_ONLY','true')
        assert authpost(c,'/portfolios',{'name':'Real','kind':'snapshot'}).status_code==403
        r=c.post(f'/api/v4/portfolios/{pid}/prices/csv',files={'file':('prices.csv',b'symbol,date,close\nTEST,2026-11-01,10')},headers={'x-csrf-token':c.cookies.get('piq_csrf','')})
        assert r.status_code==403
        # Safe read-only insights remain functional in demo-only beta.
        assert c.get(f'/api/v4/portfolios/{pid}/overview').status_code==200
        assert authpost(c,f'/portfolios/{pid}/stress',{'preset':'technology_slump'}).status_code==200
        assert authpost(c,f'/portfolios/{pid}/analyst',{'question':'Explain ETF overlap'}).status_code==200


def test_export_contains_only_users_data_without_credentials():
    with TestClient(app) as alice,TestClient(app) as bob:
        ar=signup(alice).json()['user'];br=signup(bob).json()['user']
        assert alice.get('/api/v4/account/export').status_code==200
        a=alice.get('/api/v4/account/export');b=bob.get('/api/v4/account/export')
        assert a.headers['content-disposition'].startswith('attachment;')
        assert a.headers['cache-control']=='no-store'
        data=a.json(); data_b=b.json()
        assert data['schema_version']==1
        assert data['account']['email']==ar['email']
        assert len(data['portfolios'])==1
        assert len(data['portfolios'][0]['holdings'])==8
        assert data_b['account']['email']==br['email']
        assert ar['email'] not in b.text
        assert br['email'] not in a.text
        assert 'password_hash' not in a.text
        assert 'csrf_hash' not in a.text
        assert 'token_hash' not in a.text


def test_export_includes_owned_ledger_history_and_constituents():
    with TestClient(app) as c:
        signup(c)
        pid=authpost(c,'/portfolios',{'name':'Research ledger','kind':'ledger'}).json()['id']
        assert authpost(c,f'/portfolios/{pid}/transactions',{'kind':'DEPOSIT','occurred_on':'2026-01-02','amount':1000}).status_code==201
        doc=c.get('/api/v4/account/export').json()
        ledger=[p for p in doc['portfolios'] if p['name']=='Research ledger'][0]
        assert ledger['kind']=='ledger'
        assert ledger['transactions'][0]['amount']==1000
        assert ledger['transactions'][0]['occurred_on']=='2026-01-02'


def test_delete_requires_csrf_password_and_explicit_confirmation():
    with TestClient(app) as c:
        signup(c)
        assert c.post('/api/v4/account/delete',json={'password':PASSWORD,'confirmation':'DELETE'}).status_code==403
        assert authpost(c,'/account/delete',{'password':'wrong','confirmation':'DELETE'}).status_code==403
        assert authpost(c,'/account/delete',{'password':PASSWORD,'confirmation':'not confirmed'}).status_code==422
        assert c.get('/api/v4/auth/me').status_code==200
        assert authpost(c,'/account/delete',{'password':PASSWORD,'confirmation':'DELETE'}).status_code==200
        assert c.get('/api/v4/auth/me').status_code==401
        assert c.get('/api/v4/account/export').status_code==401


def test_delete_erases_records_sessions_and_preserves_other_user():
    with TestClient(app) as alice, TestClient(app) as bob:
        a=signup(alice).json()['user'];b=signup(bob).json()['user']
        aid=alice.get('/api/v4/portfolios').json()[0]['id']
        bid=bob.get('/api/v4/portfolios').json()[0]['id']
        assert authpost(alice,'/account/delete',{'password':PASSWORD,'confirmation':'DELETE'}).status_code==200
        with SessionLocal() as db:
            assert db.scalar(select(Account).where(Account.id==a['id'])) is None
            assert db.scalar(select(LoginSession).where(LoginSession.account_id==a['id'])) is None
            assert db.scalar(select(Portfolio).where(Portfolio.id==aid)) is None
            assert db.scalars(select(Holding).where(Holding.portfolio_id==aid)).all()==[]
            assert db.scalar(select(Account).where(Account.id==b['id'])) is not None
            assert db.scalar(select(Portfolio).where(Portfolio.id==bid)) is not None
        assert bob.get('/api/v4/auth/me').status_code==200


def test_production_guards_include_invite_and_demo_gate(monkeypatch):
    monkeypatch.setenv('DEPLOYMENT_MODE','production')
    monkeypatch.setenv('COOKIE_SECURE','true')
    monkeypatch.setenv('TRUSTED_HOSTS','testserver')
    monkeypatch.setenv('AUTH_RATE_LIMIT_SECRET','this-is-a-sufficiently-long-test-secret-only')
    monkeypatch.delenv('BETA_INVITE_CODE',raising=False)
    # Existing production SQLite guard protects against accidental public SQLite use.
    with pytest.raises(RuntimeError,match='PostgreSQL'):
        with TestClient(app):pass


def test_production_requires_an_invite_and_demo_only_flag(monkeypatch):
    from server import store
    monkeypatch.setattr(store, 'DATABASE_URL', 'postgresql+psycopg://test-only')
    monkeypatch.setenv('DEPLOYMENT_MODE','production')
    monkeypatch.setenv('COOKIE_SECURE','true')
    monkeypatch.setenv('TRUSTED_HOSTS','beta.test')
    monkeypatch.setenv('AUTH_RATE_LIMIT_SECRET','some-very-long-random-auth-secret-for-ci')
    monkeypatch.delenv('BETA_INVITE_CODE',raising=False)
    with pytest.raises(RuntimeError,match='BETA_INVITE_CODE'):
        with TestClient(app):pass
    monkeypatch.setenv('BETA_INVITE_CODE','long-invite-code-for-testing')
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    with pytest.raises(RuntimeError,match='BETA_DEMO_ONLY'):
        with TestClient(app):pass
