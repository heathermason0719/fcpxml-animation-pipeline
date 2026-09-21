"""Resumable deterministic jobs. Journals track execution; manifests own decisions."""
from __future__ import annotations
import copy
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from fractions import Fraction
from pathlib import Path

from scripts.manifest_transaction import manifest_transaction
from scripts.hyperframes_adapter import parse_time
from scripts.fcpxml_timing import format_time
from scripts.validate_delivery import DeliveryExpectation, probe_delivery, validate_probe
from scripts.work_model_store import atomic_json, digest, layout, load, now, project_lock, request_check, remember, safe, save, sha, verified_operation, fresh_hashes
from scripts.work_model_inputs import animation_cues, cue_inputs, cue_key, dependencies, preview_range, source_paths, timeline_inputs, timeline_key
from scripts.work_model_media import render_cue, composite_preview, validate_alpha
from scripts.work_model_policy import production_basis, first_confirmed, upgrade, blocking_feedback
from scripts.work_model_storyboard import storyboard_spec, render_storyboard


def _validate_media(path, manifest, cue, quality, log):
    dims = manifest['project']['preview' if quality == 'preview' else 'delivery']
    fps = 1 / parse_time(manifest['project']['source']['frameDuration'])
    duration = parse_time(cue['resolvedTimeline']['duration'])
    probe = probe_delivery(path)
    issues = validate_probe(probe, DeliveryExpectation(dims['width'], dims['height'], fps, duration))
    # ffprobe decimal duration is rounded; reject a missing or extra frame.
    if abs(Fraction(str(probe['duration'])) - duration) >= 1 / (fps * 2):
        issues.append('exact_duration_mismatch')
    if issues:
        raise ValueError('invalid cue media: ' + ', '.join(issues))
    alpha_cue = copy.deepcopy(cue)
    if quality == 'preview':
        # Declared points use the canonical native coordinate space.
        native = manifest['project']['delivery']
        for sample in alpha_cue.get('alphaExpectation', {}).get('samples', []):
            for field in ('transparentPoints','opaquePoints'):
                sample[field] = [[int(x*dims['width']/native['width']), int(y*dims['height']/native['height'])] for x,y in sample.get(field,[])]
    return {'probe':probe,'alpha':validate_alpha(path, alpha_cue, log_path=log)}


def supplemental_key(root, manifest, cue):
    return digest({'cue':cue_key(root,manifest,cue), 'source':manifest.get('sourceHashes'),
                   'placement':{name:format_time(parse_time(cue['resolvedTimeline'][name])) for name in ('start','duration')},
                   'dimensions':manifest['project']['preview']})


