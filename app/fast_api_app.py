# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging
import os

from fastapi import FastAPI, Request
from google.adk.cli.fast_api import get_fast_api_app
from starlette.middleware.base import BaseHTTPMiddleware

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# Configure standard console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

setup_telemetry()

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

from fastapi.responses import HTMLResponse

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=False,
    trigger_sources=["pubsub"],
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=False,
)
app.title = "ClaimGuardAI"
app.description = "ClaimGuardAI Medical Coding Audit Agent"


@app.get("/", response_class=HTMLResponse)
def read_index():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)



class PubSubNormalizeMiddleware(BaseHTTPMiddleware):
    """Middleware to normalize Pub/Sub subscription path to a short name."""
    async def dispatch(self, request: Request, call_next):
        if "/trigger/pubsub" in request.url.path and request.method == "POST":
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                    subscription = data.get("subscription")
                    if subscription and isinstance(subscription, str):
                        # Extract the subscription name from the end of the path
                        if "/" in subscription:
                            normalized = subscription.split("/")[-1]
                            data["subscription"] = normalized
                            logger.info(f"Normalized subscription path '{subscription}' to '{normalized}'")
                        
                        # Re-encode body and override receive to feed it forward
                        new_body = json.dumps(data).encode("utf-8")
                        async def receive():
                            return {"type": "http.request", "body": new_body, "more_body": False}
                        request._receive = receive
                except Exception as e:
                    logger.warning(f"Failed to parse or normalize Pub/Sub body: {e}")
        return await call_next(request)


app.add_middleware(PubSubNormalizeMiddleware)


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.info(f"Feedback received: {feedback.model_dump()}")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
