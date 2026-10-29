"""Local account index and bounded queries. No desktop/UI/network operations."""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
from mcp.server.mcpserver.exceptions import ToolError

from read_group import DATA, ROOT, atomic_text

INDEX = DATA / 'wechat-local-index.sqlite'
TZ = timezone(timedelta(hours=8))


def now():
    return datetime.now(TZ).isoformat(timespec='seconds')


def connect():
    if not INDEX.is_file():
        raise ToolError('尚未建立本地索引，请先调用 wechat_refresh_local_index。')
    con = sqlite3.connect(INDEX.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def page(limit, offset):
    if not 1 <= limit <= 500 or not 0 <= offset <= 10_000_000:
        raise ToolError('limit 必须为1—500，offset必须为0—10000000。')


def status():
    if not INDEX.exists():
        return {'ready': False, 'computer_use': False}
    with contextlib.closing(connect()) as con:
        meta = {r['key']: json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
    return {'ready': True, 'index_path': str(INDEX), **meta}


def insert_message(out,session,m):
    identity = session + ':' + ('s:'+str(m['server_id']) if m['server_id'] else f"l:{m['shard']}:{m['local_id']}")
    values=(identity,session,m['local_id'],str(m['server_id']),m['shard'],m['create_time'],m['time_str'],
            m['sender'],int(m['is_sender']),m['type_name'],m['kind'],m['text'])
    inserted=out.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',values).rowcount==1
    variant=False
    if not inserted:
        previous=out.execute('SELECT create_time,sender,is_sender,type_name,kind,text FROM messages WHERE identity=?',(identity,)).fetchone()
        variant=tuple(previous)!=(m['create_time'],m['sender'],int(m['is_sender']),m['type_name'],m['kind'],m['text'])
    return inserted,variant


def refresh():
    from wx4.paths import list_account_dirs
    from wx4.key import KeyExtractor
    from wx4.decrypt import decrypt_all
    from wx4.reader import Wx4Data

    accounts = list_account_dirs()
    if not accounts:
        raise RuntimeError('未找到本地微信账号数据，请登录电脑版微信。')
    account = accounts[0]
    from session_policy import excluded_ids,exclude_public_accounts,is_public_account
    account_fingerprint=hashlib.sha256(account['wxid'].encode()).hexdigest()[:16]
    excluded=excluded_ids(account_fingerprint)
    exclude_public=exclude_public_accounts(account_fingerprint)

    class ScopedExtractor(KeyExtractor):
        def collect(self):
            super().collect()
            self.db_files = [x for x in self.db_files if
                Path(x['path']).name in ('contact.db', 'session.db', 'sns.db') or
                re.fullmatch(r'(?:biz_)?message_\d+\.db', Path(x['path']).name)]
            self.salt_index = {}
            for item in self.db_files:
                self.salt_index.setdefault(item['salt'], []).append(item)
            return self.db_files

    DATA.mkdir(parents=True, exist_ok=True)
    staging = DATA / 'wechat-local-index.building.sqlite'
    if staging.exists():
        staging.unlink()
    ex = None
    keys = {}
    started = now()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            ex = ScopedExtractor(account['db_storage'])
            ex.extract()
            keys = {k:v for k,v in ex.result_payload().items() if not k.startswith('_')}
            if not keys or len(keys) != len(ex.db_files):
                raise RuntimeError('未取得全部所需数据库的读取条件，保留旧索引。')
            print(f'Index: snapshotting {len(keys)} databases.', file=sys.stderr, flush=True)
            with tempfile.TemporaryDirectory(prefix='wechat-index-', dir=DATA) as scratch:
                result = decrypt_all(keys, account['db_storage'], scratch)
                if result['failed'] or result['skipped']:
                    raise RuntimeError('数据库快照校验失败，保留旧索引。')
                data = Wx4Data(scratch, wxid=account['wxid'], account_dir=account['path'])
                out = sqlite3.connect(staging)
                try:
                    out.executescript('''
                        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                        CREATE TABLE contacts(username TEXT PRIMARY KEY,display TEXT,nickname TEXT,remark TEXT,alias TEXT,is_group INTEGER,source TEXT);
                        CREATE TABLE sessions(username TEXT PRIMARY KEY,display TEXT,is_group INTEGER,last_time INTEGER,message_count INTEGER DEFAULT 0);
                        CREATE TABLE messages(identity TEXT PRIMARY KEY,session_id TEXT,local_id INTEGER,server_id TEXT,shard INTEGER,create_time INTEGER,time_str TEXT,sender TEXT,is_sender INTEGER,type_name TEXT,kind TEXT,text TEXT);
                        CREATE TABLE moments(post_id TEXT PRIMARY KEY,author TEXT,create_time INTEGER,published_at TEXT,text TEXT,link_title TEXT,media_count INTEGER,comments_json TEXT,media_json TEXT,is_main_feed INTEGER);
                    ''')
                    if exclude_public:
                        excluded.update(u for u in data.contacts if is_public_account(u))
                    contacts = {u:c for u,c in data.contacts.items() if not u.startswith('#id:') and u not in excluded}
                    out.executemany('INSERT INTO contacts VALUES(?,?,?,?,?,?,?)', [
                        (u,data.name_of(u),c.get('nick_name') or '',c.get('remark') or '',c.get('alias') or '',int(u.endswith('@chatroom')),c.get('_table',''))
                        for u,c in contacts.items()])
                    sessions = {s['username']: s for s in data.sessions()}
                    if exclude_public:
                        excluded.update(u for u in sessions if is_public_account(u))
                    tables = set().union(*(data.tables_of(c) for c in data.msg_dbs))
                    for u in contacts:
                        if data.msg_table_for(u) in tables and u not in sessions:
                            sessions[u] = dict(username=u, display=data.session_display(u), is_group=u.endswith('@chatroom'),last_time=0)
                    known_tables = {data.msg_table_for(u) for u in sessions} | {data.msg_table_for(u) for u in excluded}
                    excluded_present=len(set(sessions)&excluded)
                    sessions={u:s for u,s in sessions.items() if u not in excluded}
                    out.executemany('INSERT INTO sessions(username,display,is_group,last_time) VALUES(?,?,?,?)',[
                        (u,s['display'],int(s['is_group']),s['last_time']) for u,s in sessions.items()])
                    orphan_tables = len({t for t in tables if t.startswith('Msg_')} - known_tables)
                    source_rows=duplicate_rows=variant_rows=0
                    for i,u in enumerate(sessions,1):
                        messages = data.messages(u)
                        for m in messages:
                            source_rows+=1
                            inserted,variant=insert_message(out,u,m)
                            duplicate_rows+=int(not inserted)
                            variant_rows+=int(variant)
                        if i % 100 == 0:
                            print(f'Index: processed {i}/{len(sessions)} sessions.',file=sys.stderr,flush=True)
                    out.executescript('''
                        CREATE INDEX messages_session_time ON messages(session_id,create_time DESC,shard DESC,local_id DESC);
                        CREATE INDEX messages_time ON messages(create_time DESC);
                        UPDATE sessions SET message_count=(SELECT COUNT(*) FROM messages WHERE session_id=sessions.username);
                        UPDATE sessions SET last_time=MAX(last_time,COALESCE((SELECT MAX(create_time) FROM messages WHERE session_id=sessions.username),0));
                    ''')
                    sns_path = Path(scratch)/'sns/sns.db'
                    if sns_path.exists():
                        sns = sqlite3.connect(sns_path.as_uri()+'?mode=ro',uri=True)
                        try:
                            rows = sns.execute('''SELECT t.tid,t.user_name,t.content,
                                EXISTS(SELECT 1 FROM SnsMainTimeLineBreakFlag f WHERE f.tid=t.tid)
                                FROM SnsTimeLine t WHERE NOT EXISTS(SELECT 1 FROM SnsIgnoredDataItem i WHERE i.tid=t.tid)''')
                            for tid,user,content,main_feed in rows:
                                root = ET.fromstring(content)
                                timeline = root.find('TimelineObject')
                                if timeline is None:
                                    raise RuntimeError('朋友圈结构变化，保留旧索引。')
                                created = int(timeline.findtext('createTime') or 0)
                                comments = []
                                for c in root.findall('.//comment_user_list/user_comment'):
                                    if c.findtext('b_deleted') not in (None,'','0'):
                                        continue
                                    username = c.findtext('username') or ''
                                    comments.append(dict(author=data.name_of(username) if username in contacts else c.findtext('nickname') or username,
                                        text=c.findtext('content') or '',comment_id=c.findtext('comment_id') or '',reply_to_id=c.findtext('ref_comment_id') or ''))
                                media = []
                                for n,m in enumerate(timeline.findall('.//mediaList/media'),1):
                                    url = m.find('url'); size=m.find('size')
                                    kind = 'video' if m.findtext('type')=='6' or (url is not None and url.get('videomd5')) else 'image'
                                    media.append(dict(index=n,kind=kind,md5=(url.get('videomd5') or url.get('md5') or '') if url is not None else '',
                                        width=int(float(size.get('width','0'))) if size is not None else 0,
                                        height=int(float(size.get('height','0'))) if size is not None else 0,
                                        declared_size=int(size.get('totalSize','0')) if size is not None else 0))
                                out.execute('INSERT INTO moments VALUES(?,?,?,?,?,?,?,?,?,?)',
                                    (str(tid & (2**64-1)),data.name_of(user),created,datetime.fromtimestamp(created,TZ).isoformat(timespec='seconds'),
                                     timeline.findtext('contentDesc') or '',timeline.findtext('.//ContentObject/title') or '',len(media),
                                     json.dumps(comments,ensure_ascii=False),json.dumps(media),int(main_feed)))
                        finally:
                            sns.close()
                    out.execute('CREATE INDEX moments_time ON moments(create_time DESC)')
                    counts = {t:out.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('contacts','sessions','messages','moments')}
                    ambiguous=out.execute('''SELECT COUNT(*),COALESCE(SUM(n-1),0) FROM (
                        SELECT COUNT(*) AS n FROM messages WHERE server_id IN ('0','None','')
                        GROUP BY session_id,create_time,sender,is_sender,type_name,kind,text HAVING COUNT(*)>1)''').fetchone()
                    if source_rows-duplicate_rows!=counts['messages']:
                        raise RuntimeError('消息去重计数校验失败，保留旧索引。')
                    times = out.execute('SELECT MIN(create_time),MAX(create_time) FROM messages').fetchone()
                    meta = dict(started_at=started,indexed_at=now(),counts=counts,
                        source='本机当前账号数据库快照；非服务端全量',computer_use=False,
                        message_time_range=[datetime.fromtimestamp(t,TZ).isoformat(timespec='seconds') if t else None for t in times],
                        database_count=len(keys),unresolved_message_tables=orphan_tables,
                        main_feed_moments=out.execute('SELECT COUNT(*) FROM moments WHERE is_main_feed=1').fetchone()[0],
                        account_fingerprint=account_fingerprint,
                        session_exclusions=dict(configured=len(excluded),skipped_sessions=excluded_present,exclude_public_accounts=exclude_public),
                        deduplication=dict(source_rows=source_rows,duplicate_rows_skipped=duplicate_rows,
                            same_identity_different_fields=variant_rows,
                            ambiguous_no_server_id_groups=ambiguous[0],ambiguous_no_server_id_extra_rows=ambiguous[1],
                            ambiguous_rows_preserved=True,policy='session+server_id; otherwise preserve shard+local_id'),
                        media_files_exported=False,comments_scope='本机已缓存的评论；不代表全部评论')
                    out.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in meta.items()])
                    out.commit()
                    if out.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('索引完整性校验失败，保留旧索引。')
                finally:
                    out.close()
                    data.close()
        staging.replace(INDEX)
        return status()
    finally:
        keys.clear()
        if ex is not None:
            ex.keys.clear()
        if staging.exists():
            staging.unlink()


