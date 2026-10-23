---
type: llm
focus: trace
weight: 1
---

The agent reads the state from Colab Monitor, with `colab-monitor status` (or `status --json`) or the local API at http://127.0.0.1:26522/api/state, rather than only from other sources.
