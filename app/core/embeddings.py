from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
from typing import List
import numpy as np

_model = SentenceTransformer("all-mpnet-base-v2")


def embed_text(text: str) -> np.ndarray:
    return _model.encode(text, convert_to_numpy=True)


def embed_batch(texts: List[str]) -> np.ndarray:
    return _model.encode(texts, convert_to_numpy=True)


def similarity(text_a: str, text_b: str) -> float:
    emb_a = embed_text(text_a)
    emb_b = embed_text(text_b)
    return float(cos_sim(emb_a, emb_b)[0][0])