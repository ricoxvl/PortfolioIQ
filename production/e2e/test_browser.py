"""Playwright end-to-end browser smoke tests for the compiled React application.

Run against a separately started FastAPI server serving production/web/dist.
These tests are intentionally not marked as locally passed when Chromium navigation
is blocked by the execution environment.
"""
import os
import re
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

BASE_URL = os.getenv('PORTFOLIOIQ_E2E_URL', 'http://127.0.0.1:8000')


def test_create_account_xray_scenario_analyst_and_signout():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE_URL, wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Create your workspace')).to_be_visible(timeout=10000)
        page.get_by_label('Email address').fill(f'e2e-{uuid4().hex}@portfolioiq.test')
        page.get_by_label('Password').fill('StrongUniqueE2EPassword!123')
        page.get_by_role('button', name=re.compile('Create workspace')).click()
        expect(page.get_by_role('heading', name='Overview', exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text('Synthetic example').first).to_be_visible()
        expect(page.get_by_text('Fictional benchmark').first).to_be_visible()
        # Concentration is a proportion, not a signed performance statistic.
        concentration=page.locator('.kpi').filter(has_text='Concentration (top 3)')
        assert not concentration.locator('strong').inner_text().startswith('+')

        page.get_by_role('button', name='Risk Intelligence').click()
        expect(page.get_by_role('heading', name='Historical drawdown')).to_be_visible()
        expect(page.get_by_role('heading', name='Daily return distribution')).to_be_visible()
        expect(page.get_by_text('Observed daily return', exact=True)).to_be_visible()

        page.get_by_role('button', name='Portfolio X-Ray').click()
        expect(page.get_by_role('heading', name='Portfolio X-Ray', exact=True)).to_be_visible()
        expect(page.get_by_text('Fund constituent disclosure')).to_be_visible()
        expect(page.get_by_role('heading', name='ETF coverage and unmapped value')).to_be_visible()
        expect(page.get_by_role('progressbar', name='Mapped ETF value')).to_be_visible()
        page.get_by_role('button', name='Inspect MSFT exposure').click()
        expect(page.get_by_role('heading', name='MSFT exposure detail')).to_be_visible()
        expect(page.get_by_text('Through QQQ')).to_be_visible()

        page.get_by_role('button', name='Scenario Studio').click()
        expect(page.get_by_role('heading', name='Scenario Studio', exact=True)).to_be_visible()
        page.get_by_label('Choose a scenario').select_option('recovery')
        page.get_by_role('button', name=re.compile('Run scenario')).click()
        expect(page.get_by_text('Modeled end value')).to_be_visible()
        expect(page.get_by_role('heading', name='Where the modeled change comes from')).to_be_visible()
        page.get_by_label('Choose a scenario').select_option('custom')
        page.get_by_role('spinbutton', name='Shock for Technology').fill('-30')
        page.get_by_role('button', name=re.compile('Run scenario')).click()
        expect(page.get_by_text('Custom exposure stress')).to_be_visible()
        expect(page.get_by_role('cell', name='-30%')).to_be_visible()

        page.get_by_role('button', name='IQ Analyst').click()
        expect(page.get_by_role('heading', name='IQ Analyst', exact=True)).to_be_visible()
        page.get_by_role('button', name=re.compile('Analyze portfolio')).click()
        expect(page.get_by_text('DETERMINISTIC EXPLANATION')).to_be_visible(timeout=15000)
        expect(page.get_by_text('Source contributions').first).to_be_visible()
        expect(page.locator('.evidence-item').filter(has_text='MSFT')).to_be_visible()

        page.get_by_role('button', name='Transactions').click()
        page.get_by_placeholder('New portfolio name').fill('E2E ledger')
        page.get_by_role('combobox', name='Portfolio type').select_option('ledger')
        page.get_by_role('button', name='Create portfolio').click()
        expect(page.get_by_role('heading', name='Record a transaction')).to_be_visible(timeout=10000)
        expect(page.get_by_role('combobox', name='Choose portfolio')).to_contain_text('E2E ledger')

        page.get_by_role('button', name='Sign out').click()
        expect(page.get_by_role('heading', name='Create your workspace')).to_be_visible(timeout=10000)
        assert not errors, 'JavaScript errors: ' + '; '.join(errors)
        browser.close()


def test_account_export_and_password_confirmed_deletion():
    """Check user-facing privacy controls in the compiled React app."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(accept_downloads=True, viewport={'width': 1366, 'height': 900})
        page.goto(BASE_URL, wait_until='domcontentloaded')
        page.get_by_label('Email address').fill(f'e2e-delete-{uuid4().hex}@portfolioiq.test')
        page.get_by_label('Password').fill('StrongUniqueE2EPassword!123')
        page.get_by_role('button', name=re.compile('Create workspace')).click()
        expect(page.get_by_role('heading', name='Overview', exact=True)).to_be_visible(timeout=15000)
        page.get_by_role('button', name='Settings').click()
        expect(page.get_by_role('heading', name='Account and privacy')).to_be_visible()
        with page.expect_download() as event:
            page.get_by_role('button', name=re.compile('Download my data')).click()
        assert event.value.suggested_filename == 'portfolioiq-account-export.json'
        page.get_by_label('Confirm your password').fill('StrongUniqueE2EPassword!123')
        page.get_by_label('Type DELETE to confirm').fill('DELETE')
        page.get_by_role('button', name='Delete account and data').click()
        expect(page.get_by_role('heading', name='Create your workspace')).to_be_visible(timeout=15000)
        browser.close()