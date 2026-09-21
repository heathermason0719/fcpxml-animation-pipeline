"""Mutable version context. Deliberately independent of all production policy."""
import copy

from scripts.work_model_store import now, user_source


def update_intent(manifest, request):
    upserts, removes = request.get('upserts', []), request.get('removeIds', [])
    if not isinstance(upserts, list) or not isinstance(removes, list):
        raise ValueError('working-intent requires upserts and removeIds arrays')
    ids = [item.get('id') if isinstance(item, dict) else None for item in upserts]
    if any(not isinstance(key, str) or not key.strip() for key in ids + removes):
        raise ValueError('working-intent items require stable nonempty IDs')
    if len(set(ids)) != len(ids) or len(set(removes)) != len(removes) or set(ids) & set(removes):
        raise ValueError('working-intent IDs must be unique and cannot be both upserted and removed')
    items = {item['id']: copy.deepcopy(item) for item in manifest.get('workingIntent', {}).get('items', [])}
    for key in removes:
        items.pop(key, None)
    for item in upserts:
        if set(item) != {'id', 'kind', 'text', 'locator', 'source'}:
            raise ValueError('working-intent upsert requires id, kind, text, locator and source')
        if not isinstance(item['text'], str) or not item['text'].strip():
            raise ValueError('working-intent text must be nonempty')
        items[item['id']] = {**copy.deepcopy(item), 'source': user_source(item['source']), 'updatedAt': now()}
    manifest['workingIntent'] = {'items': list(items.values())}
    return copy.deepcopy(manifest['workingIntent'])
