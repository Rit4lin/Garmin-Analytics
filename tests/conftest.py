import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test-garmin-analytics.db"
os.environ["GARMINTOKENS"] = str(Path("./nonexistent-test-tokens").resolve())
