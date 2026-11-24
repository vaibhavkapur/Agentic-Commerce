# Getting Started

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

## Prerequisites and Clone

Requires Node.js 20.19+ and npm. Docker is needed only for isolated verification.

```bash
git clone https://github.com/vaibhavkapur/Merchant-Integration-Copilot.git
cd Merchant-Integration-Copilot
```

## Run Locally

Requires Node.js 20.19+ and npm. No credentials are needed for the sample workflow.

```sh
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. The API listens on **127.0.0.1:4318**. A Northstar checkout sample is created on first start. Local project data persists in `.data/projects.json`, excluded from Git.

```sh
npm test          # Independent application/API acceptance tests
npm run build    # Type-check the app and create dist/
npm start        # Serve the built app and API on port 4318
npm run test:runner # Run Docker acceptance tests after runner:build
```

The initial sample patch is generated with deterministic source analysis, not a model call. It has not been executed. Click **Run verification** to collect evidence. Without additional configuration, syntax analysis runs and Docker/Stripe checks explicitly report blocked.

See [Configuration](configuration.md) to enable services and [Demo Script](demo-script.md) for the sample walkthrough.
