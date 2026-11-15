#!/usr/bin/env python3
"""Validate the disposable demo Blueprint's security-critical invariants.

Requires PyYAML as a development/CI dependency, not a production runtime dependency.
"""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
config = yaml.safe_load((ROOT / 'render.yaml').read_text(encoding='utf-8'))
services = config.get('services') or []
databases = config.get('databases') or []
assert len(services) == 1, 'Expected exactly one web service'
assert len(databases) == 1, 'Expected exactly one private demo database'
web = services[0]
db = databases[0]
assert web['type'] == 'web' and web['runtime'] == 'docker'
assert web['dockerContext'] == '.' and web['dockerfilePath'] == 'production/Dockerfile'
assert web['healthCheckPath'] == '/api/v4/ready'
assert web['autoDeployTrigger'] == 'checksPass'
assert web['plan'] == 'free' and db['plan'] == 'free'
assert db['ipAllowList'] == [], 'Do not allow public database connections'
vars = {x['key']: x for x in web['envVars']}
for name, value in [('DEPLOYMENT_MODE', 'production'), ('COOKIE_SECURE', 'true'),
                    ('BETA_DEMO_ONLY', 'true')]:
    assert str(vars[name].get('value')).lower() == value, f'Unsafe {name}'
for key in ('AUTH_RATE_LIMIT_SECRET', 'BETA_INVITE_CODE'):
    assert vars[key].get('generateValue') is True, f'No automatically generated {key}'
assert vars['TRUSTED_HOSTS']['fromService']['envVarKey'] == 'RENDER_EXTERNAL_HOSTNAME'
assert vars['DATABASE_URL']['fromDatabase']['name'] == db['name']
assert all(v['key'] != 'OPENAI_API_KEY' for v in web['envVars'])
print('Render Blueprint YAML parsed and demo-only deployment invariants passed.')