def _spec(root, manifest, action, request, *, job_id=None):
    scope = request.get('scope', 'local')
    if 'allowDraft' in request and type(request['allowDraft']) is not bool:
        raise ValueError('allowDraft must be an explicit boolean')
    if action == 'preview' and scope in {'storyboard', 'still', 'exploration'}:
        candidate = manifest
        if scope == 'exploration':
            from scripts.work_model_exploration import candidate_manifest
            candidate = candidate_manifest(manifest, request)
        if scope == 'still' and len(request.get('cueIds', [])) != 1:
            raise ValueError('still preview requires exactly one cueId')
        lineage = {}
        if scope == 'exploration':
            exploration = next(e for e in manifest['explorations'] if e['id'] == request['explorationId'])
            variant = next(v for v in exploration['variants'] if v['id'] == request['variantId'])
            from scripts.work_model_exploration import variant_lineage
            current_lineage = variant_lineage(variant, root, manifest=manifest)
            lineage = {key: current_lineage.get(name) for key, name in
                       [('variantRevision', 'revision'), ('variantContentIdentity', 'contentIdentity')]}
        return {**lineage, 'lineageFiles': current_lineage.get('files', []) if scope == 'exploration' else [], 'scope': scope, 'static': storyboard_spec(root, candidate, request),
                'explorationId': request.get('explorationId'), 'variantId': request.get('variantId')}
    source_paths(root, manifest)
    if action == 'preview':
        if scope not in {'local', 'full'}:
            raise ValueError('unsupported preview scope')
        start, duration = preview_range(manifest, request)
        work = request.get('workCueIds', request.get('cueIds', []))
        data = timeline_inputs(root, manifest, start=start, duration=duration,
            allow_draft=request.get('allowDraft', False), required_cue_ids=work,
            excluded_cue_ids=request.get('excludedCueIds', []))
        # An old unapproved motion file is historical media, not an available
        # active implementation. Context must never auto-enrol it into work.
        task = next((d for d in manifest['decisions'] if d.get('taskId') == request.get('taskId')
                     and d['kind'] == 'explore-motion'), None)
        available = []
        for overlay in data['overlays']:
            cue = next(c for c in manifest['cues'] if c['id'] == overlay['cueId'])
            eligible = first_confirmed(manifest, cue.get('objectId')) or (scope != 'full' and task
                       and cue.get('objectId') in task['objectIds'])
            if eligible or cue['id'] in work:
                available.append(overlay)
            else:
                data['missingCueIds'].append(cue['id'])
        data['overlays'] = available
        basis = production_basis(manifest, request, [o['cueId'] for o in available], full=scope == 'full',
                                 job_id=job_id, time_range=data['range'])
        if scope == 'full' and not available and data['missingCueIds']:
            raise ValueError('first design confirmation required before full Motion production')
        return {'timeline': data, 'scope': scope, 'workCueIds': work, 'productionBasis': basis}
    data = timeline_inputs(root, manifest)
    return {'timeline': data, 'native': {c['id']: cue_key(root, manifest, c, 'delivery') for c in animation_cues(manifest)},
            'identity': manifest['identity'], 'protocol': '2'}


def _approved(root, manifest):
    from scripts.work_model import current_review_set
    review = current_review_set(root,manifest)
    if not review:
        raise ValueError('current complete review set is required for delivery')
    kinds={d['kind'] for d in manifest['decisions'] if d.get('reviewSetId') == review['id']}
    if not ({'approve','authorize'} <= kinds or 'approve-and-deliver' in kinds):
        raise ValueError('explicit user approval and authorization are required')
    from scripts.work_model_feedback_targets import review_target
    if blocking_feedback(manifest, review_target(manifest, review)):
        raise ValueError('pending feedback must be resolved before delivery')
    return review


def _job_path(root, job_id):
    if not isinstance(job_id,str) or not job_id.startswith('job-') or any(c not in '0123456789abcdef' for c in job_id[4:]):
        raise ValueError('invalid jobId')
    return safe(root,'jobs/'+job_id+'.json',exists=False)


def _number(root, manifest, afterforge, index):
    numbers=[]
    episode=next(ep for ep in index['episodes'] if ep['id']==manifest['identity']['episodeId'])
    for version in episode['versions']:
        version_root=safe(afterforge,version['root'])
        m=load(version_root)
        numbers += [int(d['id'][1:]) for d in m.get('deliveries',[])]
        for file in (version_root/'jobs').glob('*.json'):
            record=json.loads(file.read_text())
            if record.get('releaseId'):
                numbers.append(int(record['releaseId'][1:]))
    return 'd'+str(max(numbers,default=0)+1).zfill(4)


def _snapshot(root, manifest, spec, destination, review=None):
    names=set(spec.get('static', {}).get('files', []))
    names.update(spec.get('lineageFiles', []))
    for overlay in spec.get('timeline', {}).get('overlays', []):
        cue=next(c for c in manifest['cues'] if c['id']==overlay['cueId'])
        names.update(cue_inputs(root,manifest,cue)['files'])
    if 'timeline' in spec:
        names.update(path.relative_to(root).as_posix() for path in source_paths(root,manifest))
    names.update(p.relative_to(root).as_posix() for p in (root/'assets/source').glob('narration-*') if p.is_file())
    if review:
        names.update(a['path'] for a in manifest['artifacts'] if a['id'] in review['artifactIds'])
    # Cache location is not an input identity. Copy only proven reusable bytes
    # into this job's fixed snapshot, then reverify there before reuse.
    if spec.get('static') and spec.get('scope') != 'exploration':
        from scripts.work_model_storyboard import reusable_frame
        for frame in spec['static']['frames']:
            cached = reusable_frame(root, manifest, frame)
            if cached:
                names.add(cached['path'])
    for name in names:
        target=safe(destination,name,exists=False)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(safe(root,name),target)
    return sorted(names)


