# The city's engine

This folder is the part of CityLab that makes Kamalnagar live: its people, their
days, their families, their money and the city's diary. The web page in
`frontend/` is just a window onto it.

To start it on its own:

```bash
pip install -e ".[dev]"
uvicorn citylab.main:app --port 8000
```

To check that everything still works:

```bash
pytest -q
```

See the main [README](../README.md) for what to try once it's running.
