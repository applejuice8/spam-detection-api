import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ml_model import MODEL_DIR, SpamClassifier
from tests.test_config import settings


def test_threshold_decides_the_label(fake_model_dir):
    text = ['free prize winner claim now call 1']
    proba = SpamClassifier(fake_model_dir).predict(text)[0]['spam_probability']
    assert proba > 0.9

    assert SpamClassifier(fake_model_dir, threshold=0.5).predict(text)[0]['label'] == 'spam'
    assert SpamClassifier(fake_model_dir, threshold=proba).predict(text)[0]['label'] == 'spam'      # At the threshold counts as spam
    assert SpamClassifier(fake_model_dir, threshold=math.nextafter(proba, 2)).predict(text)[0]['label'] == 'ham'


def test_probability_is_unaffected_by_threshold(fake_model_dir):
    text = ['free prize winner claim now call 1']
    a = SpamClassifier(fake_model_dir, threshold=0.2).predict(text)[0]['spam_probability']
    b = SpamClassifier(fake_model_dir, threshold=0.9).predict(text)[0]['spam_probability']
    assert a == b


def test_version_changes_with_threshold(fake_model_dir):
    # Cached predictions carry a label, so a new threshold must not reuse them
    assert SpamClassifier(fake_model_dir, 0.5).version != SpamClassifier(fake_model_dir, 0.7).version
    assert SpamClassifier(fake_model_dir, 0.5).version == SpamClassifier(fake_model_dir, 0.5).version


@pytest.mark.parametrize('value', [0, 1, -0.1, 1.5])
def test_threshold_setting_must_be_between_0_and_1(value):
    with pytest.raises(ValidationError):
        settings(spam_threshold=value)


def test_threshold_setting_defaults_to_half():
    assert settings().spam_threshold == 0.5


def test_model_dir_does_not_depend_on_working_directory():
    assert MODEL_DIR.is_absolute()
    assert MODEL_DIR == Path(__file__).resolve().parent.parent / 'ml' / 'models'


def test_importing_from_another_directory_finds_the_same_model_dir(tmp_path):
    root = Path(__file__).resolve().parent.parent
    out = subprocess.run(
        [sys.executable, '-c', 'from app.ml_model import MODEL_DIR; print(MODEL_DIR)'],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': str(root), 'DATABASE_URI': 'sqlite+aiosqlite://'},
    )
    assert out.stdout.strip() == str(root / 'ml' / 'models'), out.stderr
