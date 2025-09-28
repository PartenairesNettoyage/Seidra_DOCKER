import importlib
import os
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture()
def video_timeline_client(tmp_path):
    pytest.importorskip('fastapi')

    os.environ['SEIDRA_DATABASE_URL'] = f"sqlite:///{tmp_path / 'timeline.db'}"
    os.environ['SEIDRA_MEDIA_DIR'] = str(tmp_path / 'media')
    os.environ['SEIDRA_THUMBNAIL_DIR'] = str(tmp_path / 'thumbs')
    os.environ['SEIDRA_MODELS_DIR'] = str(tmp_path / 'models')
    os.environ['SEIDRA_TMP_DIR'] = str(tmp_path / 'tmp')

    for module in [
        'api.media',
        'api.generation',
        'core.config',
        'services.database',
    ]:
        sys.modules.pop(module, None)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    database_module = importlib.import_module('services.database')
    Base = database_module.Base
    engine = database_module.engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = database_module.DatabaseService()
    try:
        db.create_user('video-user', 'video@example.com', 'hashed')
    finally:
        db.close()

    media_module = importlib.import_module('api.media')
    generation_module = importlib.import_module('api.generation')

    app = FastAPI()
    app.include_router(media_module.router, prefix='/media')
    app.include_router(generation_module.router, prefix='/generate')
    app.dependency_overrides[generation_module.verify_token] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[media_module.verify_token] = lambda: SimpleNamespace(id=1)

    with TestClient(app) as client:
        yield client, database_module.DatabaseService


def test_full_timeline_flow(video_timeline_client):
    client, DatabaseService = video_timeline_client

    upload_response = client.post(
        '/media/video-assets',
        data={'duration': '4.5'},
        files={'file': ('clip.mp4', b'video-bytes', 'video/mp4')},
    )
    assert upload_response.status_code == 200
    asset_payload = upload_response.json()

    download_response = client.get(f"/media/video-assets/{asset_payload['id']}")
    assert download_response.status_code == 200
    assert download_response.headers['content-type'] == asset_payload['mime_type']

    timeline_payload = {
        'name': 'Montage API',
        'description': 'Test intégration timeline',
        'frame_rate': 24,
        'total_duration': 4.5,
        'assets': [
            {
                'id': asset_payload['id'],
                'name': asset_payload['name'],
                'kind': asset_payload['kind'],
                'duration': asset_payload['duration'],
                'status': 'ready',
                'url': asset_payload['url'],
                'download_url': asset_payload['download_url'],
                'file_size': asset_payload['file_size'],
                'job_id': None,
                'created_at': asset_payload['created_at'],
                'mime_type': asset_payload['mime_type'],
            }
        ],
        'clips': [
            {
                'id': 'clip-1',
                'asset_id': asset_payload['id'],
                'start': 0,
                'duration': asset_payload['duration'],
                'layer': 'video',
            }
        ],
    }

    timeline_response = client.post('/generate/video/timeline', json=timeline_payload)
    assert timeline_response.status_code == 200
    body = timeline_response.json()
    timeline_id = body['id']
    assert body['name'] == 'Montage API'
    assert body['total_duration'] == pytest.approx(4.5)

    fetch_response = client.get(f'/generate/video/timeline/{timeline_id}')
    assert fetch_response.status_code == 200
    fetched = fetch_response.json()
    assert fetched['id'] == timeline_id
    assert fetched['assets'][0]['id'] == asset_payload['id']

    render_response = client.post(f'/generate/video/timeline/{timeline_id}/render')
    assert render_response.status_code == 200
    render_body = render_response.json()
    job_id = render_body['job_id']
    assert render_body['status'] == 'queued'

    db = DatabaseService()
    try:
        record = db.get_video_timeline(timeline_id, 1)
        assert record is not None
        assert record.job_id == job_id

        job = db.get_job(job_id)
        assert job is not None
        assert job.job_type == 'video_timeline'
        assert job.parameters['timeline_id'] == timeline_id
    finally:
        db.close()

    second_render = client.post(f'/generate/video/timeline/{timeline_id}/render')
    assert second_render.status_code == 409
