.PHONY: install playground lint test run

install:
	agents-cli install

playground:
	agents-cli playground

run:
	uv run python -m app.fast_api_app
