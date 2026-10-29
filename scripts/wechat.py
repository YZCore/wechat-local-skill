"""Cross-harness entrypoint for the installed local WeChat backend."""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone, timedelta
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

TOOLS={
 'wechat_get_index_status':('wechat_index','status'),
 'wechat_list_sessions':('wechat_index','list_sessions'),
 'wechat_list_contacts':('wechat_index','list_contacts'),
 'wechat_read_session':('wechat_index','search_messages'),
 'wechat_search_messages':('wechat_index','search_messages'),
 'wechat_query_moments':('wechat_index','query_moments'),
 'wechat_export_session':('wechat_index','export_session'),
 'wechat_get_media_inventory':('wechat_index','media_inventory'),
 'wechat_read_bound_group':('read_group','read_bound_group'),
 'wechat_read_recent_moments':('read_moments','export_moments'),
 'wechat_get_media_status':('wechat_media','media_status'),
 'wechat_list_media_messages':('wechat_media','list_media'),
 'wechat_read_media':('wechat_media','read_media'),
 'wechat_search_media_content':('wechat_media','search_media_content'),
 'wechat_refresh_local_index':('wechat_index','refresh'),
 'wechat_refresh_media_index':('build_media_index','main'),
}


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f')


def load_backend(root):
    backend=root/'auto-read'
    sys.path.insert(0,str(backend))
    if not (backend/'read_group.py').exists():
        raise RuntimeError('后端尚未部署；运行同目录setup_backend.py查看部署计划。')
    return backend


def doctor(root):
    backend=root/'auto-read';python=backend/'.venv/Scripts/python.exe'
    state=dict(root=str(root),backend_ready=(backend/'read_group.py').is_file(),
               python_ready=python.is_file(),interpreter=sys.executable)
    if state['backend_ready'] and state['python_ready']:
        load_backend(root)
        wi=importlib.import_module('wechat_index')
        state['chat']=wi.status()
        state['media']=importlib.import_module('wechat_media').media_status()
        if not state['chat'].get('ready'):next_action='refresh'
        elif not state['media'].get('ready') or state['media'].get('needs_refresh'):next_action='call wechat_refresh_media_index'
        elif not state['media'].get('local_transcription_model_ready'):next_action='setup_backend.py --prepare-model'
        else:next_action='直接执行用户的查询或媒体任务'
    else:next_action='setup_backend.py --apply'
    state['next_action']=next_action
    return state


def params(tokens,file=None):
    value=json.loads(Path(file).read_text(encoding='utf-8-sig')) if file else {}
    if not isinstance(value,dict):raise ValueError('参数文件应为JSON对象。')
    i=0
    while i<len(tokens):
        key=tokens[i]
        if not key.startswith('--') or i+1>=len(tokens):raise ValueError('参数使用 --参数名 值。')
        raw=tokens[i+1]
        try:v=json.loads(raw)
        except json.JSONDecodeError:v=raw
        # Identities and numeric chat names are text, not numeric identifiers.
        if key[2:].replace('-','_') in ('identity','session','keyword','author','language'):v=raw
        value[key[2:].replace('-','_')]=v
        i+=2
    return value


