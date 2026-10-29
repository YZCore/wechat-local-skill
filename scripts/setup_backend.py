"""Inspect, deploy, and configure the portable Windows WeChat backend."""
from __future__ import annotations
import argparse
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

SKILL=Path(__file__).resolve().parents[1]
SOURCES=[
 ('WeChatMsg-4x','chenanhan230-del/WeChatMsg-4x','ea4d3f295f767996883958cf88aa5f793cac4c75',
  ['wx4/__init__.py','wx4/common.py','wx4/paths.py','wx4/key.py','wx4/decrypt.py','wx4/reader.py','wx4/media.py']),
 ('wechatauto-replica','fanyuantaier/wechatauto-replica','5d29e297aee095df65785fc8386af77506554698',
  ['wechatauto/db.py','wechatauto/media.py']),
]


def runtime_python(explicit=None):
    if explicit:return Path(explicit).resolve()
    if sys.version_info[:2]==(3,11):return Path(sys.executable)
    local=Path.home()/'AppData/Local/Programs/Python/Python311/python.exe'
    if local.exists():return local
    launcher=shutil.which('py')
    if launcher:
        r=subprocess.run([launcher,'-3.11','-c','import sys;print(sys.executable)'],capture_output=True,text=True)
        if r.returncode==0:return Path(r.stdout.strip())
    return Path(sys.executable)


def plan(root,python):
    backend=root/'auto-read'
    missing=[]
    for folder,repo,revision,files in SOURCES:
        for f in files:
            if not (backend/'vendor'/folder/f).is_file():missing.append(folder+'/'+f)
    running=None
    if os.name=='nt' and shutil.which('tasklist'):
        r=subprocess.run(['tasklist','/FI','IMAGENAME eq Weixin.exe','/FO','CSV','/NH'],capture_output=True)
        running=b'weixin.exe' in r.stdout.lower()
    return dict(platform=platform.platform(),root=str(root),base_python=str(python),
        wechat_running=running,uv_available=bool(shutil.which('uv')),
        libreoffice_available=any(Path(p).exists() for p in ['C:/Program Files/LibreOffice/program/soffice.exe','D:/Program Files/LibreOffice/program/soffice.exe']),
        backend_present=(backend/'read_group.py').is_file(),
        private_environment_present=(backend/'.venv/Scripts/python.exe').is_file(),
        chat_index_present=(backend/'data/wechat-local-index.sqlite').is_file(),
        media_index_present=(backend/'data/wechat-media-index.sqlite').is_file(),
        model_present=(backend/'models/faster-whisper-base/model.bin').is_file(),
        upstream_files_to_fetch=missing,
        next_action='程序已安装；运行wechat.py doctor查看记录状态' if (backend/'read_group.py').is_file()
        else '加--apply安装程序，再运行wechat.py refresh读取微信记录')


def run(command,**kwargs):
    print('Setup: '+str(command[0])+' '+str(command[1]),file=sys.stderr,flush=True)
    subprocess.run([str(x) for x in command],stdout=sys.stderr,stderr=sys.stderr,check=True,**kwargs)


def connection(root):
    backend=root/'auto-read'
    folder=root/'connections';folder.mkdir(parents=True,exist_ok=True)
    value=dict(mcpServers=dict(wechat_local=dict(command=str(backend/'.venv/Scripts/python.exe'),
        args=['-X','utf8',str(backend/'read_group.py'),'--server'])))
    path=folder/'mcp-stdio.json'
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(path)


