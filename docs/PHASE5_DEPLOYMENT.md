# PortfolioIQ Phase 5 — private beta deployment and safety runbook

**Status: prepared, not deployed.** Never treat this configuration as a security audit or a financial-data-production launch. The private beta accepts only the fictional demonstration portfolio. Testers can use the guided analyst, Portfolio X-Ray, risk views, and scenario simulation; real imported transactions and holdings are blocked by server-side policy.

## Prerequisites

- A VM or server you control, a DNS name, and firewall allowing inbound TCP 80/443 and optionally UDP 443. Do **not** expose PostgreSQL or FastAPI ports on the public internet.
- Docker Engine with Docker Compose, plus explicit control over secrets, access, firewall, domain and backups. You are responsible for cloud hosting charges.
- A strong per-deployment database password, authentication rate-limit secret, and an invite code distributed privately. Never commit `.env.beta`.
- A separate security review before opening the beta to strangers or entering real investment records.

## First deployment (not executed by ChatGPT)

```bash
cd production
cp .env.beta.example .env.beta
# Edit .env.beta. Set your domain, and use 32+ character URL-safe secrets.
chmod 600 .env.beta
# Confirm your DNS points to the host and review the firewall.
docker compose --env-file .env.beta -f compose.beta.yaml config
# Review interpolated config carefully. It may contain secrets; do not paste it publicly.
docker compose --env-file .env.beta -f compose.beta.yaml up -d --build
# Caddy obtains HTTPS certificates when DNS/ports allow ACME.
docker compose --env-file .env.beta -f compose.beta.yaml ps
```

The app service applies Alembic migrations before accepting requests. Postgres stores data in a named volume. Caddy is the only service with published ports. The app has HTTPS-only session cookies and strict allowed-host handling.

## Before allowing testers

1. Open `https://YOUR_BETA_DOMAIN` from outside the server. Confirm a valid TLS certificate, correct response headers, and no warnings.
2. Attempt to register without an invitation. The backend must respond 403.
3. Sign up with the invite code. Verify the demo dashboard, ETF X-Ray, stress scenarios, guided analyst, data export and account deletion.
4. Confirm that creating portfolios or importing CSVs returns 403 in beta-only mode.
5. Run `pytest` and check GitHub Actions. Resolve red jobs before sharing the link.
6. Confirm backups/restore, logging, incident contact, privacy notice, and your hosting provider's access/data policies. Avoid storing identifiable investment records.

## Backup / restore drill

Back up a running PostgreSQL beta instance to a file **outside your repository** and encrypt/store it using your hosting provider's managed backup policy. Example for an operator only:

```bash
# From production/ on the beta server, securely redirect to a protected directory.
docker compose --env-file .env.beta -f compose.beta.yaml exec -T postgres \
  pg_dump -U portfolioiq -d portfolioiq -Fc > /secure/backup/portfolioiq_YYYYMMDD.dump
```

A backup is not considered valid until a restore into a **separate** test database has been verified. Do not restore over the live beta. Account deletion removes active database rows but cannot retroactively erase old encrypted backups; set and disclose a bounded backup-retention policy.

## Known limitations / launch blockers

- No managed email verification or password recovery yet. Use invitation-only demo testing, not an open public signup.
- Behind a reverse proxy, the built-in sign-in throttle sees the proxy peer address. This is a conservative shared-IP limit, not an adequate stand-alone anti-abuse solution. Apply a trusted edge rate-limit and review proxy/IP handling before wider launch.
- No live pricing or brokerage connection. All seeded values and fund holdings are fictional; AI uses guided calculations unless explicitly separately configured.
- Docker image build, Caddy TLS, real Postgres against a host, and browser acceptance testing must be verified in a real deployment environment. This package is scaffolding, not proof of deployment.
- Production regulatory, security, privacy and accessibility reviews are still outstanding. Do not market this as a regulated financial service.

## Rollback

Keep a tagged, known-good app image and a tested backup. Roll back app code only if database schema compatibility is verified; never run destructive migration downgrades against live customer data without a reviewed recovery plan.
