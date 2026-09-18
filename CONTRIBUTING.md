# Contributing

Use Python 3.12 and install `requirements.txt` in a virtual environment. Setup
instructions are in [README.md](README.md). No credentials are needed for tests.

1. Fork the repository and create a branch for your change.
2. Keep the change focused and add regression coverage for behavior changes.
3. Run `python -m unittest discover -s tests -v`.
4. Run `python -m compileall -q main.py config.py src tests scripts`.
5. Open a pull request describing the problem, change and test results.

Preserve the single CSFloat transport and request counter, complete output
pricing, ten distinct inputs, eligibility checks, fee handling and freshness
checks. Mock marketplace and Discord calls in tests. Do not run live requests
from CI. Explain changes to float math, probabilities and strategy ranking.

Never attach `.env`, webhook URLs, API keys or unredacted logs to issues. For bug
reports include the command, Python/Docker version, sanitized error, relevant
non-secret settings, and expected versus actual behavior.

Contributions are provided under the project's [MIT license](LICENSE).
