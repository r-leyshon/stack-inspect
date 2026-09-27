# stack-inspect

The local collector. Adapters post events here and the UI at <http://127.0.0.1:9477> shows the execution graph. It binds to loopback only. Run it with:

```bash
uvx --from stack-inspect stack-inspect serve
```

During development in this repository:

```bash
uv run stack-inspect serve
```
