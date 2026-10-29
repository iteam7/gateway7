"""Measure sequential Pipeline.run calls with fixed, in-memory fixtures.

Run ``python -m demo.benchmark --json`` for a machine-readable report.
This is a local microbenchmark, not an HTTP load test or a capacity estimate.
"""

import argparse
import asyncio
from collections.abc import Sequence
import json
import logging
import math
import platform
import sys
import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from gateway7.config import LimitsConfig
from gateway7.loader import LoadedPlugin, LoadedPlugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import API_VERSION, NextHandler, PluginContext, PluginDescriptor


DEFAULT_COUNTS = (0, 1, 3, 8, 16, 32)
DEFAULT_SAMPLES = 200
DEFAULT_WARMUP = 20
DEFAULT_TIMEOUT = 30.0
MAX_TOTAL_REQUESTS = 50_000


class _Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class _Noop:
    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse:
        return await call_next(request)


class _ImmediateProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.response = ChatResponse(text="synthetic benchmark answer", usage=None)

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        return self.response


def _pipeline(count: int) -> tuple[Pipeline, _ImmediateProvider]:
    descriptor = PluginDescriptor("benchmark-noop", API_VERSION, _Settings, lambda _: _Noop())
    instances = {}
    for index in range(count):
        name = f"noop_{index}"
        plugin = _Noop()
        instances[name] = LoadedPlugin(name, descriptor, plugin, plugin.handle, None, None)
    loaded = LoadedPlugins(instances, tuple(instances.values()))
    provider = _ImmediateProvider()
    return Pipeline(loaded, provider, LimitsConfig(), metrics=Metrics()), provider


def _validate_options(
    counts: Sequence[int], samples: int, warmup: int, timeout_seconds: float
) -> None:
    if (
        not 1 <= len(counts) <= 16
        or any(type(count) is not int or not 0 <= count <= 64 for count in counts)
        or len(set(counts)) != len(counts)
    ):
        raise ValueError("counts must contain 1–16 distinct integers from 0 through 64")
    if type(samples) is not int or not 1 <= samples <= 10_000:
        raise ValueError("samples must be an integer from 1 through 10000")
    if type(warmup) is not int or not 0 <= warmup <= 1_000:
        raise ValueError("warmup must be an integer from 0 through 1000")
    if len(counts) * (samples + warmup) > MAX_TOTAL_REQUESTS:
        raise ValueError("all cases together must not exceed 50000 requests including warmup")
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or not 1 <= timeout_seconds <= 300
    ):
        raise ValueError("timeout must be finite and from 1 through 300 seconds")


