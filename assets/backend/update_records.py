"""Preserve the prior local index, then refresh from the current WeChat account."""
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime,timezone,timedelta

from wechat_index import ROOT, INDEX, refresh
from wx4.paths import list_account_dirs

stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
with contextlib.closing(sqlite3.connect(INDEX.as_uri()+'?mode=ro',uri=True)) as con:
    old={k:json.loads(v) for k,v in con.execute('SELECT key,value FROM metadata')}
    accounts=list_account_dirs()
    if not accounts or hashlib.sha256(accounts[0]['wxid'].encode()).hexdigest()[:16]!=old['account_fingerprint']:
        raise RuntimeError('当前账号与已有索引不一致，尚未更新记录。')
    backup=ROOT/'data/index-history'/stamp/'wechat-local-index.sqlite'
    backup.parent.mkdir(parents=True,exist_ok=True)
    with contextlib.closing(sqlite3.connect(backup)) as target:
        con.backup(target)

baseline=dict(backup_path=str(backup),previous_indexed_at=old['indexed_at'],previous_counts=old['counts'])
(ROOT/'logs/latest-update-baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2),encoding='utf-8')
print('Previous index backed up; rebuilding current records.',flush=True)

class Tee:
    def __init__(self,console,file):
        self.console=console;self.file=file
    def write(self,text):
        self.console.write(text);self.file.write(text)
    def flush(self):
        self.console.flush();self.file.flush()

with (ROOT/'logs/latest-update-progress.log').open('w',encoding='utf-8',buffering=1) as log:
    with contextlib.redirect_stderr(Tee(sys.stderr,log)):
        result=refresh()
assert result['account_fingerprint']==old['account_fingerprint']
(ROOT/'logs/latest-update-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if (ROOT/'data/wechat-media-index.sqlite').exists():
    from build_media_index import main as refresh_media
    with contextlib.redirect_stdout(sys.stderr):
        media_result=refresh_media()
    print('Media index refreshed with current exclusion rules.',flush=True)
