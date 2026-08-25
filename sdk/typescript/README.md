# NeuroWeave TypeScript SDK

Integrate the NeuroWeave Cognitive Runtime Platform into any AI agent in
under five minutes. Zero runtime dependencies — built on native `fetch`
(Node 18+ or any modern browser).

## Install

```bash
cd sdk/typescript
npm install
npm run build
```

## Quick Start

```ts
import { CognitiveAgent } from "neurowave";

const agent = new CognitiveAgent({
  provider: "google",
  memory: true,
  worldModel: true,
  predictiveRecall: true,
  contextComposer: true,
});

const response = await agent.chat("123", "Help me design a distributed cache.");
console.log(response.response);
```

Point `baseUrl` at your running NeuroWeave server (defaults to
`http://localhost:8000`):

```ts
const agent = new CognitiveAgent({
  baseUrl: "https://neuroweave.your-domain.com",
  apiKey: "...",
});
```

## Lower-level access

```ts
import { NeuroWeaveClient } from "neurowave";

const client = new NeuroWeaveClient({ baseUrl: "http://localhost:8000" });
console.log(await client.metrics("123"));
console.log(await client.explain("123", "memory", "mem-id"));
```

## Privacy

```ts
await agent.forgetUser("123"); // GDPR/CCPA right to be forgotten
```
