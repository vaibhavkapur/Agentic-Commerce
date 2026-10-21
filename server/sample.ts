import type { SourceFiles } from "../src/types";
export const sampleFiles: SourceFiles = {
  "package.json":
    JSON.stringify(
      {
        name: "northstar-checkout",
        version: "1.0.0",
        type: "module",
        dependencies: { express: "5.1.0", stripe: "18.5.0" },
        devDependencies: { typescript: "5.9.2" },
      },
      null,
      2,
    ) + "\n",
  "src/app.ts": `import express from 'express';
import Stripe from 'stripe';

const app = express();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
const processed = new Set<string>();
let fulfillmentCount = 0;

app.use(express.json());

app.post('/webhooks/stripe', express.raw({ type: 'application/json' }), (req, res) => {
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      req.body,
      req.get('stripe-signature')!,
      process.env.STRIPE_WEBHOOK_SECRET!,
    );
  } catch {
    return res.status(400).json({ error: 'Invalid signature' });
  }
  if (!processed.has(event.id)) {
    processed.add(event.id);
    if (event.type === 'payment_intent.succeeded') fulfillmentCount++;
  }
  return res.json({ received: true });
});

app.get('/health', (_req, res) => res.json({ status: 'ok' }));
// Fixture-only observability. Replace the in-memory Set with durable storage.
app.get('/test/fulfillments', (_req, res) => res.json({ count: fulfillmentCount }));
export default app;
`,
  "src/server.ts": `import app from './app';\napp.listen(3000, () => console.log('Checkout ready'));\n`,
  "tsconfig.json": JSON.stringify(
    {
      compilerOptions: {
        target: "ES2022",
        module: "ESNext",
        moduleResolution: "Bundler",
        esModuleInterop: true,
        strict: true,
      },
    },
    null,
    2,
  ),
  "README.md":
    "# Northstar checkout\n\nA small Express fixture with a webhook middleware ordering bug.\n\nThe in-memory event store is for demonstration only.\n",
};
