"""core.similarity: cosine similarity, max difference, top-1 agreement, NCHW/NHWC alignment."""

from __future__ import annotations

import numpy as np

from core.similarity import compare_arrays, compare_runs


def test_identical_arrays_are_perfectly_similar() -> None:
    rng = np.random.default_rng(0)
    original = rng.standard_normal((4, 10)).astype(np.float32)

    metrics = compare_arrays(original, original.copy())

    assert metrics["Output similarity"] == "1.0000"
    assert float(metrics["Max difference"]) == 0.0
    assert metrics["Top-1 agreement"] == "1.0000"


def test_small_perturbation_still_scores_high_similarity() -> None:
    rng = np.random.default_rng(0)
    original = rng.standard_normal((4, 10)).astype(np.float32)
    result = original + rng.normal(scale=0.001, size=original.shape).astype(np.float32)

    metrics = compare_arrays(original, result)

    assert float(metrics["Output similarity"]) > 0.999
    assert float(metrics["Max difference"]) < 0.01


def test_opposite_vectors_score_negative_similarity() -> None:
    original = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    result = -original

    metrics = compare_arrays(original, result)

    assert float(metrics["Output similarity"]) == -1.0


def test_top1_agreement_counts_argmax_matches() -> None:
    original = np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.7]], dtype=np.float32)
    result = np.array([[0.2, 0.8], [0.1, 0.9], [0.6, 0.4]], dtype=np.float32)  # only row 0 agrees

    metrics = compare_arrays(original, result)

    assert metrics["Top-1 agreement"] == f"{1 / 3:.4f}"


def test_aligns_nchw_against_nhwc_before_comparing() -> None:
    rng = np.random.default_rng(0)
    nchw = rng.standard_normal((1, 3, 8, 8)).astype(np.float32)
    nhwc = np.transpose(nchw, (0, 2, 3, 1))

    metrics = compare_arrays(nchw, nhwc)

    assert metrics["Output similarity"] == "1.0000"
    assert float(metrics["Max difference"]) == 0.0


def test_true_shape_mismatch_is_reported_not_measured() -> None:
    original = np.zeros((1, 4), dtype=np.float32)
    result = np.zeros((1, 5), dtype=np.float32)

    metrics = compare_arrays(original, result)

    assert "not measured" in metrics["Output similarity"]
    assert "shape mismatch" in metrics["Output similarity"]


def test_compare_runs_degrades_to_not_measured_on_failure() -> None:
    def _boom(_feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        raise RuntimeError("synthetic failure")

    metrics = compare_runs(_boom, _boom, {"x": np.zeros(1)})

    assert "not measured" in metrics["Output similarity"]
    assert "comparison failed" in metrics["Output similarity"]


def test_compare_runs_calls_both_callables_with_same_feeds() -> None:
    feeds = {"x": np.array([1.0, 2.0, 3.0], dtype=np.float32)}
    seen: list[dict[str, np.ndarray]] = []

    def _run(f: dict[str, np.ndarray]) -> list[np.ndarray]:
        seen.append(f)
        return [f["x"] * 2]

    metrics = compare_runs(_run, _run, feeds)

    assert len(seen) == 2
    assert metrics["Output similarity"] == "1.0000"
