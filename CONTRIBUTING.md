# Contributing to Bakery Lab

Bug reports, clearer instructions, small fixes, and feature ideas are welcome.
You do not need machine-learning experience to contribute.

## Try the app

Use Python 3.11 or newer. From the project folder, run:

```sh
python serve.py
```

On Windows, `py serve.py` also works. On macOS or Linux, you may need
`python3 serve.py`. The daily log uses only Python's standard library. It saves
your records in `local/waste-log.sqlite3` on your computer.

The optional sales experiment and the full test suite need additional packages.
They are separate from using the daily log.

## Make a change

1. Fork the repository and create a branch for your change, or download the
   project to explore it first.
2. Keep a pull request focused on one fix or improvement. For a large feature,
   describe the idea in an issue before spending time building it.
3. Explain what changed and how you checked it. Add a small regression test when
   fixing behaviour that could break again.
4. Update the instructions when the way someone uses the app changes. For visual
   changes, include a screenshot with fictional records.

To install the development tools and run the checks on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests -q
```

On macOS or Linux, use `python3 -m venv .venv`, then replace
`.\.venv\Scripts\python` with `.venv/bin/python` in the remaining commands.
If you already activated your development environment, run `python -m pytest tests -q`.
The first package installation requires internet access; the bundled-data tests
run locally. Tests use temporary databases rather than your personal daily log.

The browser-state checks use Node.js 18 or newer and no third-party Node
packages. Run `node tests/test_ui_state.cjs` to check recording coverage,
unknown measurements, backups, and delayed-response warning handling. These
checks exercise state behaviour; they do not replace visual browser testing.

If you change the forecasting analysis or dashboard template, run `python run.py`
in that environment and review the generated results. Keep scaled sales values
separate from real item counts and kilograms. Forecast error is not evidence of
food saved.

## Share safe examples

- Use the smallest fictional example that shows a problem. Mention whether you
  expected a different result or saw an error.
- Do not attach a real bakery's records, customer or employee details, database
  files, `.env` files, passwords, tokens, or other credentials to issues or pull
  requests. Check screenshots and notebook outputs too.
- Keep `local/`, virtual environments, caches, and personal exports out of your
  changes. Keep the bundled dataset's licence and attribution notices.

For a possible security vulnerability, follow [SECURITY.md](SECURITY.md) rather
than posting technical details in a public issue.
