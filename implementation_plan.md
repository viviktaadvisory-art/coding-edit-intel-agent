# Implementation Plan: Make coding-edit-intel-agent Ambient

Make the coding-edit-intel-agent agent ambient (event-driven) by setting up a local FastAPI service that processes Pub/Sub trigger messages, normalizes subscription paths, and is configured correctly in `pyproject.toml` and a `Makefile`.

## Proposed Changes

### Configuration & Package Dependencies

#### [MODIFY] [pyproject.toml](file:///c:/Users/vivek/OneDrive%20-%20vivikta.net%201/Documents/Dell/Vivek%20Work/4.%20Personal/Vivikta/Kaggle/coding-edit-intel-agent/pyproject.toml)
- Add `"fastapi>=0.110.0"` and `"uvicorn>=0.28.0"` to the `dependencies` list.

### Application Logic

#### [NEW] [fast_api_app.py](file:///c:/Users/vivek/OneDrive%20-%20vivikta.net%201/Documents/Dell/Vivek%20Work/4.%20Personal/Vivikta/Kaggle/coding-edit-intel-agent/app/fast_api_app.py)
- Create a new file `app/fast_api_app.py`.
- Configure standard Python logging for console logs.
- Retrieve/build the FastAPI app using `get_fast_api_app` from `google.adk.cli.fast_api` with:
  - `agents_dir` targeting the `coding-edit-intel-agent` root directory.
  - `web=False` (ambient agent, no interactive chat UI).
  - `trigger_sources=["pubsub"]` (Pub/Sub driven).
  - `otel_to_cloud=False` (disable cloud tracing / OTEL export).
- Implement `PubSubNormalizeMiddleware` to normalize the Pub/Sub fully-qualified subscription path down to its short name (e.g. from `projects/project-id/subscriptions/sub-name` to `sub-name`).
- Add the middleware to the FastAPI application.
- Expose the `/feedback` route to collect and log feedback using standard Python logging.
- Set up the execution block to run the app using `uvicorn` on port `8080`.

### Build & Execution Automation

#### [NEW] [Makefile](file:///c:/Users/vivek/OneDrive%20-%20vivikta.net%201/Documents/Dell/Vivek%20Work/4.%20Personal/Vivikta/Kaggle/coding-edit-intel-agent/Makefile)
- Create a `Makefile` in the project root with the following targets:
  - `install`: Runs `agents-cli install` (wraps `uv sync`).
  - `playground`: Runs `agents-cli playground` to open the local development playground.
  - `run`: Runs the FastAPI server locally (`uv run python -m app.fast_api_app`).

---

## Verification Plan

### Automated Steps
1. Run `uv sync` to update the dependencies.
2. Run `uv run python -m app.fast_api_app` and verify it starts up successfully on port `8080`.

### Manual Verification
1. Send a mock HTTP POST request simulating a Pub/Sub trigger message to `http://localhost:8080/trigger/pubsub` with a fully-qualified subscription name:
   ```bash
   Invoke-RestMethod -Uri "http://localhost:8080/trigger/pubsub" -Method Post -Body '{"message": {"data": "eyJjbGFpbV9pZCI6ICJDMSJ9"}, "subscription": "projects/my-project/subscriptions/my-subscription"}' -Headers @{"Content-Type"="application/json"}
   ```
2. Verify that the middleware extracts `"my-subscription"` and logs: `Normalized subscription path 'projects/my-project/subscriptions/my-subscription' to 'my-subscription'`.
