"""Rank conversations by messages sent by the current account."""
import contextlib
import csv
from datetime import datetime
import json
import shutil
import sqlite3

from wechat_index import INDEX, ROOT
from session_policy import excluded_ids, exclude_public_accounts, is_public_account


def main():
    with contextlib.closing(sqlite3.connect(INDEX.as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        meta = {r['key']: json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
        excluded = excluded_ids(meta['account_fingerprint'])
        sessions = list(con.execute('SELECT username FROM sessions'))
        assert all(r['username'] not in excluded for r in sessions)
        if exclude_public_accounts(meta['account_fingerprint']):
            assert all(not is_public_account(r['username']) for r in sessions)
        assert not con.execute('SELECT 1 FROM messages WHERE is_sender IS NULL OR is_sender NOT IN (0,1) LIMIT 1').fetchone()
        total_sent = con.execute('SELECT COUNT(*) FROM messages WHERE is_sender=1').fetchone()[0]
        rows = [dict(r) for r in con.execute('''
            SELECT s.username AS session_id,s.display AS name,s.is_group,
                   COUNT(*) AS sent_count,s.message_count AS total_count
            FROM messages m JOIN sessions s ON s.username=m.session_id
            WHERE m.is_sender=1
            GROUP BY s.username
            ORDER BY sent_count DESC,s.display,s.username''')]
        assert sum(r['sent_count'] for r in rows) == total_sent
        assert all(0 < r['sent_count'] <= r['total_count'] for r in rows)
        assert [r['sent_count'] for r in rows] == sorted((r['sent_count'] for r in rows), reverse=True)
    top = rows[:20]
    for i, r in enumerate(top, 1):
        r.update(rank=i, category='群聊' if r['is_group'] else '非群聊')
    stamp = datetime.fromisoformat(meta['indexed_at']).strftime('%Y%m%d-%H%M%S')
    csv_path = ROOT / 'exports' / ('我的发言次数前20-' + stamp + '.csv')
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['排名', '对象', '类型', '我发送的消息数', '会话总消息数', '会话ID'])
        for r in top:
            safe = lambda v: "'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v
            writer.writerow([r['rank'], safe(r['name']), r['category'], r['sent_count'], r['total_count'], safe(r['session_id'])])
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        check = list(csv.DictReader(f))
    assert [int(r['我发送的消息数']) for r in check] == [r['sent_count'] for r in top]
    path = ROOT.parent / '我的发言次数前20.md'
    lines = ['# 我的发言次数前20', '', f"索引更新：{meta['indexed_at']}。", '',
             f"当前 {meta['counts']['sessions']:,} 个会话、{meta['counts']['messages']:,} 条消息中，由我发送的共 **{total_sent:,} 条**，分布在 **{len(rows)} 个会话**。", '',
             '按会话统计全部本地已保存历史，以发送者账号等于当前账号（is_sender=1）为准。每条消息计一次，包含文字、图片、语音、视频、文件等。已应用此前的会话及公众号排除规则；重名对象按会话ID分别统计。', '',
             '| 排名 | 对象 | 类型 | 我发送的消息数 |', '|---:|---|---|---:|']
    for r in top:
        name = r['name'].replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')
        lines.append(f"| {r['rank']} | {name} | {r['category']} | {r['sent_count']:,} |")
    lines += ['', f'[下载CSV](auto-read/exports/{csv_path.name})', '',
              '计数使用[SQLite聚合函数](https://www.sqlite.org/lang_aggfunc.html)，并核对各会话的本人发送数之和等于全库本人发送数。', '']
    if path.exists():
        history = ROOT.parent / 'logs/文档历史'
        history.mkdir(exist_ok=True)
        shutil.copy2(path, history / (path.stem + '-' + stamp + '.md'))
    path.write_text('\n'.join(lines), encoding='utf-8')
    payload = dict(indexed_at=meta['indexed_at'], counts=meta['counts'], total_sent=total_sent,
                   sessions_with_sent_messages=len(rows), top20=top,
                   markdown_path=str(path), csv_path=str(csv_path))
    (ROOT / 'logs/latest-sent-message-ranking.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