def refresh(backend):
    wi=importlib.import_module('wechat_index')
    if wi.INDEX.exists():
        subprocess.run([sys.executable,'-X','utf8','-u',str(backend/'update_records.py')],
                       cwd=backend,stdout=sys.stderr,stderr=sys.stderr,check=True)
        return wi.status()
    with contextlib.redirect_stdout(sys.stderr):result=wi.refresh()
    # First deployment has an empty prior baseline for the quantity reports.
    backup=backend/'data/index-history'/('initial-empty-'+stamp())/'wechat-local-index.sqlite'
    backup.parent.mkdir(parents=True,exist_ok=True)
    with contextlib.closing(wi.connect()) as source,contextlib.closing(sqlite3.connect(backup)) as old:
        for r in source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"):
            old.execute(r[0])
        metadata={r['key']:json.loads(r['value']) for r in source.execute('SELECT * FROM metadata')}
        metadata['counts']={k:0 for k in metadata['counts']}
        old.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in metadata.items()])
        old.commit()
    (backend/'logs/latest-update-baseline.json').write_text(json.dumps(dict(backup_path=str(backup),
        previous_indexed_at=result['indexed_at'],previous_counts=metadata['counts']),ensure_ascii=False,indent=2),encoding='utf-8')
    (backend/'logs/latest-update-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def call(tool,arguments,backend):
    if tool not in TOOLS:raise ValueError('未知工具；用tools查看可用工具。')
    if tool=='wechat_refresh_local_index':return refresh(backend)
    if tool=='wechat_search_messages' and not str(arguments.get('keyword','')).strip():
        raise ValueError('搜索词不能为空。')
    if tool=='wechat_read_session':arguments={'keyword':'','limit':100,**arguments}
    if tool=='wechat_read_bound_group':
        wi=importlib.import_module('wechat_index');rg=importlib.import_module('read_group')
        if not rg.GROUP:raise ValueError('尚未设置绑定群，请直接按session读取会话。')
        with contextlib.closing(wi.connect()) as c:wi.resolve_session(c,rg.GROUP)
    module,name=TOOLS[tool]
    function=getattr(importlib.import_module(module),name)
    with contextlib.redirect_stdout(sys.stderr):return function(**arguments)


def report(which):
    module=importlib.import_module('session_counts' if which=='sessions' else 'sent_message_ranking')
    output=io.StringIO()
    with contextlib.redirect_stdout(output):module.main()
    return json.loads(output.getvalue())


def exclusion_plan(backend,names,public):
    wi=importlib.import_module('wechat_index')
    with contextlib.closing(wi.connect()) as c:
        meta={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
        targets={}
        for name in names:
            row=wi.resolve_session(c,name)
            targets[row['username']]=dict(c.execute('SELECT * FROM sessions WHERE username=?',(row['username'],)).fetchone())
        if public:
            for r in c.execute("SELECT * FROM sessions WHERE username GLOB 'gh_*'"):
                targets[r['username']]=dict(r)
    if not targets and not public:raise ValueError('请提供会话名或--public-accounts。')
    plan=dict(account_fingerprint=meta['account_fingerprint'],source_counts=meta['counts'],
        indexed_at=meta['indexed_at'],targets=list(targets.values()),exclude_public_accounts=public)
    path=backend/'logs'/('session-exclusion-plan-'+stamp()+'.json')
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(plan_path=str(path),selected_sessions=len(targets),
                selected_messages=sum(r['message_count'] for r in targets.values()),targets=list(targets.values()),
                exclude_public_accounts=public)


def exclusion_apply(backend,path):
    wi=importlib.import_module('wechat_index');sp=importlib.import_module('session_policy')
    plan=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if len({t['username'] for t in plan['targets']})!=len(plan['targets']):
        raise ValueError('计划含重复会话，请重新生成。')
    backup=backend/'data/index-history'/('before-skill-exclusion-'+stamp())/'wechat-local-index.sqlite'
    backup.parent.mkdir(parents=True,exist_ok=True)
    staging=wi.INDEX.with_name('wechat-local-index.excluding.sqlite')
    with contextlib.closing(wi.connect()) as c:
        meta={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
        if (meta['account_fingerprint'],meta['counts'],meta['indexed_at'])!=(plan['account_fingerprint'],plan['source_counts'],plan['indexed_at']):
            raise ValueError('索引已更新，请按当前数据重新生成排除计划。')
        for target in plan['targets']:
            r=c.execute('SELECT display,message_count FROM sessions WHERE username=?',(target['username'],)).fetchone()
            if r is None or (r['display'],r['message_count'])!=(target['display'],target['message_count']):
                raise ValueError('会话状态已变化，请重新生成计划。')
        for p in [backup,staging]:
            with contextlib.closing(sqlite3.connect(p)) as destination:c.backup(destination)
    policy=json.loads(sp.POLICY.read_text(encoding='utf-8')) if sp.POLICY.exists() else dict(version=1,accounts={},rules={})
    oldpolicy=sp.POLICY.read_bytes() if sp.POLICY.exists() else b''
    existing={r['session_id']:r for r in policy.setdefault('accounts',{}).get(meta['account_fingerprint'],[])}
    removed=0
    with contextlib.closing(sqlite3.connect(staging)) as c:
        c.execute('BEGIN IMMEDIATE')
        for target in plan['targets']:
            identity=target['username']
            removed+=c.execute('DELETE FROM messages WHERE session_id=?',(identity,)).rowcount
            c.execute('DELETE FROM sessions WHERE username=?',(identity,))
            c.execute('DELETE FROM contacts WHERE username=?',(identity,))
            existing[identity]=dict(session_id=identity,name=target['display'],excluded_at=wi.now(),reason='user_selected')
        rules=policy.setdefault('rules',{}).setdefault(meta['account_fingerprint'],{})
        if plan['exclude_public_accounts']:
            rules['exclude_public_accounts']=True
            c.execute("DELETE FROM contacts WHERE username GLOB 'gh_*'")
        policy['accounts'][meta['account_fingerprint']]=list(existing.values())
        old_counts=meta['counts']
        meta['counts']={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('contacts','sessions','messages','moments')}
        meta['filtered_at']=wi.now()
        meta['deduplication']['rows_excluded_after_indexing']=meta['deduplication'].get('rows_excluded_after_indexing',0)+removed
        times=c.execute('SELECT MIN(create_time),MAX(create_time) FROM messages').fetchone()
        meta['message_time_range']=[datetime.fromtimestamp(t,wi.TZ).isoformat(timespec='seconds') if t else None for t in times]
        meta['session_exclusions']=dict(configured=len(existing),exclude_public_accounts=rules.get('exclude_public_accounts',False),applied_at=meta['filtered_at'])
        for k,v in meta.items():c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(k,json.dumps(v,ensure_ascii=False)))
        if meta['counts']['messages']!=old_counts['messages']-removed:raise RuntimeError('排除数量不一致。')
        c.commit()
    if oldpolicy:(backup.parent/'excluded_sessions-before.json').write_bytes(oldpolicy)
    from read_group import atomic_text
    atomic_text(sp.POLICY,json.dumps(policy,ensure_ascii=False,indent=2))
    try:staging.replace(wi.INDEX)
    except Exception:
        if oldpolicy:sp.POLICY.write_bytes(oldpolicy)
        else:sp.POLICY.unlink(missing_ok=True)
        raise
    atomic_text(backend/'logs/latest-update-baseline.json',json.dumps(dict(backup_path=str(backup),previous_indexed_at=meta['indexed_at'],previous_counts=old_counts),ensure_ascii=False))
    atomic_text(backend/'logs/latest-update-result.json',json.dumps({'ready':True,'index_path':str(wi.INDEX),**meta},ensure_ascii=False))
    return dict(excluded_sessions=len(plan['targets']),removed_messages=removed,counts=meta['counts'],backup_path=str(backup))


def compare(baseline):
    wi=importlib.import_module('wechat_index')
    with contextlib.closing(wi.connect()) as c:
        c.execute('ATTACH DATABASE ? AS previous_index',(Path(baseline).resolve().as_uri()+'?mode=ro',))
        a=json.loads(c.execute("SELECT value FROM metadata WHERE key='account_fingerprint'").fetchone()[0])
        b=json.loads(c.execute("SELECT value FROM previous_index.metadata WHERE key='account_fingerprint'").fetchone()[0])
        if a!=b:raise ValueError('两份索引不是同一账号。')
        old=c.execute('SELECT COUNT(*) FROM previous_index.messages').fetchone()[0]
        new=c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        retained=c.execute('SELECT COUNT(*) FROM previous_index.messages o JOIN messages n ON n.identity=o.identity').fetchone()[0]
        changed=c.execute('''SELECT COUNT(*) FROM previous_index.messages o JOIN messages n ON n.identity=o.identity
            WHERE o.text IS NOT n.text OR o.kind IS NOT n.kind OR o.type_name IS NOT n.type_name
            OR o.create_time IS NOT n.create_time OR o.is_sender IS NOT n.is_sender''').fetchone()[0]
        dedup=json.loads(c.execute("SELECT value FROM metadata WHERE key='deduplication'").fetchone()[0])
    return dict(previous_messages=old,current_messages=new,retained_ids=retained,new_ids=new-retained,
                missing_previous_ids=old-retained,changed_payloads=changed,source_duplicates=dedup.get('duplicate_rows_skipped',0))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=os.environ.get('WECHAT_LOCAL_ROOT','D:/WeChatBridge'))
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor');commands.add_parser('tools');commands.add_parser('refresh')
    p=commands.add_parser('call');p.add_argument('tool',choices=TOOLS);p.add_argument('--params-file')
    p=commands.add_parser('report');p.add_argument('which',choices=['sessions','sent'])
    p=commands.add_parser('compare');p.add_argument('--baseline',required=True)
    p=commands.add_parser('exclude');subs=p.add_subparsers(dest='operation',required=True)
    p=subs.add_parser('plan');p.add_argument('--session',action='append',default=[]);p.add_argument('--public-accounts',action='store_true')
    p=subs.add_parser('apply');p.add_argument('--plan',required=True)
    args,rest=parser.parse_known_args();root=Path(args.root).resolve();backend=root/'auto-read'
    python=backend/'.venv/Scripts/python.exe'
    if python.exists() and Path(sys.executable).resolve()!=python.resolve():
        return subprocess.run([str(python),'-X','utf8',str(Path(__file__).resolve()),*sys.argv[1:]]).returncode
    if args.command=='doctor':result=doctor(root)
    else:
        load_backend(root)
        if args.command=='tools':
            import inspect
            result={k:str(inspect.signature(getattr(importlib.import_module(m),f))) for k,(m,f) in TOOLS.items()}
        elif args.command=='call':result=call(args.tool,params(rest,args.params_file),backend)
        elif args.command=='refresh':result=refresh(backend)
        elif args.command=='report':result=report(args.which)
        elif args.command=='compare':result=compare(args.baseline)
        elif args.operation=='plan':result=exclusion_plan(backend,args.session,args.public_accounts)
        else:result=exclusion_apply(backend,args.plan)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
