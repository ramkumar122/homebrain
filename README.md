# HomeBrain

> **Alexa knows who is in the room. HomeBrain decides what that person is allowed to do.**

HomeBrain is a self-hosted [MCP](https://modelcontextprotocol.io) server for Alexa+. It gives a household a durable brain for home operations. It knows what the household owns and what's covered, and it runs repair cases that last many turns and many days: troubleshooting, finding a provider, booking with passkey verification, and reminders.

**Status:** under construction for the Amazon "Build, Ship, Shape" hackathon (Alexa+ track). See [DESIGN.md](DESIGN.md) for the approved design and dated plan.

## Honest labels

- HomeBrain **does not recognise voices**. Alexa+ does that; an MCP tool call carries no audio.
- The demo conversation is driven by an **Alexa+ stand-in: Bedrock Claude driving the same MCP tools Alexa+ would call.** It is not Alexa.
- Service providers and bookings are **demo fixtures** (`data_source: "DEMO_FIXTURE"`).

## Quick start (local)

```bash
make install     # uv sync + pre-commit hooks
make check       # lint, type-check, tests
make up          # docker compose: server + DynamoDB Local
curl localhost:8080/healthz
```

## Licence

Apache-2.0. See [LICENSE](LICENSE).