async def run_benchmark(
    counts: Sequence[int] = DEFAULT_COUNTS,
    *,
    samples: int = DEFAULT_SAMPLES,
    warmup: int = DEFAULT_WARMUP,
    timeout_seconds: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Run bounded fixtures without creating background tasks or opening resources."""
    _validate_options(counts, samples, warmup, timeout_seconds)
    request = ChatRequest(messages=[Message(role="user", content="synthetic benchmark prompt")])
    logger = logging.getLogger("gateway7")
    was_disabled = logger.disabled
    logger.disabled = True
    results = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        async with asyncio.timeout(timeout_seconds):
            for count in counts:
                pipeline, provider = _pipeline(count)
                elapsed_samples = []
                for index in range(warmup + samples):
                    if loop.time() >= deadline:
                        raise TimeoutError
                    before = provider.calls
                    started = time.perf_counter_ns()
                    response = await pipeline.run(request, "benchmark")
                    elapsed = time.perf_counter_ns() - started
                    if provider.calls != before + 1 or response != provider.response:
                        raise RuntimeError("Synthetic pipeline contract failed")
                    if elapsed < 0:
                        raise RuntimeError("Measurement clock moved backwards")
                    if index >= warmup:
                        elapsed_samples.append(elapsed)
                    # Outside each measured interval: allow Ctrl+C and the suite
                    # deadline to run even though the fixed handlers never block.
                    await asyncio.sleep(0)
                if loop.time() >= deadline:
                    raise TimeoutError
                ordered = sorted(elapsed_samples)
                p50 = ordered[math.ceil(samples * 0.50) - 1] / 1_000_000
                p95 = ordered[math.ceil(samples * 0.95) - 1] / 1_000_000
                if not all(math.isfinite(value) and value >= 0 for value in (p50, p95)):
                    raise RuntimeError("Invalid measurement")
                results.append(
                    {
                        "middleware_count": count,
                        "samples": samples,
                        "warmup": warmup,
                        "provider_calls": provider.calls,
                        "measured_provider_calls": provider.calls - warmup,
                        "p50_ms": p50,
                        "p95_ms": p95,
                    }
                )
    finally:
        logger.disabled = was_disabled
    clock = time.get_clock_info("perf_counter")
    return {
        "schema_version": 1,
        "mode": "sequential_in_process_pipeline",
        "metrics_included": True,
        "logging_io_included": False,
        "timeout_seconds": timeout_seconds,
        "percentile_method": "nearest-rank",
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "clock": {
                "name": "time.perf_counter_ns",
                "implementation": clock.implementation,
                "resolution_seconds": clock.resolution,
                "monotonic": clock.monotonic,
            },
        },
        "includes": [
            "Pipeline.run validation, deadline timers and no-op middleware",
            "Immediate in-memory provider with unknown fixture usage",
            "Provider and middleware Prometheus observations",
        ],
        "excludes": [
            "Construction, module loading and startup/shutdown hooks",
            "HTTP, authentication, admission, network and real LLM inference",
            "Log output, harness checks and scheduling between samples",
        ],
        "notes": [
            "Warmup calls are excluded from percentiles but included in provider_calls.",
            "Zero-middleware results are measured directly; no baseline is subtracted.",
            "Local sequential timings do not establish production capacity or monotonic scaling.",
        ],
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="All cases together are limited to 50000 requests, including warmup.",
    )
    parser.add_argument(
        "--counts",
        type=int,
        nargs="+",
        default=DEFAULT_COUNTS,
        help="1–16 distinct middleware counts, each from 0 through 64",
    )
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES, help="Measured requests per case (1–10000)"
    )
    parser.add_argument(
        "--warmup", type=int, default=DEFAULT_WARMUP, help="Unmeasured requests per case (0–1000)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Whole-run time budget in seconds (1–300)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print a JSON report")
    args = parser.parse_args(argv)
    try:
        _validate_options(args.counts, args.samples, args.warmup, args.timeout)
    except ValueError as error:
        parser.error(str(error))
    try:
        report = asyncio.run(
            run_benchmark(
                args.counts, samples=args.samples, warmup=args.warmup, timeout_seconds=args.timeout
            )
        )
        if args.as_json:
            print(json.dumps(report, allow_nan=False))
        else:
            environment = report["environment"]
            print("Gateway7 sequential Pipeline.run microbenchmark (milliseconds)")
            print(
                f"{environment['implementation']} {environment['python']}; "
                f"{environment['system']} {environment['release']} {environment['machine']}"
            )
            clock = environment["clock"]
            print(
                f"Clock: {clock['name']} ({clock['implementation']}); "
                f"resolution={clock['resolution_seconds']}s; monotonic={clock['monotonic']}"
            )
            print("Metrics: included; log I/O: excluded; percentiles: nearest-rank")
            print("middleware  samples  warmup  provider_calls  p50_ms  p95_ms")
            for row in report["results"]:
                print(
                    f"{row['middleware_count']:10d}  {row['samples']:7d}  {row['warmup']:6d}  "
                    f"{row['provider_calls']:14d}  {row['p50_ms']:.6f}  {row['p95_ms']:.6f}"
                )
            for key in ("includes", "excludes", "notes"):
                print(f"{key.capitalize()}: " + "; ".join(report[key]))
        return 0
    except KeyboardInterrupt:
        print("Benchmark interrupted; no complete report produced", file=sys.stderr)
        return 130
    except TimeoutError:
        print("Benchmark exceeded --timeout; no complete report produced", file=sys.stderr)
        return 1
    except Exception:
        print("Benchmark failed; no complete report produced", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
