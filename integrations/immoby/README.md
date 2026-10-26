# Immoby cloud guest-assistance integration

Prototype in shadow mode: automatic guest replies are disabled. No guest dataset, real credentials or booking contacts are stored in this repository.

Includes signed OpenWA webhooks, durable queues, property-scoped knowledge retrieval, configurable GLM/Kimi/DeepSeek transports, nearby web search, and an independent email watchdog. Connectivity alerts wait for a continuous five-minute outage; relinking/action-required alerts are immediate.

Run tests from this directory with `python3 -m unittest discover -s tests -v`. Configure deployment secrets from `.env.example`, mount the private knowledge database separately, and review the Compose services before deployment. WhatsApp pairing and actual PMS booking bindings must be configured on the target cloud host.

The current prototype drafts responses for operator review. Model accuracy, live notification delivery and the production dispatcher require validation before automatic guest sending is enabled.
