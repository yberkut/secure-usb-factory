# Contributing

Secure USB Factory is a destructive-storage toolkit. Treat every hardware scenario as unsafe unless you are using disposable media.

## Local checks

```bash
make bootstrap
make test
make lint
make package
```

E2E scenarios use real devices and packaged tools. Prepare them explicitly:

```bash
make e2e-config
# edit tests/e2e/e2e.env with disposable media values
make package
make e2e-smoke
```

Do not commit `tests/e2e/e2e.env`, `build/`, or `dist/`.
