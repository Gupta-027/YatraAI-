"""Embedding provider abstraction.

Two implementations:

``HashingEmbedder`` (default)
    A signed feature-hashing projection of word unigrams, bigrams and character
    4-grams into a fixed-dimension unit vector. Deterministic, dependency-free
    and fast, so ``pip install`` stays under a minute and CI needs no model
    download. It captures lexical similarity well; paired with the full-text
    arm of hybrid retrieval it is a genuinely usable retriever - see
    ``evaluation/reports/rag_evaluation.md`` for measured precision on both
    providers.

``SentenceTransformerEmbedder``
    Real dense semantic embeddings. Enabled with
    ``EMBEDDING_PROVIDER=sentence-transformers`` after
    ``pip install -e ".[embeddings]"``. Falls back to hashing (loudly) when the
    optional dependency is missing so the demo never hard-fails.
"""

from __future__ import annotations

import functools
import hashlib
import itertools
import math
import re
from abc import ABC, abstractmethod
from collections import Counter

from yatraai.config import get_settings
from yatraai.core.telemetry import track
from yatraai.logging_config import get_logger

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Small, hand-picked stop list. Deliberately short: travel questions are terse and
# over-aggressive filtering hurts recall ("what to wear" -> "wear").
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "but",
        "if",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "without",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "as",
        "we",
        "you",
        "i",
        "they",
        "he",
        "she",
        "them",
        "us",
        "our",
        "your",
        "their",
        "there",
        "here",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "can",
        "could",
        "should",
        "would",
        "may",
        "might",
        "will",
        "shall",
        "about",
        "into",
        "over",
        "under",
        "than",
        "then",
        "so",
        "such",
        "very",
        "more",
        "most",
        "some",
        "any",
        "each",
        "which",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "why",
        "how",
    ]
)


def tokenize(text: str) -> list[str]:
    return [
        t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 1 and t not in _STOPWORDS
    ]


class Embedder(ABC):
    provider_name: str = "base"
    model_name: str = "base"
    dim: int = 384

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashingEmbedder(Embedder):
    provider_name = "hashing"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.model_name = f"signed-feature-hash-{dim}"

    # -- feature extraction -------------------------------------------------
    @staticmethod
    def _features(text: str) -> Counter[str]:
        tokens = tokenize(text)
        feats: Counter[str] = Counter()
        for tok in tokens:
            feats[f"w:{tok}"] += 1
        for a, b in itertools.pairwise(tokens):
            feats[f"b:{a}_{b}"] += 1
        # Character 4-grams give partial-match robustness (e.g. "temple"/"temples").
        joined = " ".join(tokens)
        for i in range(len(joined) - 3):
            gram = joined[i : i + 4]
            if " " not in gram:
                feats[f"c:{gram}"] += 1
        return feats

    def _hash_index(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dim, 1.0 if (value >> 63) & 1 else -1.0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with track("embeddings", self.provider_name, "embed_documents"):
            return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        feats = self._features(text)
        for feature, count in feats.items():
            idx, sign = self._hash_index(feature)
            # Sublinear TF damps repeated tokens, exactly like tf-idf's 1+log(tf).
            weight = 1.0 + math.log(count)
            # Character grams are noisier than words - down-weight them.
            if feature.startswith("c:"):
                weight *= 0.35
            elif feature.startswith("b:"):
                weight *= 0.85
            vector[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]


class SentenceTransformerEmbedder(Embedder):
    provider_name = "sentence-transformers"

    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension() or dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with track("embeddings", self.provider_name, "embed_documents"):
            vectors = self._model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True
            )
            return [v.tolist() for v in vectors]


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "sentence-transformers":
        try:
            embedder = SentenceTransformerEmbedder(s.embedding_model, s.embedding_dim)
            log.info(
                "embeddings.provider", provider=embedder.provider_name, model=embedder.model_name
            )
            return embedder
        except Exception as exc:
            log.warning(
                "embeddings.fallback",
                requested="sentence-transformers",
                error=str(exc),
                hint='install with: pip install -e ".[embeddings]"',
            )
    return HashingEmbedder(s.embedding_dim)


def reset_embedder_cache() -> None:
    get_embedder.cache_clear()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
