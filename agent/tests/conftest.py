import os
from pathlib import Path

from dotenv import load_dotenv

# Real keys first (the scenario evals need them), then dummies so the unit tests stay green
# on a keyless clone: Assistant() builds the LiveKit LLM client, which refuses to construct
# without a key, but the unit tests never touch the network. setdefault must come AFTER
# load_dotenv or the dummy wins and the evals fail with 401.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
for var in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
    os.environ.setdefault(var, "test")
