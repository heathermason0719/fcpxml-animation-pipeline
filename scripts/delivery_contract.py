"""One machine-owned delivery protocol, shared by every publication path."""
import json
import re
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'references/work-model-contract.json'
CONTRACT = json.loads(CONTRACT_PATH.read_text())
PROTOCOL_VERSION = CONTRACT['deliveryProtocolVersion']


def delivery_names(identity, release_id):
    if not re.fullmatch(r'd\d{4,}', release_id): raise ValueError('invalid release id')
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '-', identity['episodeTitle'].strip())
    title = re.sub(r'\s+', '-', title)
    title = re.sub('-+', '-', title).strip('.-')[:120]
    if not title: raise ValueError('episode title has no usable characters')
    values = {'episode': title, 'number': release_id[1:]}
    return CONTRACT['delivery']['directoryPattern'].format(**values), CONTRACT['delivery']['xmlPattern'].format(**values)


def documentation_block():
    return '\n'.join(['<!-- delivery-contract:start -->',
        '当前正式交付协议：' + PROTOCOL_VERSION + '。',
        '目录：`AfterForge/' + CONTRACT['delivery']['directoryPattern'] + '/`。',
        'XML：`' + CONTRACT['delivery']['xmlPattern'] + '`，与当前 XML 使用的全部 AfterForge 动画 MOV 同级。',
        '同一 SHA-256 只保存一个物理媒体实体；正式版本间可硬链接。内部仅保留元数据和 XML 证据。',
        '<!-- delivery-contract:end -->'])
