#!/usr/bin/env python3
"""Prepare equal isolated history for an actual Agent tool-choice exercise.

This utility does not choose queries or perform the measured edit/registration.
The Agent reads SKILL and invokes the normal CLI; report reads those receipts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import work_model as model
from scripts.work_model_store import load, layout
from tests.test_work_model_concepts import png_bytes
from tests.work_model_fixtures import request, user


def hashes(root):
    result={}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('synthetic history must not contain symlinks')
        if path.is_file():
            result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def prepare(source, destination):
    if destination.exists():
        raise ValueError('output directory must not exist')
    afterforge,_=layout(source)
    before=hashes(afterforge)
    master=destination/'seed/AfterForge';master.parent.mkdir(parents=True)
    shutil.copytree(afterforge,master)
    relative=source.relative_to(afterforge);root=master/relative
    model.update(root,request(root,'fixture-intent',operation='working-intent',upserts=[
        {'id':'focus-a','kind':'focus','text':'补 A 说明并保留三张非推荐候选','locator':{'description':'Scene A','cueId':'a'},'source':user('隔离验证要求')},
        {'id':'preserve-b','kind':'preserve','text':'保留 B 与所有有效原意见','locator':{'description':'Scene B','cueId':'b'},'source':user('隔离验证要求')}]))
    vid=load(root)['identity']['versionId']
    model.update(root,request(root,'fixture-global',operation='feedback',body='全片仍需保留节奏讨论意见',target={'versionId':vid},source=user('隔离全片意见')))
    model.update(root,request(root,'fixture-range',operation='feedback',body='1 秒到 2 秒的时间意见',target={'versionId':vid,'timeStart':'1s','timeEnd':'2s'},source=user('隔离时间意见')))
    roots={}
    for name in ('baseline','improved'):
        dest=destination/name/'AfterForge';dest.parent.mkdir(parents=True)
        shutil.copytree(master,dest);version=dest/relative;roots[name]=str(version)
        stage=version/'.staging/creative-inputs/round2';stage.mkdir(parents=True)
        for i,color in enumerate(((120,100,220),(70,150,160),(180,130,70)),1):
            (stage/f'candidate-{i}.png').write_bytes(png_bytes(color))
    assert hashes(afterforge)==before
    metadata={'sourceVersion':str(source),'sourceAfterForge':str(afterforge),'sourceHashes':before,
        'roots':roots,'task':'给 A 现有总体说明末尾补一句“保持标题停留，便于阅读。”；保留 B 与原意见；登记三张合成非推荐候选，不换推荐、不确认、不渲染。',
        'fixtureOnly':True,'measuredActionsPerformed':False}
    (destination/'prepare.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in metadata.items() if k!='sourceHashes'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-version',type=Path,required=True)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.source_version.resolve(),args.root.resolve())
