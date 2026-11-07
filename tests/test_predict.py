import pytest


@pytest.fixture
def headers(api_key):
    return {'X-API-Key': api_key}


async def test_predict_spam(client, spam_classifier, headers):
    r = await client.post('/predict', json={'text': 'free prize winner claim now'}, headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body['label'] == 'spam'
    assert body['spam_probability'] > 0.5
    assert body['model_f1'] == spam_classifier.metadata['f1']


async def test_predict_ham(client, spam_classifier, headers):
    r = await client.post('/predict', json={'text': 'see you at lunch tomorrow'}, headers=headers)

    assert r.status_code == 200
    assert r.json()['label'] == 'ham'
    assert r.json()['spam_probability'] < 0.5


async def test_predict_rejects_empty_text(client, spam_classifier, headers):
    r = await client.post('/predict', json={'text': ''}, headers=headers)
    assert r.status_code == 422


async def test_predict_requires_api_key(client, spam_classifier):
    r = await client.post('/predict', json={'text': 'hello'})
    assert r.status_code == 401


async def test_predict_rejects_invalid_api_key(client, spam_classifier):
    r = await client.post('/predict', json={'text': 'hello'}, headers={'X-API-Key': 'sk_invalid'})
    assert r.status_code == 401
