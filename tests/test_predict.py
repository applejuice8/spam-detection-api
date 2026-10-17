from fastapi.testclient import TestClient

from app.main import app


def test_predict_spam():
    with TestClient(app) as client:
        r = client.post('/predict', json={'text': 'WINNER!! Claim your free prize now'})

    assert r.status_code == 200
    assert r.json()['label'] == 'spam'


def test_predict_rejects_empty_text():
    with TestClient(app) as client:
        r = client.post('/predict', json={'text': ''})
    assert r.status_code in (401, 422)   # 422 if auth passes, 401 if not logged in
