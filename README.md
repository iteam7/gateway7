# Modular LLM Gateway — Team 7

A gateway that routes requests to LLM providers through pluggable modules.

Plugins are async middleware: they process a request, await the next handler, and process the returning answer.
One YAML order defines the path in both directions; see [plugin authoring and API v2 migration](docs/plugins.md).

> Work in progress for the ITPD course.

- Current week report: [reports/week-03/README.md](reports/week-03/README.md) (in progress)
- Documentation: [docs/](docs/)
- Documentation site: [Gateway7 documentation](https://iteam7.github.io/gateway7/)
- Setup and run: [docs/setup.md](docs/setup.md)
- Customer demo: [docs/demo.md](docs/demo.md)
- Architecture: [docs/architecture/README.md](docs/architecture/README.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Definition of Done: [docs/definition-of-done.md](docs/definition-of-done.md)
- License: [MIT](LICENSE)

Run the deterministic HTTP demonstration from a checkout with Python and uv installed:

```sh
uv sync --locked
uv run --locked python -m demo.run
```

For the manually started gateway in the setup guide, the client sends no provider key:

```sh
curl --fail-with-body http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with the word pong"}]}'
```

The fake upstream returns `pong — deterministic upstream`.
Its response demonstrates the plugin and HTTP path; the real-provider criterion in [US-01](https://github.com/iteam7/gateway7/issues/30) remains a separate check.
