from fastapi import Request, Depends
from app.ml_model import SpamClassifier
from typing import Annotated


def get_spam_classifier(req: Request) -> SpamClassifier:
    return req.app.state.spam_classifier


SpamClassifierDep = Annotated[SpamClassifier, Depends(get_spam_classifier)]
