"""Read-only, temporary database snapshots and in-memory image decoding material."""
from contextlib import contextmanager, redirect_stdout
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import logging
from pathlib import Path
import re
import struct
import sys
import tempfile
import types

from read_group import ROOT, DATA
from wechat_index import status


def current_account():
    from wx4.paths import list_account_dirs
    accounts = list_account_dirs()
    if not accounts:
        raise RuntimeError('请先登录电脑版微信。')
    account = accounts[0]
    fingerprint = hashlib.sha256(account['wxid'].encode()).hexdigest()[:16]
    if fingerprint != status()['account_fingerprint']:
        raise RuntimeError('当前微信账号与索引不一致。')
    return account


@contextmanager
def snapshot():
    from wx4.key import KeyExtractor
    from wx4.decrypt import decrypt_all
    from wx4.reader import Wx4Data
    account = current_account()

    class ScopedExtractor(KeyExtractor):
        def collect(self):
            super().collect()
            self.db_files = [x for x in self.db_files if
                re.fullmatch(r'(?:biz_)?message_\d+\.db|media_\d+\.db|message_resource\.db', Path(x['path']).name)]
            self.salt_index = {}
            for item in self.db_files:
                self.salt_index.setdefault(item['salt'], []).append(item)
            return self.db_files

    extractor = None
    keys = {}
    try:
        with redirect_stdout(sys.stderr):
            extractor = ScopedExtractor(account['db_storage'])
            extractor.extract()
            keys = {k:v for k,v in extractor.result_payload().items() if not k.startswith('_')}
            if not keys or len(keys) != len(extractor.db_files):
                raise RuntimeError('媒体数据库读取条件不完整；保留已有媒体索引。')
            print('Media: snapshotting %s databases.' % len(keys), file=sys.stderr, flush=True)
            with tempfile.TemporaryDirectory(prefix='media-snapshot-', dir=DATA) as scratch:
                result = decrypt_all(keys, account['db_storage'], scratch)
                if result['failed'] or result['skipped']:
                    raise RuntimeError('媒体数据库快照校验失败。')
                data = Wx4Data(scratch, wxid=account['wxid'], account_dir=account['path'])
                try:
                    yield account, data
                finally:
                    data.close()
    finally:
        keys.clear()
        if extractor is not None:
            extractor.keys.clear()


def isolated_media_module():
    name = '_wechat_readonly_vendor'
    if name + '.media' in sys.modules:
        return sys.modules[name + '.media'], sys.modules[name + '.db']
    folder = ROOT / 'vendor/wechatauto-replica/wechatauto'
    package = types.ModuleType(name)
    package.__path__ = [str(folder)]
    sys.modules[name] = package
    # Load only db/media files. Never execute the upstream package/UI initializer.
    original_package = sys.modules.get('wechatauto')
    original_logger = sys.modules.get('wechatauto.logger')
    stub = types.ModuleType('wechatauto')
    stub.__path__ = [str(folder)]
    logger = types.ModuleType('wechatauto.logger')
    logger.wxlog = logging.getLogger('wechat-readonly-media')
    logger.wxlog.disabled = True
    sys.modules['wechatauto'] = stub
    sys.modules['wechatauto.logger'] = logger
    try:
        for sub in ('db', 'media'):
            spec = importlib.util.spec_from_file_location(name + '.' + sub, folder / (sub + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
    finally:
        for key, previous in [('wechatauto', original_package), ('wechatauto.logger', original_logger)]:
            if previous is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous
    return sys.modules[name + '.media'], sys.modules[name + '.db']


class ImageReader:
    def __init__(self, account):
        import psutil
        self.account = account
        self.module, self.helpers = isolated_media_module()
        adapter = types.SimpleNamespace(account_dir=account['path'], wxid=account['wxid'],
            _find_weixin_pids=lambda:[p.pid for p in psutil.process_iter(['name'])
                if (p.info['name'] or '').lower() == 'weixin.exe'])
        self.downloader = self.module.MediaDownloader(adapter)
        self.downloader._persist_key = lambda value: None
        self.downloader._load_persisted_key = lambda: None
        # No implicit upstream polling, UI requests, or disk key cache.
        self.downloader._resolve_aes_key = lambda: None
        self.material = None

    def _derive(self, sample):
        with Path(sample).open('rb') as f:
            self.downloader._key_probe = f.read(31)[15:31]
        helpers = self.helpers
        k32 = helpers._k32
        for pid in self.downloader.db._find_weixin_pids():
            module = helpers._find_weixin_module(pid)
            if not module:
                continue
            base, size, dll = module
            handle = k32.OpenProcess(0x410, False, pid)
            if not handle:
                continue
            def read(address, n):
                buffer = ctypes.create_string_buffer(n)
                got = ctypes.c_size_t()
                k32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, n, ctypes.byref(got))
                return buffer.raw[:got.value]
            try:
                disk = Path(dll).read_bytes()
                pe = struct.unpack_from('<I', disk, 0x3c)[0]
                count = struct.unpack_from('<H', disk, pe+6)[0]
                opt = struct.unpack_from('<H', disk, pe+20)[0]
                for section in range(count):
                    offset = pe+24+opt+section*40
                    virtual_size, rva = struct.unpack_from('<II', disk, offset+8)
                    if not struct.unpack_from('<I', disk, offset+36)[0] & 0x80000000:
                        continue
                    for start in range(0, virtual_size, 2*1024*1024):
                        address = base+rva+start
                        buf = read(address, min(2*1024*1024+64, virtual_size-start))
                        pos = buf.find(b'global_config')
                        while pos >= 0:
                            if pos+32 <= len(buf) and struct.unpack_from('<QQ', buf, pos+16) == (13,15):
                                pointer = read(address+pos+16-0x138, 8)
                                if len(pointer) == 8:
                                    pointer = read(struct.unpack('<Q',pointer)[0]+0x68, 8)
                                    if len(pointer) == 8:
                                        cfg = struct.unpack('<Q',pointer)[0]
                                        user = helpers._read_remote_string(handle, read, cfg+0x48)
                                        material = read(cfg+0x40, 4)
                                        if user == self.account['wxid'] and len(material) == 4:
                                            candidate = self.downloader.derive_image_keys(struct.unpack('<I',material)[0], user)
                                            if self.downloader._validate_key(candidate[0]):
                                                return candidate
                            pos = buf.find(b'global_config', pos+1)
            finally:
                k32.CloseHandle(handle)
        return None

    def decode(self, path):
        from wx4.media import decode_dat
        with Path(path).open('rb') as f:
            signature = f.read(6)
        if signature == self.module.V2_MAGIC:
            if self.material is None:
                self.material = self._derive(path)
            if self.material is None:
                raise RuntimeError('当前图片解密条件不可用；未操作微信界面。')
            return self.downloader.decrypt_image(str(path), aes_key=self.material[0], xor_key=self.material[1])
        raw = Path(path).read_bytes()
        if raw.startswith((b'\xff\xd8\xff', b'\x89PNG', b'GIF8', b'RIFF', b'BM')):
            return raw
        plain = decode_dat(raw)
        if plain is not None:
            return plain
        return self.downloader.decrypt_image(str(path), xor_key=self.material[1] if self.material else None)

    def close(self):
        self.material = None
        self.downloader._image_key = self.downloader._img_key = self.downloader._key_probe = None
