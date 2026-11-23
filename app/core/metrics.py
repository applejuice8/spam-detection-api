from prometheus_client import Counter, Gauge, Histogram


# Metrics the HTTP instrumentator can't know about

# Every prediction served, including ones answered from the cache. Spam share = spam rate / total rate.
PREDICTIONS = Counter(
    'spam_predictions_total',
    'Predictions served, by predicted label',
    ['label']                       # spam, ham
)

# result: hit (found), miss (not found), error
PREDICTION_CACHE = Counter(
    'spam_prediction_cache_total',
    'Prediction cache lookups, by result',
    ['result']
)

# Model only, without HTTP, API key lookup or Redis time. Predictions take milliseconds, so the buckets are small.
MODEL_INFERENCE_SECONDS = Histogram(
    'spam_model_inference_seconds',
    'Time spent in model.predict',
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

# Set once at startup. The version label shows which model is running.
MODEL_F1 = Gauge(
    'spam_model_f1',
    'F1 score of the loaded model, from metadata.json',
    ['model_version']
)

# scope: login, signup, refresh, predict_ip, predict_user
RATE_LIMITED = Counter(
    'rate_limited_total',
    'Requests rejected with 429, by limit',
    ['scope']
)

# reason: missing (no X-API-Key header), invalid (unknown, revoked or expired)
API_KEY_REJECTIONS = Counter(
    'api_key_rejections_total',
    'Requests rejected for a bad API key, by reason',
    ['reason']
)