def deploy(root,python,vault=None,group=None):
    if os.name!='nt':raise RuntimeError('当前部署实现需要Windows；请按实际系统选择后端。')
    backend=root/'auto-read'
    for folder in ['data','logs','exports','models']:(backend/folder).mkdir(parents=True,exist_ok=True)
    copied=[]
    for source in (SKILL/'assets/backend').iterdir():
        if source.is_file() and not (backend/source.name).exists():
            shutil.copyfile(source,backend/source.name);copied.append(source.name)
    settings_path=backend/'runtime-settings.json'
    settings=json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
    if vault is not None:settings['vault']=str(Path(vault).resolve())
    if group is not None:settings['group']=group
    settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    policy=backend/'excluded_sessions.json'
    if not policy.exists():policy.write_text(json.dumps(dict(version=1,accounts={},rules={})),encoding='utf-8')
    rules=root/'AGENTS.md'
    if not rules.exists():shutil.copyfile(SKILL/'assets/project-rules.md',rules)
    venv=backend/'.venv/Scripts/python.exe'
    uv=shutil.which('uv')
    if not venv.exists():
        if uv:run([uv,'venv',str(backend/'.venv'),'--python',str(python)])
        else:run([python,'-m','venv',str(backend/'.venv')])
    requirements=backend/'requirements.txt'
    required=[x.split('==')[0] for x in requirements.read_text(encoding='utf-8').splitlines() if x.strip() and not x.startswith('#')]
    code='import importlib.metadata as m,json; names='+repr(required)+'; out=[]\nfor n in names:\n try:m.version(n)\n except m.PackageNotFoundError:out.append(n)\nprint(json.dumps(out))'
    missing=json.loads(subprocess.check_output([str(venv),'-X','utf8','-c',code],text=True,encoding='utf-8'))
    if missing:
        if uv:run([uv,'pip','install','--python',str(venv),'-r',str(requirements)])
        else:
            has_pip=subprocess.run([str(venv),'-m','pip','--version'],capture_output=True).returncode==0
            if not has_pip:run([venv,'-m','ensurepip','--upgrade'])
            run([venv,'-m','pip','install','-r',str(requirements)])
    downloaded=[]
    for folder,repo,revision,files in SOURCES:
        for filename in files:
            target=backend/'vendor'/folder/filename
            if target.exists():continue
            target.parent.mkdir(parents=True,exist_ok=True)
            url=f'https://raw.githubusercontent.com/{repo}/{revision}/{filename}'
            request=urllib.request.Request(url,headers={'User-Agent':'wechat-local-skill'})
            print('Setup: fetching '+folder+'/'+filename,file=sys.stderr,flush=True)
            with urllib.request.urlopen(request,timeout=60) as response:body=response.read()
            staging=target.with_suffix(target.suffix+'.part');staging.write_bytes(body);staging.replace(target)
            downloaded.append(folder+'/'+filename)
    return dict(root=str(root),files_added=copied,upstream_files_added=downloaded,connection_file=connection(root),
                next_action='在电脑版微信登录后，运行wechat.py refresh')


def prepare_model(root):
    backend=root/'auto-read';python=backend/'.venv/Scripts/python.exe'
    if not python.exists():raise RuntimeError('先使用--apply部署后端环境。')
    destination=backend/'models/faster-whisper-base'
    if not (destination/'model.bin').exists() or not (destination/'tokenizer.json').exists():
        code='from faster_whisper.utils import download_model;download_model("base",output_dir='+repr(str(destination))+')'
        run([python,'-X','utf8','-c',code])
    return dict(model_directory=str(destination),next_action='wechat.py call wechat_refresh_media_index，然后读取目标语音')


def main():
    default='D:/WeChatBridge' if Path('D:/').exists() else str(Path.home()/'Projects/WeChatBridge')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=os.environ.get('WECHAT_LOCAL_ROOT',default))
    p.add_argument('--python');p.add_argument('--apply',action='store_true')
    p.add_argument('--vault');p.add_argument('--group')
    p.add_argument('--prepare-model',action='store_true');p.add_argument('--connection-only',action='store_true')
    a=p.parse_args();root=Path(a.root).resolve();python=runtime_python(a.python)
    result=plan(root,python)
    if a.apply:result['deployment']=deploy(root,python,a.vault,a.group)
    if a.prepare_model:result['transcription']=prepare_model(root)
    if a.connection_only:result['connection_file']=connection(root)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps(dict(error=str(exc),next_action='根据该阶段返回的具体问题处理后，从本阶段继续'),ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
