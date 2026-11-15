# PortfolioIQ — ephemeral Render private-beta deployment

**Prepared, NOT deployed.** This configuration is for a small, time-boxed, invitation-only demonstration using **fictional portfolio data only**. The service URL is public on the internet; *private* means registration requires a code, not that the site is private-network-only. Do not store sensitive account statements, brokerage credentials, or real personal financial information.

## Cost and persistence warning

`render.yaml` requests Render's **free** web service and **free** PostgreSQL database for a short-lived demonstration. Render's free web instances can sleep after inactivity and take time to wake. More importantly, its free PostgreSQL database **expires after 30 days** and **has no backups**. Demo accounts and any feedback stored in that database may be lost. If you want a sustained beta with actual invited testers, choose and approve a paid database/hosting plan and configure backups and tested restores **before** inviting them. Costs and availability can change; confirm in your dashboard. The Blueprint creates resources when you approve it in Render, but committing this file does not start hosting or incur costs.

## Create the ephemeral demo (requires your own Render account)

1. Connect the Render app to ChatGPT or sign in to Render, authorize the private `ricoxvl/PortfolioIQ` GitHub repository.
2. In Render choose **New > Blueprint**, connect the repository, and select `render.yaml` on `main`.
3. Review the two proposed resources and verify both plans, region, and anticipated charges **before** clicking Apply. Do not use real financial accounts or secrets.
4. Wait until web build and database start finish, then open the `https://...onrender.com` address from the service dashboard.
5. In Render service Environment, securely view the generated `BETA_INVITE_CODE`; do not commit or publish it. Distribute it to only your test accounts.
6. Check `https://<your service hostname>/api/v4/ready` returns `{"status":"ready"}` and `/robots.txt` disallows crawling.
7. From a separate private browser session, confirm registration without a code is blocked. Register a **test-only** account with the invitation code, view synthetic performance, X-Ray, scenarios, and the guided analyst; export then delete the account.
8. Confirm the app rejects imports and new portfolios while `BETA_DEMO_ONLY=true`. Keep the invite secret and monitor abnormal signups, errors, and usage.

The Render service uses managed HTTPS, the app's `COOKIE_SECURE=true`, strict allowed-host checking against Render's generated hostname, an independent generated rate-limit secret, and its own generated invite code. The Python Docker entrypoint applies Alembic migrations before serving traffic. Render provides `postgresql://` connection URLs; SQLAlchemy's data layer converts them into `postgresql+psycopg://`.

## Operational controls before a broader beta

- Verify the full GitHub Actions pipeline is green, including React, Python, PostgreSQL, Docker build, and Chromium browser tests.
- Use a paid managed PostgreSQL plan with automatic backups and **actually test a restore** in isolation; the free DB is disposable.
- Add edge rate-limiting and verify remote-IP semantics behind Render's reverse proxy; the internal throttle may see one shared proxy IP.
- Configure an email verification and password-recovery provider, legal/privacy notice and a defined retention policy before collecting any non-demo personal data.
- Keep demo-only mode on. Avoid sending data to third-party LLMs during this demo.
- Add a service owner/incident channel, usage budget, monitoring, and an explicit shutdown date.

## Shutdown and costs

Delete the Blueprint resources in Render when finished. Deleting a web service does not always delete its database; check both. Backups and user credentials should be handled through Render's own secure controls, never in Git or chat. This guide is not a security audit, investment-advice approval, or authorization to spend money.

## Validation

Use CI and the local backend tests before creating resources. For a live deployment, verify HTTPS, response headers, readiness, invitation gating, account deletion, and import rejection on the actual Render host. The existence of `render.yaml` is not proof of a successful deploy.