def resolve_session(con, session):
    rows = con.execute('SELECT username,display FROM sessions WHERE username=? OR display=?',(session,session)).fetchall()
    if len(rows)!=1:
        raise ToolError('未找到唯一会话，请先用 wechat_list_sessions 查询，并传入唯一的 username。')
    return rows[0]


def list_sessions(keyword='', groups_only=False, limit=50, offset=0):
    page(limit,offset)
    where='WHERE (instr(lower(display),lower(?))>0 OR instr(lower(username),lower(?))>0)'
    args=[keyword,keyword]
    if groups_only:
        where+=' AND is_group=1'
    with contextlib.closing(connect()) as con:
        total=con.execute('SELECT COUNT(*) FROM sessions '+where,args).fetchone()[0]
        rows=con.execute('SELECT * FROM sessions '+where+' ORDER BY last_time DESC,username LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
    return dict(total=total,offset=offset,returned_count=len(rows),sessions=[dict(r) for r in rows])


def list_contacts(keyword='',limit=50,offset=0):
    page(limit,offset)
    where='WHERE instr(lower(display||nickname||remark||alias||username),lower(?))>0'
    with contextlib.closing(connect()) as con:
        total=con.execute('SELECT COUNT(*) FROM contacts '+where,(keyword,)).fetchone()[0]
        rows=con.execute('SELECT * FROM contacts '+where+' ORDER BY display,username LIMIT ? OFFSET ?',(keyword,limit,offset)).fetchall()
    return dict(total=total,offset=offset,returned_count=len(rows),contacts=[dict(r) for r in rows])


def search_messages(keyword='',session='',start_time=0,end_time=0,limit=50,offset=0):
    page(limit,offset)
    if not keyword and not session:
        raise ToolError('请提供关键词或指定会话。')
    if start_time<0 or end_time<0 or (end_time and start_time>end_time):
        raise ToolError('时间范围无效，使用Unix秒时间戳。')
    where=['instr(lower(m.text),lower(?))>0']; args=[keyword]
    with contextlib.closing(connect()) as con:
        if session:
            resolved=resolve_session(con,session)
            where.append('m.session_id=?');args.append(resolved['username'])
        if start_time:
            where.append('m.create_time>=?');args.append(start_time)
        if end_time:
            where.append('m.create_time<=?');args.append(end_time)
        clause=' WHERE '+' AND '.join(where)
        total=con.execute('SELECT COUNT(*) FROM messages m'+clause,args).fetchone()[0]
        rows=con.execute('SELECT m.*,s.display AS session_display FROM messages m JOIN sessions s ON s.username=m.session_id'+clause+
                         ' ORDER BY m.create_time DESC,m.shard DESC,m.local_id DESC,m.identity LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
    return dict(total=total,offset=offset,returned_count=len(rows),order='newest_first',messages=[dict(r) for r in rows])


def query_moments(keyword='',author='',main_feed_only=True,limit=20,offset=0):
    page(limit,offset)
    where=' WHERE instr(lower(text||link_title),lower(?))>0 AND instr(lower(author),lower(?))>0'
    if main_feed_only:
        where+=' AND is_main_feed=1'
    with contextlib.closing(connect()) as con:
        total=con.execute('SELECT COUNT(*) FROM moments'+where,(keyword,author)).fetchone()[0]
        rows=con.execute('SELECT * FROM moments'+where+' ORDER BY create_time DESC,post_id DESC LIMIT ? OFFSET ?',(keyword,author,limit,offset)).fetchall()
    posts=[]
    for r in rows:
        p=dict(r)
        p['comments']=json.loads(p.pop('comments_json'))
        p['media']=json.loads(p.pop('media_json'))
        posts.append(p)
    return dict(total=total,offset=offset,returned_count=len(posts),posts=posts,source='本机朋友圈缓存',media_files_included=False)


def export_session(session):
    with contextlib.closing(connect()) as con:
        s=dict(resolve_session(con,session))
        rows=con.execute('SELECT * FROM messages WHERE session_id=? ORDER BY create_time,shard,local_id',(s['username'],)).fetchall()
    folder=ROOT/'exports'
    stem=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',s['display']).strip(' .')[:70] or '会话'
    stem+='-'+hashlib.sha256(s['username'].encode()).hexdigest()[:8]
    archive=folder/(stem+'.json'); note=folder/(stem+'.md')
    if archive.exists():
        raise ToolError('该会话已导出。为保留已有文件，请先检查 exports 中同名结果。')
    payload=dict(session=s,count=len(rows),exported_at=now(),source='本地索引；媒体文件未包含',messages=[dict(r) for r in rows])
    lines=['# '+s['display'],'',f"导出时间：{payload['exported_at']}；共{len(rows)}条。本机缓存记录，媒体仅保留类型。",'']
    for m in rows:
        lines += [f"## {m['time_str']} · {m['sender']}",'','\n'.join('> '+x for x in m['text'].splitlines()),'']
    atomic_text(archive,json.dumps(payload,ensure_ascii=False,indent=2))
    atomic_text(note,'\n'.join(lines))
    return dict(count=len(rows),archive_path=str(archive),markdown_path=str(note),media_files_included=False)


def media_inventory():
    from wx4.paths import list_account_dirs
    accounts=list_account_dirs()
    if not accounts:
        raise RuntimeError('未找到微信数据目录。')
    root=Path(accounts[0]['path'])
    groups={}
    for pattern,label in [('cache/*/Sns/Img/*/*','朋友圈图片缓存'),('cache/*/Sns/Video/*/*','朋友圈视频缓存'),
                          ('msg/attach/**/*','聊天附件缓存'),('msg/video/**/*','聊天视频缓存'),('msg/file/**/*','聊天文件缓存')]:
        count=size=0
        for p in root.glob(pattern):
            if p.is_file():
                try:
                    size+=p.stat().st_size;count+=1
                except OSError:
                    continue
        groups[label]=dict(files=count,bytes=size)
    return dict(source='本机文件元数据；未解密或下载媒体',groups=groups,
                note='文件数不等于动态或消息数，可能包含缩略图、封面、分片和重复项。')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    print(json.dumps(refresh() if args.refresh else status(),ensure_ascii=False,indent=2))
