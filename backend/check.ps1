# Single local gate: lint, format check, types, tests. Run from backend/.
$py = ".\.venv\Scripts\python.exe"
& $py -m ruff check . ; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m ruff format --check . ; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m mypy app ; if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py -m pytest -q ; exit $LASTEXITCODE
