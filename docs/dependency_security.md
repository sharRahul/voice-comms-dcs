# Dependency security

Voice-Comms-DCS keeps `requirements.txt` readable for humans and uses `constraints.txt` as the reproducible pip install path.

## Runtime install

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -e . --no-deps
```

## Development install

```powershell
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m pip install -e . --no-deps
```

## Validation

```powershell
python -m compileall src
python -m pytest -q
ruff check src tests
pip-audit --skip-editable
```

## Updating dependencies

1. Update `requirements.txt` only when the runtime dependency set changes.
2. Update `constraints.txt` intentionally after local testing.
3. Run the tests, lint, and dependency audit before pushing.
4. Do not commit virtual environments, downloaded model files, `.env`, tokens, or local machine paths.

The PyInstaller build script fails if `constraints.txt` is missing so release builds do not silently fall back to broad dependency ranges.
