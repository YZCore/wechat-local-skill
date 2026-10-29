"""Per-installation paths and group selection; no credentials."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FILE=ROOT/'runtime-settings.json'
SETTINGS=json.loads(FILE.read_text(encoding='utf-8')) if FILE.exists() else {}
GROUP=os.environ.get('WECHAT_BOUND_GROUP',SETTINGS.get('group',''))
VAULT_ROOT=Path(os.environ.get('WECHAT_OBSIDIAN_VAULT',SETTINGS.get('vault',str(ROOT.parent/'Vault'))))
VAULT=VAULT_ROOT/'01_收集箱/微信流'