def _cache(root, snapshot, manifest, cue, quality, job):
    key=cue_key(snapshot,manifest,cue,quality)
    relative=f'cache/cues/{quality}/{key}/media.mov'
    movie=safe(root,relative,exists=False)
    record_path=movie.with_suffix('.json')
    log=snapshot/'render.log'
    valid=None
    if movie.is_file() and record_path.is_file():
        try:
            record=json.loads(record_path.read_text())
            if record.get('inputKey')==key and record.get('sha256')==sha(movie):
                valid=_validate_media(movie,manifest,cue,quality,log)
        except (ValueError,OSError,subprocess.CalledProcessError):
            valid=None
    cache_hit = valid is not None
    if valid is None:
        target=safe(snapshot,relative,exists=False)
        render_cue(snapshot,manifest,cue,quality=quality,target=target,log_path=log)
        valid=_validate_media(target,manifest,cue,quality,log)
        record={'inputKey':key,'sha256':sha(target),'path':relative,**valid}
        with manifest_transaction(root):
            movie.parent.mkdir(parents=True,exist_ok=True)
            temporary=movie.with_name('.media-'+job['id']+'.mov')
            shutil.copy2(target,temporary)
            os.replace(temporary,movie)
            atomic_json(record_path,record)
    destination=safe(snapshot,relative,exists=False)
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(movie,destination)
    job.setdefault('mediaReuse', {})[cue['id']] = 'cache-hit' if cache_hit else 'rebuilt'
    job['completedCueIds']=list(dict.fromkeys(job.get('completedCueIds',[])+[cue['id']]))
    atomic_json(_job_path(root,job['id']),job)
    return {'path':relative,'sha256':sha(destination),'inputKey':key,**valid}


def _artifact(root, manifest, kind, path, key, time_range, cue_ids, complete=True, **extra):
    return {'id':'artifact-'+digest([kind,key,time_range,extra])[:20], 'kind':kind,
            'path':path.relative_to(root).as_posix(),'sha256':sha(path),'inputKey':key,
            'range':time_range,'cueIds':cue_ids,'complete':complete,'createdAt':now(),**extra}


def _overlap_ids(overlays):
    result=set()
    for i,a in enumerate(overlays):
        for b in overlays[i+1:]:
            if max(parse_time(a['start']),parse_time(b['start'])) < min(parse_time(a['start'])+parse_time(a['duration']),parse_time(b['start'])+parse_time(b['duration'])):
                result.update([a['cueId'],b['cueId']])
    return result


