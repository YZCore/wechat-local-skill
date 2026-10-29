"""Publish per-conversation counts from the current deduplicated local index."""
from collections import Counter
import contextlib
import csv
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import shutil
import sqlite3

from wechat_index import INDEX,ROOT
from session_policy import excluded_ids

TZ=timezone(timedelta(hours=8))
PROJECT=ROOT.parent


def date(value):
    return datetime.fromtimestamp(value,TZ).strftime('%Y-%m-%d %H:%M:%S') if value else ''


def kind(row):
    if row['is_group']:
        return '群聊'
    if row['username'].startswith('gh_'):
        return '公众号（按ID识别）'
    return '其他非群聊'


def csv_text(value):
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value


def md(value):
    return str(value).replace('|','\\|').replace('\r',' ').replace('\n',' ')


def main():
    with contextlib.closing(sqlite3.connect(INDEX.as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        meta={r['key']:json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
        excluded=excluded_ids(meta['account_fingerprint'])
        grouped=con.execute('''SELECT s.username,s.display,s.is_group,s.message_count AS cached_count,
            COUNT(m.identity) AS message_count,MIN(m.create_time) AS first_time,MAX(m.create_time) AS last_time
            FROM sessions s LEFT JOIN messages m ON m.session_id=s.username
            GROUP BY s.username ORDER BY message_count DESC,s.display,s.username''').fetchall()
        total=con.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        assert sum(r['message_count'] for r in grouped)==total==meta['counts']['messages']
        assert all(r['message_count']==r['cached_count'] for r in grouped)
        assert len(grouped)==meta['counts']['sessions']
        previous=json.loads((ROOT/'logs/latest-update-baseline.json').read_text(encoding='utf-8'))
        before_path=Path(previous['backup_path'])
        old_counts={}
        with contextlib.closing(sqlite3.connect(before_path.as_uri()+'?mode=ro',uri=True)) as old:
            old_meta={k:json.loads(v) for k,v in old.execute('SELECT key,value FROM metadata')}
            assert old_meta['account_fingerprint']==meta['account_fingerprint']
            old_counts={u:dict(name=name,count=n) for u,name,n in old.execute('SELECT username,display,message_count FROM sessions')}
            con.execute('ATTACH DATABASE ? AS previous_index',(before_path.as_uri()+'?mode=ro',))
            retained=con.execute('''SELECT COUNT(*) FROM previous_index.messages o JOIN messages n ON n.identity=o.identity''').fetchone()[0]
            missing=con.execute('''SELECT COUNT(*) FROM previous_index.messages o WHERE NOT EXISTS
                (SELECT 1 FROM messages n WHERE n.identity=o.identity)''').fetchone()[0]
            changed=con.execute('''SELECT COUNT(*) FROM previous_index.messages o JOIN messages n ON n.identity=o.identity
                WHERE n.create_time IS NOT o.create_time OR n.type_name IS NOT o.type_name
                OR n.kind IS NOT o.kind OR n.text IS NOT o.text''').fetchone()[0]
            expected_excluded=sum(old_counts.get(u,{}).get('count',0) for u in excluded)
    rows=[]
    types=Counter();type_messages=Counter()
    for rank,r in enumerate(grouped,1):
        r=dict(r);category=kind(r);old=old_counts.get(r['username'])
        types[category]+=1;type_messages[category]+=r['message_count']
        rows.append(dict(rank=rank,name=r['display'],category=category,count=r['message_count'],
            previous_count=old['count'] if old else 0,change=r['message_count']-(old['count'] if old else 0),
            first_record=date(r['first_time']),latest_record=date(r['last_time']),session_id=r['username'],
            previous_name=old['name'] if old else ''))
    effective_updated_at=meta.get('filtered_at') or meta['indexed_at']
    stamp=datetime.fromisoformat(effective_updated_at).strftime('%Y%m%d-%H%M%S')
    folder=ROOT/'exports';folder.mkdir(exist_ok=True)
    stem='各对象聊天记录数量-'+stamp
    csv_path=folder/(stem+'.csv');json_path=folder/(stem+'.json');md_path=PROJECT/'各对象聊天记录数量.md'
    summary=dict(indexed_at=meta['indexed_at'],updated_at=effective_updated_at,previous_indexed_at=old_meta['indexed_at'],
        previous_messages=old_meta['counts']['messages'],messages=total,
        net_change=total-old_meta['counts']['messages'],sessions=len(rows),
        sessions_with_messages=sum(r['count']>0 for r in rows),zero_message_sessions=sum(r['count']==0 for r in rows),
        counts_by_category={k:dict(sessions=types[k],messages=type_messages[k]) for k in types},
        previous_record_ids_retained=retained,previous_record_ids_not_found=missing,
        previous_records_with_changed_time_type_or_text=changed,
        excluded_sessions=len(excluded),intentionally_excluded_previous_records=expected_excluded,
        unexpected_previous_records_not_found=max(0,missing-expected_excluded),
        new_sessions=sum(r['session_id'] not in old_counts for r in rows),
        renamed_sessions=sum(bool(r['previous_name']) and r['name']!=r['previous_name'] for r in rows),
        deduplication=meta.get('deduplication'),message_time_range=meta['message_time_range'],
        csv_path=str(csv_path),markdown_path=str(md_path),json_path=str(json_path))
    with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['序号','对象名称','类型','消息条数','上次条数','本次净增','最早记录','最新记录','会话ID','上次名称'])
        for r in rows:
            writer.writerow([r['rank'],csv_text(r['name']),r['category'],r['count'],r['previous_count'],r['change'],
                             r['first_record'],r['latest_record'],csv_text(r['session_id']),csv_text(r['previous_name'])])
    payload=dict(summary=summary,objects=rows)
    lines=['# 各对象聊天记录数量','',f"清单更新时间：{summary['updated_at']}。数据库快照：{summary['indexed_at']}。",'',
        f"本次共 **{len(rows):,} 个会话、{total:,} 条去重后的消息**；比上次净变化 **{summary['net_change']:+,} 条**。",'',
        f"消息时间范围：{meta['message_time_range'][0]} 至 {meta['message_time_range'][1]}。",'',
        f"旧记录中找到 {retained:,} 条，未找到 {missing:,} 条；旧记录的时间、类型或正文变化 {changed:,} 条。",'',
        f"按用户要求排除 {len(excluded)} 个会话，涉及旧记录 {expected_excluded:,} 条；非预期缺失 {summary['unexpected_previous_records_not_found']:,} 条。",'',
        f"[完整CSV清单](auto-read/exports/{csv_path.name}) · [完整JSON清单](auto-read/exports/{json_path.name})",'',
        '统计按会话ID区分对象，重名对象不合并。条数来自当前索引的实际消息行，含文字、图片、语音、视频、文件和系统消息等类型；附件消息只计一条，不代表原文件已导出。公众号按gh_标识识别，其他非群聊包含好友、系统和工具会话。', '',
        '| 类型 | 会话数 | 消息条数 |','|---|---:|---:|']
    for k in types:
        lines.append(f'| {k} | {types[k]:,} | {type_messages[k]:,} |')
    lines += ['',f"无消息会话：{summary['zero_message_sessions']} 个，也保留在清单中。",'',
        '## 全部对象，按消息数量排序','',
        '| 排名 | 对象 | 类型 | 消息条数 | 比上次变化 | 最早记录 | 最新记录 |',
        '|---:|---|---|---:|---:|---|---|']
    for r in rows:
        lines.append(f"| {r['rank']} | {md(r['name'])} | {r['category']} | {r['count']:,} | {r['change']:+,} | {r['first_record']} | {r['latest_record']} |")
    lines += ['','数据仅反映当前账号在本机保存的记录。计数按[SQLite聚合函数](https://www.sqlite.org/lang_aggfunc.html)执行，并核对各对象条数之和等于索引总数。','']
    if md_path.exists():
        history=PROJECT/'logs/文档历史';history.mkdir(exist_ok=True)
        shutil.copy2(md_path,history/(md_path.stem+'-'+datetime.now(TZ).strftime('%Y%m%d-%H%M%S-%f')+'.md'))
    md_path.write_text('\n'.join(lines),encoding='utf-8')
    over=[r for r in rows if r['count']>100]
    threshold_md=PROJECT/'聊天记录大于100条.md'
    threshold_csv=folder/('聊天记录大于100条-'+stamp+'.csv')
    with threshold_csv.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['序号','对象名称','类型','消息条数','最早记录','最新记录','会话ID'])
        for i,r in enumerate(over,1):
            writer.writerow([i,csv_text(r['name']),r['category'],r['count'],r['first_record'],r['latest_record'],csv_text(r['session_id'])])
    threshold_lines=['# 聊天记录大于100条的全部对象','',f"清单更新时间：{effective_updated_at}。数据库快照：{meta['indexed_at']}。",'',
        f"已排除用户指定的{len(excluded)}个会话。当前共{len(rows)}个会话、{total:,}条消息；其中严格大于100条的对象共 **{len(over)} 个**。",'',
        f"[完整CSV清单](auto-read/exports/{threshold_csv.name})",'',
        '| 序号 | 对象 | 类型 | 消息条数 |','|---:|---|---|---:|']
    for i,r in enumerate(over,1):
        threshold_lines.append(f"| {i} | {md(r['name'])} | {r['category']} | {r['count']:,} |")
    threshold_lines += ['',f"以上{len(over)}个对象合计{sum(r['count'] for r in over):,}条消息。恰好100条及不足100条的对象未列入。",'',
        '删除范围为当前采集索引和有效统计清单，历史快照仍保留。后续刷新按账号对应的排除名单跳过指定会话。','']
    if threshold_md.exists():
        history=PROJECT/'logs/文档历史';history.mkdir(exist_ok=True)
        shutil.copy2(threshold_md,history/(threshold_md.stem+'-'+datetime.now(TZ).strftime('%Y%m%d-%H%M%S-%f')+'.md'))
    threshold_md.write_text('\n'.join(threshold_lines),encoding='utf-8')
    summary.update(over_100_objects=len(over),over_100_messages=sum(r['count'] for r in over),
        over_100_markdown_path=str(threshold_md),over_100_csv_path=str(threshold_csv))
    json_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not any(r['session_id'] in excluded for r in rows)
    with csv_path.open(encoding='utf-8-sig',newline='') as f:
        exported=list(csv.DictReader(f))
    assert len(exported)==len(rows) and sum(int(r['消息条数']) for r in exported)==total
    with threshold_csv.open(encoding='utf-8-sig',newline='') as f:
        threshold_check=list(csv.DictReader(f))
    assert len(threshold_check)==len(over) and all(int(r['消息条数'])>100 for r in threshold_check)
    (ROOT/'logs/latest-session-counts-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(summary=summary,top_objects=rows[:20]),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
