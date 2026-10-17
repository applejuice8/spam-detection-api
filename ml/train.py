import kagglehub
from kagglehub import KaggleDatasetAdapter
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score
from sklearn.naive_bayes import BernoulliNB
import joblib
from pathlib import Path
import sklearn
import json


SEED = 42
TEST_SIZE = 0.2
MIN_F1 = 0.90   # Quality gate
LABELS = {'ham': 0, 'spam': 1}

MODEL_DIR = Path('ml/models')
TEST_DIR = Path('ml/test_data')


def load_dataset():
    # https://www.kaggle.com/datasets/uciml/sms-spam-collection-dataset?select=spam.csv
    df = kagglehub.dataset_load(
        KaggleDatasetAdapter.PANDAS,
        'uciml/sms-spam-collection-dataset',
        'spam.csv',
        pandas_kwargs={'encoding': 'latin-1'}
    )
    df = df[['v1', 'v2']].rename(columns={'v1': 'label', 'v2': 'text'})
    return df.drop_duplicates(subset='text')


def split_X_y_train_test(df):
    X = df['text']
    y = df['label'].map(LABELS)

    return train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=SEED
    )


# Param selected from notebook best F1 score
def setup_pipe():
    vectorizer = TfidfVectorizer(
        max_df=0.95,
        min_df=0.001,
        ngram_range=(1, 1),
        stop_words=None,
        binary=False,
        sublinear_tf=True,
        norm=None,
        use_idf=True,
        smooth_idf=False,
        lowercase=True,
        strip_accents=None,
        max_features=None,
    )

    model = BernoulliNB(
        alpha=1.0,
        binarize=0.0,
        fit_prior=False,
    )

    return Pipeline([('vec', vectorizer), ('model', model)])


def save_artifacts(pipe, f1, X_train, X_test, y_test):
    # Create dir
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    # Save model
    joblib.dump(pipe, MODEL_DIR / 'spam_detector.pkl')

    # Save metadata
    metadata = {
        'f1': f1,
        'labels': {str(v): k for k, v in LABELS.items()},   # {'0': 'ham', '1': 'spam'}
        'n_train': len(X_train),
        'sklearn_version': sklearn.__version__,
        'seed': SEED,
    }
    (MODEL_DIR / 'metadata.json').write_text(json.dumps(metadata, indent=2))

    X_test.to_frame('text').assign(label=y_test).to_csv(
        TEST_DIR / 'spam_data.csv', index=False
    )


def train():
    # Load, split data
    df = load_dataset()
    X_train, X_test, y_train, y_test = split_X_y_train_test(df)

    # Fit pipe
    pipe = setup_pipe().fit(X_train, y_train)

    # Gate against low F1 score
    f1 = f1_score(y_test, pipe.predict(X_test))
    print(f'Test F1: {f1:.4f}')
    if f1 < MIN_F1:
        raise SystemExit(f'Quality gate failed: F1 {f1:.3f} < {MIN_F1}')

    # Save
    save_artifacts(pipe, f1, X_train, X_test, y_test)


if __name__ == '__main__':
    train()
