"""metis_app.utils.brain_metrics — Coherence metrics for Tribev2 activity.

Tribev2's native pipeline returns a ``(timesteps, vertex_count)`` tensor of
predicted brain-region activity per document.  This module scores that tensor
along several axes — causal-closure, algebraic connectivity, complexity and
synchrony — and combines them into a single ``c_score`` suitable for comparing
documents, indices, or query traces.

Derived from the consciousness-metric framework in
`4R7I5T/CL1_LLM_Encoder/consciousness.py`, adapted to Tribev2 activation
tensors and stripped of the Izhikevich-substrate-specific scaffolding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Low-level metric helpers
# ---------------------------------------------------------------------------


def _prepare(activity: np.ndarray,
             downsample: int = 1,
             max_channels: int = 64) -> np.ndarray:
    """Validate, down-sample and channel-cap the activity tensor.

    Input shape: ``(V, T)`` — channels on axis 0, time on axis 1.
    Output is a ``float32`` array with possibly fewer rows and columns.
    """
    arr = np.asarray(activity, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[np.newaxis, :]
    if arr.ndim != 2 or arr.size == 0:
        return np.zeros((0, 0), dtype=np.float32)

    if arr.shape[0] > max_channels:
        # Sample evenly so we keep spatial coverage instead of the first N.
        idx = np.linspace(0, arr.shape[0] - 1, max_channels).astype(int)
        arr = arr[idx, :]

    if downsample > 1 and arr.shape[1] > downsample:
        # Block-mean along time to keep structure but shrink the work.
        t = arr.shape[1] - (arr.shape[1] % downsample)
        arr = arr[:, :t].reshape(arr.shape[0], -1, downsample).mean(axis=2)

    return arr


def _binarise(activity: np.ndarray) -> np.ndarray:
    """Threshold each channel at its mean → boolean spike-like matrix."""
    if activity.size == 0:
        return np.zeros_like(activity, dtype=np.bool_)
    means = activity.mean(axis=1, keepdims=True)
    return activity > means


def _granger_proxy(activity: np.ndarray, lag: int = 1) -> np.ndarray:
    """Cheap pairwise Granger-causality proxy.

    Full Granger is expensive; for a coherence signal we only need a
    directed adjacency whose off-diagonal mass reflects predictive
    influence.  For each pair ``(i, j)`` we compute the reduction in
    residual variance when predicting ``x_j[t]`` from ``x_i[t-lag]``
    versus its own past.  Returns a ``(V, V)`` non-negative matrix.
    """
    v, t = activity.shape
    if v < 2 or t <= lag + 1:
        return np.zeros((v, v), dtype=np.float32)

    past_self = activity[:, :-lag]
    future = activity[:, lag:]
    own_var = future.var(axis=1) + 1e-9

    # Correlation between x_i past and x_j future.
    p_mean = past_self.mean(axis=1, keepdims=True)
    f_mean = future.mean(axis=1, keepdims=True)
    p_c = past_self - p_mean
    f_c = future - f_mean
    p_std = p_c.std(axis=1) + 1e-9
    f_std = f_c.std(axis=1) + 1e-9
    corr = (p_c @ f_c.T) / (past_self.shape[1] * np.outer(p_std, f_std))
    # Explained variance from cross prediction; clamp negatives to 0.
    explained = (corr ** 2) * f_std[np.newaxis, :] ** 2
    gain = np.clip(explained / own_var[np.newaxis, :], 0.0, 1.0)
    np.fill_diagonal(gain, 0.0)
    return gain.astype(np.float32)


def _closure(weights: np.ndarray) -> float:
    """Internal-causal-weight fraction of the graph.

    Self-loops are zeroed; closure is the ratio of weight mass that
    contributes to a strongly-connected interior vs. leaving the graph.
    Here we approximate "interior" as the diagonal-symmetric part.
    """
    if weights.size == 0:
        return 0.0
    total = float(weights.sum())
    if total <= 0.0:
        return 0.0
    internal = float(np.minimum(weights, weights.T).sum())
    return max(0.0, min(1.0, internal / total))


def _fiedler_norm(weights: np.ndarray) -> float:
    """Normalised algebraic connectivity (λ₂) of the symmetrised graph."""
    v = weights.shape[0]
    if v < 2:
        return 0.0
    sym = 0.5 * (weights + weights.T)
    degree = np.diag(sym.sum(axis=1))
    laplacian = degree - sym
    try:
        eigvals = np.linalg.eigvalsh(laplacian.astype(np.float64))
    except np.linalg.LinAlgError:
        return 0.0
    eigvals = np.sort(eigvals)
    if eigvals.size < 2:
        return 0.0
    lambda_max = float(eigvals[-1])
    if lambda_max <= 0.0:
        return 0.0
    return max(0.0, min(1.0, float(eigvals[1]) / lambda_max))


def _self_model_fraction(activity: np.ndarray) -> float:
    """Mutual information between each unit and the first principal
    component of the population, averaged and normalised.

    Approximates ``1 − H(unit | PC1) / H(unit)`` via binned MI.
    """
    v, t = activity.shape
    if v < 2 or t < 8:
        return 0.0
    centred = activity - activity.mean(axis=1, keepdims=True)
    # Power iteration for the top PC — cheap and dependency-free.
    rng = np.random.default_rng(0)
    vec = rng.standard_normal(v).astype(np.float32)
    vec /= np.linalg.norm(vec) + 1e-9
    cov = centred @ centred.T / max(1, t - 1)
    for _ in range(16):
        vec = cov @ vec
        n = np.linalg.norm(vec)
        if n == 0:
            return 0.0
        vec /= n
    pc1 = vec @ centred  # shape (T,)

    # Bin both unit and PC1 into 4 quantile bins.
    def _bin(x: np.ndarray) -> np.ndarray:
        qs = np.quantile(x, [0.25, 0.5, 0.75])
        return np.digitize(x, qs)

    pc_bin = _bin(pc1)
    scores = []
    for row in activity:
        unit_bin = _bin(row)
        hx = _entropy(np.bincount(unit_bin, minlength=4) / len(unit_bin))
        if hx <= 0:
            continue
        joint = np.zeros((4, 4), dtype=np.float64)
        for u, p in zip(unit_bin, pc_bin):
            joint[u, p] += 1.0
        joint /= joint.sum() + 1e-12
        hxy = _entropy(joint.flatten())
        hy = _entropy(joint.sum(axis=0))
        mi = max(0.0, hx + hy - hxy)
        scores.append(mi / hx)
    if not scores:
        return 0.0
    return max(0.0, min(1.0, float(np.mean(scores))))


def _entropy(probs: np.ndarray) -> float:
    p = np.clip(probs, 1e-12, 1.0)
    return float(-(p * np.log2(p)).sum())


def _lz_complexity(binary: np.ndarray) -> float:
    """Normalised Lempel–Ziv complexity over a concatenated spike train."""
    if binary.size == 0:
        return 0.0
    s = "".join("1" if b else "0" for b in binary.flatten())
    n = len(s)
    if n == 0:
        return 0.0
    i = 0
    c = 1
    k = 1
    kmax = 1
    while i + k < n:
        if s[i:i + k] == s[i + k:i + 2 * k] if i + 2 * k <= n else False:
            k += 1
        else:
            if k > kmax:
                kmax = k
            i += max(1, k)
            c += 1
            k = 1
    # Normalise against the i.i.d. upper bound n / log2(n).
    norm = n / np.log2(max(n, 2))
    return max(0.0, min(1.0, c / norm if norm > 0 else 0.0))


def _channel_entropy(activity: np.ndarray) -> float:
    if activity.size == 0:
        return 0.0
    power = np.abs(activity).sum(axis=1)
    total = power.sum()
    if total <= 0:
        return 0.0
    p = power / total
    ent = _entropy(p)
    max_ent = np.log2(activity.shape[0]) if activity.shape[0] > 1 else 1.0
    return float(ent / max_ent) if max_ent > 0 else 0.0


def _synchrony(binary: np.ndarray) -> float:
    if binary.size == 0:
        return 0.0
    co_active = binary.sum(axis=0) / max(1, binary.shape[0])
    # Synchrony ≈ fraction of time bins where >50% of channels fire together.
    return float((co_active >= 0.5).mean())


def _mean_transfer_entropy(binary: np.ndarray, max_pairs: int = 64) -> float:
    v, t = binary.shape
    if v < 2 or t < 8:
        return 0.0
    rng = np.random.default_rng(0)
    # Sample directed pairs to keep this O(max_pairs), not O(V^2).
    pairs = []
    for _ in range(max_pairs):
        i, j = int(rng.integers(v)), int(rng.integers(v))
        if i != j:
            pairs.append((i, j))
    if not pairs:
        return 0.0
    vals = []
    for i, j in pairs:
        te = _transfer_entropy_pair(binary[i], binary[j])
        vals.append(te)
    return float(np.mean(vals)) if vals else 0.0


def _transfer_entropy_pair(src: np.ndarray, dst: np.ndarray) -> float:
    # TE(src -> dst) = H(dst_t | dst_{t-1}) - H(dst_t | dst_{t-1}, src_{t-1})
    if src.size < 3:
        return 0.0
    s = src.astype(np.int8)
    d = dst.astype(np.int8)
    dst_t = d[1:]
    dst_p = d[:-1]
    src_p = s[:-1]
    # Joint counts.
    joint3 = np.zeros((2, 2, 2), dtype=np.float64)
    for a, b, c in zip(dst_t, dst_p, src_p):
        joint3[a, b, c] += 1.0
    joint3 /= joint3.sum() + 1e-12
    joint_dd = joint3.sum(axis=2)
    joint_dp_sp = joint3.sum(axis=0)
    joint_dp = joint_dd.sum(axis=0)

    te = 0.0
    for a in range(2):
        for b in range(2):
            for c in range(2):
                p_abc = joint3[a, b, c]
                if p_abc <= 0:
                    continue
                p_bc = joint_dp_sp[b, c]
                p_ab = joint_dd[a, b]
                p_b = joint_dp[b]
                if p_bc <= 0 or p_ab <= 0 or p_b <= 0:
                    continue
                te += p_abc * np.log2((p_abc * p_b) / (p_bc * p_ab))
    return max(0.0, float(te))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_coherence(
    activity: np.ndarray,
    *,
    downsample: int = 1,
    max_channels: int = 64,
) -> dict[str, float]:
    """Score a Tribev2-style ``(V, T)`` activity tensor.

    Returns a dict with:

    - ``c_score`` — geometric mean of closure, λ₂_norm and ρ (0-1)
    - ``closure``
    - ``lambda2_norm``
    - ``rho``
    - ``lz_complexity``
    - ``channel_entropy``
    - ``synchrony``
    - ``mean_transfer_entropy``
    - ``mean_firing_rate``
    - ``active_channels`` (count, not fraction)
    """
    arr = _prepare(activity, downsample=downsample, max_channels=max_channels)
    if arr.size == 0:
        return _zero_metrics()

    binary = _binarise(arr)
    gran = _granger_proxy(arr)
    closure = _closure(gran)
    l2 = _fiedler_norm(gran)
    rho = _self_model_fraction(arr)
    c_score = float(np.cbrt(max(0.0, closure) * max(0.0, l2) * max(0.0, rho)))

    return {
        "c_score": c_score,
        "closure": closure,
        "lambda2_norm": l2,
        "rho": rho,
        "lz_complexity": _lz_complexity(binary),
        "channel_entropy": _channel_entropy(arr),
        "synchrony": _synchrony(binary),
        "mean_transfer_entropy": _mean_transfer_entropy(binary),
        "mean_firing_rate": float(binary.mean()),
        "active_channels": int((binary.sum(axis=1) > 0).sum()),
    }


def _zero_metrics() -> dict[str, float]:
    return {
        "c_score": 0.0,
        "closure": 0.0,
        "lambda2_norm": 0.0,
        "rho": 0.0,
        "lz_complexity": 0.0,
        "channel_entropy": 0.0,
        "synchrony": 0.0,
        "mean_transfer_entropy": 0.0,
        "mean_firing_rate": 0.0,
        "active_channels": 0,
    }


# ---------------------------------------------------------------------------
# Streaming assessor (keeps a rolling window for repeated scoring)
# ---------------------------------------------------------------------------


@dataclass
class CoherenceAssessor:
    window: int = 256
    downsample: int = 1
    max_channels: int = 64
    _buffer: list[np.ndarray] = field(default_factory=list)

    def push(self, frame: np.ndarray) -> None:
        """Append a ``(V,)`` or ``(V, k)`` activity slice."""
        f = np.asarray(frame, dtype=np.float32)
        if f.ndim == 1:
            f = f[:, np.newaxis]
        self._buffer.append(f)
        # Trim based on total time width.
        total_t = sum(x.shape[1] for x in self._buffer)
        while total_t > self.window and self._buffer:
            head = self._buffer[0]
            if head.shape[1] <= total_t - self.window:
                total_t -= head.shape[1]
                self._buffer.pop(0)
            else:
                drop = total_t - self.window
                self._buffer[0] = head[:, drop:]
                total_t -= drop

    def score(self) -> dict[str, Any]:
        if not self._buffer:
            return _zero_metrics()
        activity = np.concatenate(self._buffer, axis=1)
        return compute_coherence(
            activity,
            downsample=self.downsample,
            max_channels=self.max_channels,
        )
