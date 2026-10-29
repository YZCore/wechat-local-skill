"""User-selected account-specific conversation exclusions."""
import json
from pathlib import Path

POLICY=Path(__file__).resolve().parent/'excluded_sessions.json'


def excluded_ids(account_fingerprint):
    if not POLICY.exists():
        return set()
    payload=json.loads(POLICY.read_text(encoding='utf-8'))
    return {r['session_id'] for r in payload.get('accounts',{}).get(account_fingerprint,[])}


def exclude_public_accounts(account_fingerprint):
    if not POLICY.exists():
        return False
    payload=json.loads(POLICY.read_text(encoding='utf-8'))
    return bool(payload.get('rules',{}).get(account_fingerprint,{}).get('exclude_public_accounts',False))


def is_public_account(username):
    return username.startswith('gh_')