def _preview_output(root, snap, manifest, spec, job):
    data=spec['timeline']; overlays=copy.deepcopy(data['overlays'])
    for overlay in overlays:
        cue=next(c for c in manifest['cues'] if c['id']==overlay['cueId'])
        overlay['path']=_cache(root,snap,manifest,cue,'preview',job)['path']
    start=parse_time(data['range']['start']);duration=parse_time(data['range']['duration'])
    key=digest(data)
    output=snap/f'previews/{job["id"]}/demo.mp4'
    composite_preview(snap,manifest,overlays,start=start,duration=duration,target=output,log_path=snap/'render.log')
    kind='full-preview' if spec['scope']=='full' else 'local-preview'
    artifacts=[]
    coverage = {'workCueIds': spec['workCueIds'], 'presentedCueIds': [o['cueId'] for o in overlays],
                'reusedCueIds': [o['cueId'] for o in overlays if o['cueId'] not in spec['workCueIds']],
                'excludedCueIds': data.get('excludedCueIds', []), 'missingCueIds': data['missingCueIds'],
                'mediaReuse': dict(job.get('mediaReuse', {}))}
    artifacts.append(_artifact(snap,manifest,kind,output,key,data['range'],[o['cueId'] for o in overlays],
        not data['missingCueIds'] and not data.get('excludedCueIds'), coverage=coverage,
        missingCueIds=data['missingCueIds'], excludedCueIds=data.get('excludedCueIds', []),
        productionBasis=spec['productionBasis'], eventId=job['id'],
        previewRequest={key: copy.deepcopy(job['request'][key]) for key in
            ('scope', 'cueIds', 'workCueIds', 'segmentIds', 'range', 'excludedCueIds', 'allowDraft', 'taskId')
            if key in job['request']}))
    # Conservatively supply every overlapping animation in isolation, covering its entire local duration.
    if kind=='full-preview' and not data['missingCueIds'] and not data.get('excludedCueIds'):
        for overlay in overlays:
            if overlay['cueId'] not in _overlap_ids(overlays):
                continue
            cue=next(c for c in manifest['cues'] if c['id']==overlay['cueId'])
            supplemental=supplemental_key(snap,manifest,cue)
            target=snap/f'previews/{job["id"]}/cue-{supplemental}.mp4'
            composite_preview(snap,manifest,[overlay],start=parse_time(overlay['start']),duration=parse_time(overlay['duration']),target=target,log_path=snap/'render.log')
            artifacts.append(_artifact(snap,manifest,'cue-preview',target,supplemental,{'start':overlay['start'],'duration':overlay['duration']},[cue['id']], productionBasis=spec['productionBasis'],eventId=job['id']))
    return artifacts


