import json

import joblib
import pandas as pd
import pytest
from sklearn.metrics import f1_score

from ml import train as train_module
from ml.train import (
    LABELS,
    MIN_F1,
    setup_pipe,
    split_X_y_train_test,
    train,
)

MODEL_PATH = train_module.MODEL_DIR / 'spam_detector.pkl'
META_PATH = train_module.MODEL_DIR / 'metadata.json'
TEST_DATA_PATH = train_module.TEST_DIR / 'spam_data.csv'

needs_artifacts = pytest.mark.skipif(
    not MODEL_PATH.exists(), reason='run `python -m ml.train` first'
)


@pytest.fixture
def tiny_df():
    # Small fake dataset, so tests don't need the network
    spam = [f'free prize winner claim now call {i}' for i in range(40)]
    ham = [f'see you at lunch tomorrow ok {i}' for i in range(40)]
    return pd.DataFrame({
        'text': spam + ham,
        'label': ['spam'] * 40 + ['ham'] * 40,
    })


@pytest.fixture
def tmp_artifacts(tmp_path, monkeypatch):
    # Redirect train() output to a temp folder, so the real model is never touched
    monkeypatch.setattr(train_module, 'MODEL_DIR', tmp_path / 'models')
    monkeypatch.setattr(train_module, 'TEST_DIR', tmp_path / 'test_data')
    return tmp_path


# ---------- Data ----------
def test_split_is_stratified_and_reproducible(tiny_df):
    X_train, X_test, y_train, y_test = split_X_y_train_test(tiny_df)
    X_train2, _, _, _ = split_X_y_train_test(tiny_df)

    assert len(X_train) + len(X_test) == len(tiny_df)
    assert set(y_train) == {0, 1}
    assert y_test.mean() == pytest.approx(0.5)
    assert list(X_train.index) == list(X_train2.index)


def test_no_overlap_between_train_and_test(tiny_df):
    X_train, X_test, _, _ = split_X_y_train_test(tiny_df)
    assert set(X_train).isdisjoint(set(X_test))


# ---------- Pipeline ----------
def test_pipeline_has_vec_and_model_steps():
    # Guards against saving a bare model without its vectorizer
    assert list(setup_pipe().named_steps) == ['vec', 'model']


def test_pipeline_predicts_raw_text(tiny_df):
    X_train, _, y_train, _ = split_X_y_train_test(tiny_df)
    pipe = setup_pipe().fit(X_train, y_train)

    proba = pipe.predict_proba(['free prize winner'])
    assert proba.shape == (1, 2)
    assert proba.sum() == pytest.approx(1.0)


# ---------- train() end to end, with fake data and a temp folder ----------
def test_train_saves_artifacts(tiny_df, tmp_artifacts, monkeypatch):
    monkeypatch.setattr(train_module, 'load_dataset', lambda: tiny_df)

    train()

    assert (tmp_artifacts / 'models' / 'spam_detector.pkl').exists()
    assert (tmp_artifacts / 'models' / 'metadata.json').exists()
    assert (tmp_artifacts / 'test_data' / 'spam_data.csv').exists()


def test_quality_gate_blocks_bad_model(tiny_df, tmp_artifacts, monkeypatch):
    # Shuffled labels means nothing to learn, so the gate should fail
    bad_df = tiny_df.assign(
        label=tiny_df['label'].sample(frac=1, random_state=0).values
    )
    monkeypatch.setattr(train_module, 'load_dataset', lambda: bad_df)
    monkeypatch.setattr(train_module, 'MIN_F1', 0.99)

    with pytest.raises(SystemExit):
        train()
    assert not (tmp_artifacts / 'models' / 'spam_detector.pkl').exists()


# ---------- The real saved model (run `python -m ml.train` first) ----------
@needs_artifacts
def test_saved_model_meets_quality_bar():
    pipe = joblib.load(MODEL_PATH)
    df = pd.read_csv(TEST_DATA_PATH)

    f1 = f1_score(df['label'], pipe.predict(df['text']))
    assert f1 >= MIN_F1


@needs_artifacts
def test_saved_model_obvious_cases():
    pipe = joblib.load(MODEL_PATH)

    assert pipe.predict(['WINNER!! Claim your free prize now, call 09061701461'])[0] == LABELS['spam']
    assert pipe.predict(['Ok, see you at lunch tomorrow'])[0] == LABELS['ham']


@needs_artifacts
def test_metadata_has_label_mapping():
    meta = json.loads(META_PATH.read_text())

    assert meta['labels'] == {'0': 'ham', '1': 'spam'}
    assert 'f1' in meta
    assert 'sklearn_version' in meta