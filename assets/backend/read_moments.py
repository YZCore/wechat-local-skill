"""Export only the requested recent items from the local Moments feed cache."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET

from read_group import ROOT, DATA, VAULT, atomic_text


def export_moments(limit: int = 20, *, write_output: bool = True) -> dict:
    if not 1 <= limit <= 20:
        raise ValueError('当前采集范围为最近 1—20 条。')
    from wx4.paths import list_account_dirs
    from wx4.key import KeyExtractor
    from wx4.decrypt import decrypt_all

    accounts = list_account_dirs()
    if not accounts:
        raise RuntimeError('未找到本地微信账号数据，请先登录电脑版微信。')
    account = accounts[0]

    class MomentsExtractor(KeyExtractor):
        def collect(self):
            super().collect()
            self.db_files = [x for x in self.db_files
                             if Path(x['path']).name in ('sns.db', 'contact.db')]
            self.salt_index = {x['salt']: [x] for x in self.db_files}
            return self.db_files

    DATA.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(sys.stderr):
        extractor = MomentsExtractor(account['db_storage'])
        extractor.extract()
        keys = {k: v for k, v in extractor.result_payload().items() if not k.startswith('_')}
        if len(keys) != 2:
            raise RuntimeError('本次未能读取朋友圈和联系人数据库；旧导出已保留。')
        with tempfile.TemporaryDirectory(prefix='moments-', dir=DATA) as scratch:
            result = decrypt_all(keys, account['db_storage'], scratch)
            if result['failed'] or result['skipped']:
                raise RuntimeError('朋友圈数据库快照校验失败。')
            contacts = sqlite3.connect('file:' + (Path(scratch)/'contact/contact.db').as_posix() + '?mode=ro', uri=True)
            try:
                names = {u: (remark or nickname or u) for u, remark, nickname in
                         contacts.execute('SELECT username,remark,nick_name FROM contact')}
            finally:
                contacts.close()
            sns = sqlite3.connect('file:' + (Path(scratch)/'sns/sns.db').as_posix() + '?mode=ro', uri=True)
            try:
                # SnsTopItem_1 is incomplete and omits valid feed entries.
                # Sort the main-feed records by their own XML publication time.
                def publication_time(content):
                    return int(ET.fromstring(content).findtext('TimelineObject/createTime') or 0)
                sns.create_function('sns_created_at', 1, publication_time, deterministic=True)
                # Restrict to main feed entries; do not include profile-only visits,
                # notification/comment history, drafts, or ad tables.
                rows = sns.execute('''
                    SELECT t.tid,t.user_name,t.content,sns_created_at(t.content) AS post_time
                    FROM SnsTimeLine AS t
                    WHERE EXISTS (SELECT 1 FROM SnsMainTimeLineBreakFlag AS f WHERE f.tid=t.tid)
                    AND NOT EXISTS (SELECT 1 FROM SnsIgnoredDataItem AS i WHERE i.tid=t.tid)
                    ORDER BY post_time DESC,t.tid DESC
                    LIMIT ?
                ''', (limit,)).fetchall()
            finally:
                sns.close()
        extractor.keys.clear()
        keys.clear()

    posts = []
    for tid, username, content, stored_time in rows:
        root = ET.fromstring(content)
        timeline = root.find('TimelineObject')
        if timeline is None:
            raise RuntimeError('朋友圈记录格式变化，未覆盖原有导出。')
        xml_user = timeline.findtext('username')
        if xml_user and xml_user != username:
            raise RuntimeError('朋友圈作者校验失败。')
        created = int(timeline.findtext('createTime') or stored_time)
        if created != stored_time:
            raise RuntimeError('朋友圈发布时间校验失败。')
        media = timeline.findall('.//mediaList/media')
        comments = []
        for c in root.findall('.//comment_user_list/user_comment'):
            if c.findtext('b_deleted') not in (None, '', '0'):
                continue
            user = c.findtext('username') or ''
            comments.append({
                'author': names.get(user) or c.findtext('nickname') or user,
                'text': c.findtext('content') or '',
                'comment_id': c.findtext('comment_id') or '',
                'reply_to_id': c.findtext('ref_comment_id') or '',
                'create_time': int(c.findtext('create_time') or 0),
            })
        posts.append({
            'evidence_id': f'P{len(posts)+1:03d}',
            'post_id': str(tid & ((1 << 64) - 1)),
            'author': names.get(username) or timeline.findtext('nickname') or username,
            'create_time': created,
            'published_at': datetime.fromtimestamp(created).astimezone().isoformat(timespec='seconds'),
            'text': timeline.findtext('contentDesc') or '',
            'media_count': len(media),
            'comments': comments,
            'link_title': timeline.findtext('.//ContentObject/title') or '',
        })
    if len(posts) != limit:
        raise RuntimeError(f'本机当前仅有 {len(posts)} 条匹配记录。')
    assert len({p['post_id'] for p in posts}) == limit
    assert all(posts[i]['create_time'] >= posts[i+1]['create_time'] for i in range(len(posts)-1))
    captured = datetime.now().astimezone()
    archive = DATA / f'朋友圈最近{limit}条.json'
    note = VAULT / f'朋友圈最近{limit}条.md'
    payload = {
        'scope': '最近朋友圈信息流', 'count': len(posts),
        'exported_at': captured.isoformat(timespec='seconds'),
        'source': '本机微信朋友圈缓存，限定主信息流；按发布时间从新到旧',
        'newest_post': posts[0]['published_at'], 'oldest_post': posts[-1]['published_at'],
        'media_downloaded': False,
        'collection_method': 'local_database_only',
        'computer_use': False,
        'comments_count': sum(len(p['comments']) for p in posts),
        'comments_source': '本机已缓存的评论文字；未采集界面截图',
        'archive_path': str(archive), 'obsidian_path': str(note), 'posts': posts,
    }
    lines = [f'# 朋友圈 · 最近 {limit} 条', '',
             f"采集时间：{payload['exported_at']}", '',
             f"时间范围：{payload['oldest_post']} 至 {payload['newest_post']}。", '',
             '来源：本机微信主朋友圈信息流缓存；按发布时间从新到旧。', '',
             '直接读取本地数据库，包含作者、发布时间、正文、媒体数量与已缓存评论文字；未操作微信界面。图片及视频文件须单独核对本机缓存。', '']
    for post in posts:
        lines.extend([f"## {post['evidence_id']} · {post['author']}", '',
                      f"发布时间：{post['published_at']}", '',
                      '\n'.join('> ' + s for s in (post['text'] or '〔无文字正文〕').splitlines()), ''])
        if post['link_title']:
            lines.extend(['分享标题：' + post['link_title'], ''])
        if post['media_count']:
            lines.extend([f"媒体附件：{post['media_count']} 个（原文件未下载）", ''])
        lines.extend([f"已缓存评论：{len(post['comments'])} 条", ''])
        for c in post['comments']:
            lines.extend([f"**{c['author']}**：", '',
                          '\n'.join('> ' + s for s in c['text'].splitlines()), ''])
    if write_output:
        if note.exists():
            import shutil
            backup = ROOT.parent/'logs/文档历史'
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(note, backup / (note.stem + '-' + captured.strftime('%Y%m%d-%H%M%S-%f') + '.md'))
        atomic_text(archive, json.dumps(payload, ensure_ascii=False, indent=2))
        atomic_text(note, '\n'.join(lines))
        check = json.loads(archive.read_text(encoding='utf-8'))
        assert len(check['posts']) == check['count'] == limit
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    payload = export_moments(args.limit)
    print(json.dumps({k: v for k, v in payload.items() if k != 'posts'}, ensure_ascii=False, indent=2))
