import hashlib
import json
import warnings
from pathlib import Path
import joblib
import sklearn


MODEL_DIR = Path('ml/models')
SPAM_CLASS = 1      # Label value for spam, must match LABELS in ml/train.py
SPAM_COLUMN = 1     # Position of class in predict_proba (Sklearn sorts classes ascending)


class SpamClassifier:
    def __init__(self, model_dir: Path = MODEL_DIR):
        self.pipe = joblib.load(model_dir / 'spam_detector.pkl')
        self.metadata = json.loads((model_dir / 'metadata.json').read_text())
        # Changes whenever the model is retrained, so cached predictions from an old model are not reused
        self.version = hashlib.sha256((model_dir / 'spam_detector.pkl').read_bytes()).hexdigest()[:12]
        self.labels = {int(k): v for k, v in self.metadata['labels'].items()}
        assert self.labels[SPAM_CLASS] == 'spam', 'metadata.json label mapping changed'

        # Pickles sensitive to sklearn version
        trained_with = self.metadata['sklearn_version']
        if trained_with != sklearn.__version__:
            warnings.warn(f'Model trained with sklearn {trained_with}, running {sklearn.__version__}')

    def predict(self, texts: list[str]) -> list[dict]:
        probas = self.pipe.predict_proba(texts)[:, SPAM_COLUMN]    # Only keep spam probability
        return [
            {
                'label': self.labels[int(p >= 0.5)],
                'spam_probability': float(p),
            }
            for p in probas
        ]
