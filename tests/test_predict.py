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


async def test_predict_second_call_comes_from_cache(client, spam_classifier, headers):
    body = {'text': 'free prize winner claim now'}
    first = await client.post('/predict', json=body, headers=headers)
    second = await client.post('/predict', json=body, headers=headers)

    assert first.json()['from_cache'] is False
    assert second.json()['from_cache'] is True
    assert second.json()['label'] == first.json()['label']
    assert second.json()['spam_probability'] == first.json()['spam_probability']
    assert second.json()['model_f1'] == spam_classifier.metadata['f1']


async def test_predict_cache_key_does_not_contain_raw_text(client, spam_classifier, fake_redis, headers):
    await client.post('/predict', json={'text': 'free prize winner claim now'}, headers=headers)

    assert len(fake_redis.data) == 1
    assert 'prize' not in next(iter(fake_redis.data))


async def test_predict_still_works_when_redis_is_down(client, spam_classifier, broken_redis, headers):
    r = await client.post('/predict', json={'text': 'free prize winner claim now'}, headers=headers)

    assert r.status_code == 200
    assert r.json()['label'] == 'spam'
    assert r.json()['from_cache'] is False


# ---------- Redis failures ----------
async def test_down_redis_is_skipped_after_the_first_failure(client, spam_classifier, broken_redis, headers):
    for _ in range(5):
        r = await client.post('/predict', json={'text': 'free prize winner claim now'}, headers=headers)
        assert r.status_code == 200

    # One failed get trips the breaker. The other four requests never touch Redis.
    assert broken_redis.calls == 1


async def test_redis_is_retried_after_the_cooldown(client, spam_classifier, fake_redis, headers):
    from app.main import app

    now = [1000.0]
    app.state.cache._clock = lambda: now[0]
    fake_redis.broken = True
    await client.post('/predict', json={'text': 'free prize'}, headers=headers)
    calls_after_failure = fake_redis.calls

    fake_redis.broken = False
    now[0] += 5                     # Still cooling down
    await client.post('/predict', json={'text': 'free prize'}, headers=headers)
    assert fake_redis.calls == calls_after_failure

    now[0] += 60                    # Cooldown over, Redis is used again
    first = await client.post('/predict', json={'text': 'free prize'}, headers=headers)
    second = await client.post('/predict', json={'text': 'free prize'}, headers=headers)
    assert first.json()['from_cache'] is False
    assert second.json()['from_cache'] is True


@pytest.mark.parametrize('garbage', ['not json', '{"label": "spam"}', '[]', '"spam"', '{"label": 1, "spam_probability": "x"}'])
async def test_unreadable_cache_entry_is_treated_as_a_miss(client, spam_classifier, fake_redis, headers, garbage):
    from app.predict.router import cache_key

    text = 'free prize winner claim now'
    fake_redis.data[cache_key(text, spam_classifier.version)] = garbage

    r = await client.post('/predict', json={'text': text}, headers=headers)
    assert r.status_code == 200
    assert r.json()['label'] == 'spam'
    assert r.json()['from_cache'] is False
    # And the bad entry is replaced by a good one
    assert (await client.post('/predict', json={'text': text}, headers=headers)).json()['from_cache'] is True
