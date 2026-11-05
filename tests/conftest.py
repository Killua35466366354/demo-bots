import sys
from pathlib import Path

# Die Tests importieren gold/, suche/ und ops/ direkt aus dem Repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
