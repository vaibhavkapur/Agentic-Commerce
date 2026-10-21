# Merchant Integration Copilot

A local workspace for inspecting Express payment integrations, generating reviewable patches, and reporting exactly what has been verified.

> **[Read the full documentation](docs/index.md)**

Built with React, TypeScript, Express, and the OpenAI Agents SDK; the interface is branded Ralio. The sample workflow runs without credentials using deterministic source analysis. Docker verification, OpenAI generation, Stripe sandbox checks, and Supabase are optional. This is a local MVP.

## Getting Started

```bash
# Requires Node.js 20.19+ and npm
git clone https://github.com/vaibhavkapur/Merchant-Integration-Copilot.git
cd Merchant-Integration-Copilot
npm ci
npm run dev
```

- UI: http://127.0.0.1:5173
- API: http://127.0.0.1:4318
- Local project data: `.data/projects.json` (excluded from Git)

See [Getting Started](docs/getting-started.md) for building and running the app, and [Configuration](docs/configuration.md) for optional services.

## Quick Example

1. Open the seeded **Northstar checkout** project and inspect the webhook source and proposed patch.
2. Review the diff; generation alone does not mean the code has run.
3. Select **Run verification**. Syntax analysis runs by default; unconfigured Docker and Stripe checks report blocked.
4. Download the patch and evidence report, then apply the patch only to its matching source snapshot.

See the [Demo Script](docs/demo-script.md) for Docker verification and [Testing](docs/testing.md) for acceptance checks. The [original build brief](docs/BUILD_BRIEF.md) describes the larger proposed platform; remaining scope is tracked in [Deployment](docs/deployment.md).
