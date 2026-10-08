"""Script to export FastAPI OpenAPI specification to docs/openapi.json."""

import json
from pathlib import Path

from app.main import app

docs_dir = Path("docs")
docs_dir.mkdir(parents=True, exist_ok=True)
openapi_path = docs_dir / "openapi.json"

openapi_schema = app.openapi()
openapi_path.write_text(json.dumps(openapi_schema, indent=2))
print(f"Exported OpenAPI spec to {openapi_path}")
