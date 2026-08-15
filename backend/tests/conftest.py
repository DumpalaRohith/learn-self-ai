import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp_dir, "test.db")
# Force the offline mock provider regardless of any real keys in a local .env file.
# Set (not pop) to empty string: main.py's load_dotenv() call only fills in keys that
# are NOT already present in os.environ, so an empty value here wins over the .env file.
for _key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
    os.environ[_key] = ""

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)