def _finish_preview(root, snap, manifest, spec, job):
    static = 'static' in spec
    if static:
        candidate = manifest
        if spec['scope'] == 'exploration':
            from scripts.work_model_exploration import candidate_manifest
            candidate = candidate_manifest(manifest, job['request'])
        frames = render_storyboard(snap, candidate, spec['static'], snap / 'previews' / job['id'], snap / 'render.log')
        purpose = ('exploration' if spec['scope'] == 'exploration' else
                   'still' if spec['scope'] == 'still' and 'time' in job['request'] else 'storyboard')
        artifacts = []
        for frame in frames:
            record = dict(frame)
            record.update(id='artifact-' + digest([job['id'], frame['cueId'], frame['frameId']])[:20],
                kind='still' if purpose == 'still' else purpose + '-frame', purpose=purpose, cueIds=[frame['cueId']], complete=True,
                range={'start': '0s', 'duration': '0s'}, createdAt=now(), eventId=job['id'])
            if purpose == 'exploration':
                record.update(explorationId=spec['explorationId'], variantId=spec['variantId'],
                              **{key: spec[key] for key in ('variantRevision', 'variantContentIdentity') if spec.get(key) is not None})
            artifacts.append(record)
    else:
        artifacts = _preview_output(root, snap, manifest, spec, job)
    with manifest_transaction(root):
        fresh_hashes()
        current = load(root, writable=True)
        if digest(_spec(root, current, 'preview', job['request'], job_id=job['id'])) != job['inputKey']:
            raise ValueError('inputs changed during preview; valid cue caches retained')
        upgrade(current)
        installed = []
        try:
            for artifact in artifacts:
                if sha(safe(snap, artifact['path'])) != artifact['sha256']:
                    raise ValueError('preview bytes changed before publication')
                target = safe(root, artifact['path'], exists=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if sha(target) != artifact['sha256']:
                        raise ValueError('published preview path is immutable')
                else:
                    os.replace(safe(snap, artifact['path']), target)
                    installed.append(target)
                current['artifacts'].append(artifact)
            boards = []
            if static and purpose == 'storyboard':
                for cid in dict.fromkeys(a['cueId'] for a in artifacts):
                    cue = next(c for c in current['cues'] if c['id'] == cid)
                    if not cue.get('objectId'):
                        raise ValueError('register creative object through update before Storyboard')
                    frames = [a for a in artifacts if a['cueId'] == cid]
                    board = {'id': 'storyboard-' + digest([job['id'], cid])[:20], 'cueId': cid,
                        'objectId': cue['objectId'], 'artifactIds': [a['id'] for a in frames],
                        **copy.deepcopy(spec['static']['reviews'][cid]), 'createdAt': now()}
                    boards.append(board)
                current['storyboards'].extend(boards)
            elif static and purpose == 'exploration':
                exploration = next(e for e in current['explorations'] if e['id'] == spec['explorationId'])
                variant = next(v for v in exploration['variants'] if v['id'] == spec['variantId'])
                variant['artifactIds'] = [a['id'] for a in artifacts]
                variant.update(revision=spec['variantRevision'], contentIdentity=spec['variantContentIdentity'])
            review = None
            if spec['scope'] == 'full' and all(a['complete'] for a in artifacts):
                review = {'id': 'review-' + digest([job['id'], job['inputKey']])[:20],
                    'inputKey': digest(spec['timeline']), 'artifactIds': [a['id'] for a in artifacts],
                    'productionBasis': spec['productionBasis'], 'createdAt': now()}
                current['reviewSets'].append(review)
            if not static and spec['productionBasis'].get('taskId') and spec['productionBasis']['decisionIds']:
                commission = next(d for d in current['decisions'] if d.get('taskId') == spec['productionBasis']['taskId'])
                # A local check is part of an outstanding full-Demo task, not
                # completion of it. Recovery shares its basis until that task's
                # commissioned output has actually been published.
                from scripts.work_model_policy import commission_fulfilled
                if commission_fulfilled(current, spec):
                    current['productionRuns'].append({'taskId': spec['productionBasis']['taskId'], 'jobId': job['id'],
                        'inputKey': job['inputKey'], 'createdAt': now()})
            current['editRevision'] += 1
            result = {'status': 'complete', 'jobId': job['id'], 'artifactIds': [a['id'] for a in artifacts],
                'storyboardIds': [s['id'] for s in boards], 'reviewSet': review, 'editRevision': current['editRevision']}
            remember(current, job['request'], result)
            save(root, current)
        except BaseException:
            for path in installed:
                path.unlink(missing_ok=True)
            raise
    return result


def _recover_publication(root, job):
    """A journal is a locator, never evidence: validate every actual released byte."""
    record = job.get('preparedRelease')
    if not record:
        return None
    from scripts.work_model_delivery import verify_release, _inventory
    afterforge, _ = layout(root)
    with manifest_transaction(root):
        fresh_hashes()
        current = load(root, writable=True)
        if digest(_spec(root,current,'deliver',job['request'])) != job['inputKey']:
            raise ValueError('delivery inputs changed before publication recovery')
        if _approved(root,current)['id'] != job['reviewSetId']:
            raise ValueError('delivery review changed before publication recovery')
        package = safe(afterforge,record['packagePath'],exists=False)
        snapshot = safe(root,record['snapshotPath'],exists=False)
        if package.exists() and snapshot.exists():
            verify_release(root,afterforge,record)
            if not any(d['id']==record['id'] for d in current['deliveries']):
                current['deliveries'].append(record)
                current['editRevision'] += 1
            result={'status':'complete','delivery':record,'jobId':job['id'],
                    'recovered':True,'editRevision':current['editRevision']}
            remember(current,job['request'],result)
            save(root,current)
            return result
        # One directory rename may have completed before interruption. Only
        # remove the exact inventory this job staged, then rebuild normally.
        if package.exists() and _inventory(package) != record['inventory']['package']:
            raise ValueError('partial package differs from this job; recovery refused')
        if snapshot.exists() and (_inventory(snapshot,exclude={'inventory.json'}) != record['inventory']['snapshot']
                or json.loads((snapshot/'inventory.json').read_text()) != record['inventory']):
            raise ValueError('partial snapshot differs from this job; recovery refused')
        for path in (package,snapshot):
            if path.exists(): shutil.rmtree(path)
    return None


def _finish_delivery(root,snap,manifest,spec,job,names):
    from scripts.work_model_delivery import prepare_release,publish_release,verify_release
    recovered = _recover_publication(root,job)
    if recovered:
        return recovered
    afterforge,_=layout(root)
    for number,cue in enumerate(manifest['cues']):
        if cue['productionMode']!='animation': continue
        media=_cache(root,snap,manifest,cue,'delivery',job)
        dims=manifest['project']['delivery']
        cue['layer']=cue.get('layer',number+1)
        cue['deliveryAsset']={'fileName':'AF__'+digest(cue['id'])[:12]+'.mov',
             'relativePath':media['path'],'sha256':media['sha256'],'width':dims['width'],'height':dims['height'],
             'frameRate':str(1/parse_time(manifest['project']['source']['frameDuration'])),
             'duration':cue['resolvedTimeline']['duration'],'probe':media['probe'],'alphaEvidence':media['alpha']}
    prepared=prepare_release(root,manifest,afterforge_root=afterforge,release_id=job['releaseId'],
            input_key=job['inputKey'],dependency_paths=names,input_root=snap)
    job['preparedRelease'] = prepared['record']
    atomic_json(_job_path(root,job['id']),job)
    published=False
    try:
        with manifest_transaction(root):
            fresh_hashes()
            current=load(root,writable=True)
            if digest(_spec(root,current,'deliver',job['request']))!=job['inputKey']:
                raise ValueError('inputs changed during delivery; valid cue caches retained')
            if _approved(root,current)['id']!=job['reviewSetId']:
                raise ValueError('delivery review changed during rendering')
            for existing in current['deliveries']:
                if existing['inputKey']==job['inputKey']:
                    verify_release(root,afterforge,existing)
                    return {'status':'complete','delivery':existing,'reused':True,'jobId':job['id']}
            record=publish_release(root,prepared);published=True
            current['deliveries'].append(record);current['editRevision']+=1
            result={'status':'complete','delivery':record,'jobId':job['id'],'editRevision':current['editRevision']}
            remember(current,job['request'],result)
            try: save(root,current)
            except BaseException:
                shutil.rmtree(safe(afterforge,record['packagePath']))
                shutil.rmtree(safe(root,record['snapshotPath']))
                raise
        return result
    finally:
        for field in ('stagingPackage','stagingSnapshot'):
            path=Path(prepared[field])
            if path.exists(): shutil.rmtree(path)


@verified_operation
def _run(root,action,request,*,resume_id=None):
    root=Path(root).expanduser().resolve()
    load(root,writable=True)  # Before any lock/directory in legacy versions.
    afterforge,_=layout(root)
    job_id=resume_id or 'job-'+digest([action,request.get('requestId')])[:24]
    job_path=_job_path(root,job_id)
    lock_dir=safe(root,'jobs/locks/'+job_id,exists=False);lock_dir.mkdir(parents=True,exist_ok=True)
    with manifest_transaction(lock_dir,timeout=0.1):
        with (project_lock(afterforge) if action=='deliver' else nullcontext()),manifest_transaction(root):
            manifest=load(root,writable=True)
            existing=json.loads(job_path.read_text()) if job_path.is_file() else None
            previous = None
            if resume_id:
                request_check(manifest, request)
                if not existing:
                    raise ValueError('unknown resumable job')
                original = existing['request']
                action = existing['action']
            else:
                original = request
                if existing and existing['request'] != request:
                    raise ValueError('requestId was already used with another job request')
                previous = request_check(manifest, request) if not existing else None
            upgraded = upgrade(manifest)
            from scripts.work_model_policy import correct_incomplete_runs
            correct_incomplete_runs(root, manifest)
            if action == 'deliver' and not animation_cues(manifest):
                return {'status': 'no-animation', 'message': '无需动画交付'}
            # Explicit combined user commands are registered once. Merely
            # retrying a historical task cannot manufacture a missing decision.
            if not existing and previous is None and original.get('decision'):
                from scripts.work_model import _record_decision
                _record_decision(root, manifest, original['decision'])
            review = _approved(root, manifest) if action == 'deliver' else None
            spec = _spec(root, manifest, action, original, job_id=job_id)
            key = digest(spec)
            if existing and existing['inputKey'] != key:
                raise ValueError('job inputs changed; start a new request to reuse unaffected caches')
            cached_result = previous or (existing.get('result') if existing and existing['status'] == 'complete' else None)
            if cached_result is not None:
                if action == 'deliver' and cached_result.get('delivery'):
                    from scripts.work_model_delivery import verify_release
                    verify_release(root, afterforge, cached_result['delivery'])
                else:
                    from scripts.work_model import _artifact_current
                    records = {a['id']: a for a in manifest['artifacts']}
                    if not all(key in records and _artifact_current(root, manifest, records[key])
                               for key in cached_result.get('artifactIds', [])):
                        raise ValueError('cached preview no longer matches verified current inputs')
                return cached_result
            if action=='deliver':
                for release in manifest['deliveries']:
                    if release['inputKey']==key:
                        from scripts.work_model_delivery import verify_release
                        verify_release(root,afterforge,release)
                        manifest['editRevision'] += 1
                        result = {'status':'complete','delivery':release,'reused':True,
                                  'editRevision':manifest['editRevision']}
                        remember(manifest,original,result)
                        save(root,manifest)
                        return result
            job=existing or {'id':job_id,'action':action,'inputKey':key,'request':original,'createdAt':now(),'completedCueIds':[]}
            if action=='deliver':
                job['reviewSetId']=review['id']
                if not job.get('releaseId'):
                    _,index=layout(root);job['releaseId']=_number(root,manifest,afterforge,index)
            if upgraded or (not existing and original.get('decision')) or manifest != load(root):
                manifest['editRevision'] += 1
                save(root, manifest)
            job.update(status='running',updatedAt=now(),error=None)
            atomic_json(job_path,job)
            scratch=safe(root,'jobs/.scratch',exists=False);scratch.mkdir(parents=True,exist_ok=True)
            snap=Path(tempfile.mkdtemp(prefix=job_id+'-',dir=scratch))
            try:
                names=_snapshot(root,manifest,spec,snap,review)
                if digest(_spec(snap,manifest,action,original,job_id=job_id))!=key:
                    raise ValueError('inputs changed while freezing task')
            except BaseException as error:
                job.update(status='failed',error=str(error),updatedAt=now())
                atomic_json(job_path,job)
                shutil.rmtree(snap);raise
        try:
            result=(_finish_preview(root,snap,manifest,spec,job) if action=='preview' else
                    _finish_delivery(root,snap,manifest,spec,job,names))
            job.update(status='complete',result=result,updatedAt=now());atomic_json(job_path,job)
            if resume_id:
                with manifest_transaction(root):
                    current=load(root,writable=True);remember(current,request,result);save(root,current)
            return result
        except BaseException as error:
            job.update(status='failed',error=str(error),updatedAt=now());atomic_json(job_path,job)
            raise
        finally:
            log=snap/'render.log'
            if log.is_file():
                with (root/'jobs'/f'{job_id}.log').open('ab') as dest,log.open('rb') as source:
                    shutil.copyfileobj(source,dest)
            shutil.rmtree(snap,ignore_errors=True)


def preview(root,request): return _run(root,'preview',request)
def deliver(root,request): return _run(root,'deliver',request)
def resume(root,request):
    job_path=_job_path(Path(root).resolve(),request.get('jobId'))
    if not job_path.is_file(): raise ValueError('unknown resumable job')
    action=json.loads(job_path.read_text())['action']
    return _run(root,action,request,resume_id=request['jobId'])
