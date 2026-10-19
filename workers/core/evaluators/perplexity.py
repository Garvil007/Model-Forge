"""Sliding-window perplexity for a causal LM. Takes a pre-built tokenizer (an object with
an `.encode(text) -> list[int]` method) at construction rather than fetching one — pulling
a tokenizer from an HF repo id is a Phase 4 concern (`workers/ops/import_hf.py`'s domain),
so this evaluator stays testable standalone against a fake tokenizer and a fake runner.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

import numpy as np

from .base import EvalResult, ModelRunnerProtocol

_DEFAULT_WINDOW = 1024
_DEFAULT_STRIDE = 512


class Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...


def _log_softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    return shifted - np.log(np.sum(np.exp(shifted)))


class PerplexityEvaluator:
    def __init__(
        self,
        tokenizer: Tokenizer,
        *,
        window_size: int = _DEFAULT_WINDOW,
        stride: int = _DEFAULT_STRIDE,
    ) -> None:
        if stride <= 0 or stride > window_size:
            raise ValueError("stride must be > 0 and <= window_size")
        self._tokenizer = tokenizer
        self._window_size = window_size
        self._stride = stride

    def evaluate(
        self, runner: ModelRunnerProtocol, loader: Iterable[Any], max_samples: int
    ) -> EvalResult:
        total_nll = 0.0
        total_tokens = 0
        samples_used = 0
        for text in loader:
            if samples_used >= max_samples:
                break
            token_ids = self._tokenizer.encode(text)
            nll, count = self._sequence_nll(runner, token_ids)
            total_nll += nll
            total_tokens += count
            samples_used += 1

        if total_tokens == 0:
            raise ValueError("no tokens were available to evaluate")
        perplexity = float(np.exp(total_nll / total_tokens))
        return EvalResult(
            metric_name="Perplexity", value=perplexity, unit="", samples_used=samples_used
        )

    def _sequence_nll(self, runner: ModelRunnerProtocol, token_ids: list[int]) -> tuple[float, int]:
        """Slides a `window_size`-token window with `stride` overlap, counting each
        target token's negative log-likelihood exactly once (skipping the tokens already
        scored by the previous window, as in the standard HF sliding-window recipe)."""
        length = len(token_ids)
        if length < 2:
            return 0.0, 0

        total_nll = 0.0
        total_tokens = 0
        start = 0
        while start < length - 1:
            end = min(start + self._window_size, length)
            window = token_ids[start:end]
            batch = np.asarray(window, dtype=np.int64)[np.newaxis, :]
            logits = np.asarray(runner.predict(batch))[0]

            first_new = 0 if start == 0 else min(self._stride, len(window) - 1)
            for position in range(first_new, len(window) - 1):
                target = window[position + 1]
                log_probs = _log_softmax(logits[position])
                total_nll += float(-log_probs[target])
                total_tokens += 1

            if end == length:
                break
            start += self._stride

        return total_nll, total_tokens


__all__ = ["PerplexityEvaluator", "Tokenizer"]
