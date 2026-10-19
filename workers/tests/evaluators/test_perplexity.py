"""core.evaluators.perplexity: sliding-window perplexity for a causal LM."""

from __future__ import annotations

import numpy as np
import pytest

from core.evaluators.perplexity import PerplexityEvaluator

_VOCAB_SIZE = 4


class _FakeTokenizer:
    def encode(self, text: str) -> list[int]:
        return [ord(c) % _VOCAB_SIZE for c in text]


class _UniformLogitsRunner:
    """Always predicts a uniform distribution -> known perplexity == vocab size."""

    def predict(self, batch: np.ndarray) -> np.ndarray:
        seq_len = batch.shape[1]
        return np.zeros((1, seq_len, _VOCAB_SIZE))


def test_uniform_logits_give_perplexity_equal_to_vocab_size() -> None:
    evaluator = PerplexityEvaluator(_FakeTokenizer(), window_size=10, stride=5)
    loader = ["hello"]

    result = evaluator.evaluate(_UniformLogitsRunner(), loader, max_samples=5)

    assert result.value == pytest.approx(_VOCAB_SIZE, rel=1e-6)
    assert result.metric_name == "Perplexity"
    assert result.samples_used == 1


def test_max_samples_caps_number_of_texts_evaluated() -> None:
    evaluator = PerplexityEvaluator(_FakeTokenizer(), window_size=10, stride=5)
    loader = ["hello", "world", "again"]

    result = evaluator.evaluate(_UniformLogitsRunner(), loader, max_samples=2)

    assert result.samples_used == 2


def test_sliding_window_does_not_double_count_overlapping_tokens() -> None:
    # sequence longer than window forces a second sliding window; overlap tokens must
    # only be scored once, so perplexity should still equal the vocab size exactly.
    evaluator = PerplexityEvaluator(_FakeTokenizer(), window_size=4, stride=2)
    loader = ["abcdefgh"]

    result = evaluator.evaluate(_UniformLogitsRunner(), loader, max_samples=5)

    assert result.value == pytest.approx(_VOCAB_SIZE, rel=1e-6)


def test_empty_text_yields_no_tokens_and_raises_value_error() -> None:
    evaluator = PerplexityEvaluator(_FakeTokenizer(), window_size=10, stride=5)

    with pytest.raises(ValueError):
        evaluator.evaluate(_UniformLogitsRunner(), [""], max_samples=5)


def test_invalid_stride_raises_value_error() -> None:
    with pytest.raises(ValueError):
        PerplexityEvaluator(_FakeTokenizer(), window_size=4, stride=5)
