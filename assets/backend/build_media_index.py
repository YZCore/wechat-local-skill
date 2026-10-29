"""Build message-to-media links from temporary snapshots; exclude removed sessions."""
import contextlib
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET

from media_sources import snapshot
from wechat_index import ROOT, DATA, INDEX, connect, now
from session_policy import excluded_ids, exclude_public_accounts, is_public_account

MEDIA_INDEX = DATA / 'wechat-media-index.sqlite'


def hashes(*values):
    result = []
    for value in values:
        if isinstance(value, bytes):
            value = value.decode('utf-8', 'ignore')
        result.extend(x.lower() for x in re.findall(r'(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])', value or ''))
    return list(dict.fromkeys(result))


def main():
    with contextlib.closing(connect()) as active:
        meta = {r['key']: json.loads(r['value']) for r in active.execute('SELECT * FROM metadata')}
        targets = {r['identity']:dict(r) for r in active.execute("SELECT * FROM messages WHERE kind IN ('image','voice','video','file')")}
    sessions = sorted({r['session_id'] for r in targets.values()})
    excluded = excluded_ids(meta['account_fingerprint'])
    assert not set(sessions) & excluded
    if exclude_public_accounts(meta['account_fingerprint']):
        assert not any(is_public_account(s) for s in sessions)
    staging = DATA / 'wechat-media-index.building.sqlite'
    if staging.exists():
        staging.unlink()
    with snapshot() as (account, data), contextlib.closing(sqlite3.connect(staging, uri=True)) as out:
        out.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE assets(identity TEXT PRIMARY KEY,kind TEXT,details TEXT,voice BLOB);
            CREATE TABLE results(identity TEXT PRIMARY KEY,result TEXT NOT NULL);''')
        base = Path(account['path'])
        attach = defaultdict(list)
        video = defaultdict(list)
        files = defaultdict(list)
        for root, group, pattern in [(base/'msg/attach',attach,'*.dat'),(base/'msg/video',video,'*.mp4'),(base/'msg/file',files,'*')]:
            if root.exists():
                for p in root.rglob(pattern):
                    if p.is_file():
                        group[p.name.lower()].append(p)
        print('Media: local cache catalogued.', file=sys.stderr, flush=True)
        resource = data._open('message/message_resource.db')
        probe = {p.name:[dict(r) for r in c.execute('PRAGMA table_info("%s")' % t)]
                 for p,c,t in [(Path('resource-info'),resource,'MessageResourceInfo'),
                               (Path('resource-detail'),resource,'MessageResourceDetail')] if c}
        (ROOT/'logs/media-resource-schema.json').write_text(json.dumps(probe,ensure_ascii=False,indent=2),encoding='utf-8')
        found = set()
        stats = Counter()
        for i,session in enumerate(sessions,1):
            for m in data.messages(session):
                identity = session + ':' + ('s:'+str(m['server_id']) if m['server_id'] else f"l:{m['shard']}:{m['local_id']}")
                target = targets.get(identity)
                if target is None or identity in found:
                    continue
                found.add(identity)
                kind = target['kind']
                content = m.get('content') or ''
                packed = bytes.fromhex(m.get('packed_hex') or '')
                root = None
                start = content.find('<')
                if start >= 0:
                    try:
                        root = ET.fromstring(content[start:])
                    except ET.ParseError:
                        pass
                names = []
                expected_size = 0
                expected_md5 = ''
                duration = 0
                if root is not None:
                    for tag in ['title','filename','fileext']:
                        for node in root.findall('.//'+tag):
                            if node.text:
                                names.append(node.text.strip())
                    for node in root.iter():
                        if node.tag in ('totallen','length','filesize') and (node.text or '').isdigit():
                            expected_size = max(expected_size, int(node.text))
                        if node.tag == 'md5' and re.fullmatch('[0-9a-fA-F]{32}',node.text or ''):
                            expected_md5 = node.text.lower()
                        if kind == 'voice' and (node.get('voicelength') or '').isdigit():
                            duration = int(node.get('voicelength')) / 1000
                resource_blob = b''
                if kind == 'file' and resource and m['server_id']:
                    rr = resource.execute('''SELECT d.packed_info FROM MessageResourceDetail d
                        JOIN MessageResourceInfo i ON d.message_id=i.message_id
                        WHERE i.message_svr_id=?''',(m['server_id'],)).fetchall()
                    resource_blob = b'\n'.join(bytes(r[0]) if not isinstance(r[0],str) else r[0].encode() for r in rr if r[0])
                md5s = hashes(content,packed,resource_blob)
                detail = dict(status='missing',reason='本机未找到关联媒体',candidates=[],duration_seconds=duration)
                blob = None
                if kind == 'voice':
                    blob = data.voice_blob(session,m['server_id']) if m['server_id'] else None
                    if blob and (blob.startswith(b'#!SILK_V3') or blob.startswith(b'\x02#!SILK_V3')):
                        detail.update(status='available',reason='会话ID及消息server_id精确匹配',bytes=len(blob))
                    else:
                        blob = None
                        detail['reason'] = '语音数据库中没有这条消息的音频'
                elif kind == 'image':
                    chat_hash = hashlib.md5(session.encode()).hexdigest()
                    for h in md5s:
                        for suffix,tier in [('_h.dat','original'),('.dat','mid'),('_t.dat','thumb')]:
                            for p in attach.get(h+suffix,[]):
                                if p.relative_to(base/'msg/attach').parts[0] == chat_hash:
                                    detail['candidates'].append(dict(path=str(p),tier=tier,match='消息标识与会话目录一致'))
                elif kind == 'video':
                    for h in md5s:
                        for p in video.get(h+'.mp4',[]):
                            detail['candidates'].append(dict(path=str(p),tier='video',match='消息媒体标识与缓存文件名一致'))
                elif kind == 'file':
                    if resource_blob:
                        names.extend(p.name for group in files.values() for p in group if p.name.encode() in resource_blob)
                    candidates = {p for name in names for p in files.get(Path(name).name.lower(),[])}
                    for p in sorted(candidates):
                        if expected_size and p.stat().st_size != expected_size:
                            continue
                        matched = False
                        if expected_md5:
                            with p.open('rb') as f:
                                digest = hashlib.file_digest(f,'md5').hexdigest()
                            matched = digest == expected_md5
                            if not matched:
                                continue
                        elif expected_size and len(candidates) == 1:
                            matched = True
                        detail['candidates'].append(dict(path=str(p),tier='file',
                            match='文件MD5一致' if expected_md5 else '文件名和大小唯一匹配' if matched else '仅文件名匹配，待核对',verified=matched))
                    detail.update(filename=names[0] if names else '',expected_size=expected_size)
                if detail['candidates']:
                    ready = [c for c in detail['candidates'] if c.get('verified',True)]
                    detail.update(status='available' if ready else 'candidate',reason='已关联本地缓存' if ready else '仅候选文件，未验证关联')
                out.execute('INSERT INTO assets VALUES(?,?,?,?)',(identity,kind,json.dumps(detail,ensure_ascii=False),blob))
                stats[kind+':'+detail['status']] += 1
            if i % 50 == 0:
                print(f'Media: linked {i}/{len(sessions)} conversations.',file=sys.stderr,flush=True)
        for identity in set(targets)-found:
            target = targets[identity]
            detail = dict(status='missing',reason='新快照中未找到对应消息；保留文字索引',candidates=[])
            out.execute('INSERT INTO assets VALUES(?,?,?,NULL)',(identity,target['kind'],json.dumps(detail,ensure_ascii=False)))
            stats[target['kind']+':missing'] += 1
        info = dict(indexed_at=now(),message_indexed_at=meta['indexed_at'],account_fingerprint=meta['account_fingerprint'],
                    total=len(targets),counts=dict(stats),computer_use=False,source='本机数据库及媒体缓存；无界面操作')
        out.execute('INSERT INTO metadata VALUES(?,?)',('status',json.dumps(info,ensure_ascii=False)))
        out.commit()
        assert out.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == len(targets)
        assert out.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        # Preserve processing results only for still-eligible message identities.
        if MEDIA_INDEX.exists():
            out.execute('ATTACH DATABASE ? AS old',(MEDIA_INDEX.as_uri()+'?mode=ro',))
            out.execute('INSERT INTO results SELECT r.* FROM old.results r JOIN assets a ON a.identity=r.identity')
            out.commit()
    staging.replace(MEDIA_INDEX)
    (ROOT/'logs/latest-media-index.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False,indent=2))
    return info


if __name__ == '__main__':
    main()
