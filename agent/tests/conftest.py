import os

# Assistant() builds the LiveKit LLM client, which refuses to construct without a key.
# The unit tests never call the network, so dummy values keep them green on a keyless clone.
for var in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
    os.environ.setdefault(var, "test")
