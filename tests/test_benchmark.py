"""Check the benchmark contract, never the speed of the machine running it."""

import asyncio
import json
import logging
import math
import os
from pathlib import Path
import signal
import sys

import httpx
import pytest

from demo import benchmark


async def test_actual_pipeline_executes_same_task_noops_and_one_provider_per_request(monkeypatch):
    visits = []
    pipelines = []
    task = asyncio.current_task()
    original = benchmark._Noop.handle
    original_pipeline = benchmark._pipeline

    def capture_pipeline(count):
        pipeline, provider = original_pipeline(count)
        pipelines.append(pipeline)
        return pipeline, provider

    async def observed(self, request, context, call_next):
        visits.append((context.instance_name, asyncio.current_task()))
        return await original(self, request, context, call_next)

    def forbidden_http(*args, **kwargs):
        raise AssertionError("The benchmark must not create an HTTP client")

    logger = logging.getLogger("gateway7")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "handle", forbidden_http)
    monkeypatch.setattr(benchmark, "_pipeline", capture_pipeline)
    monkeypatch.setattr(benchmark._Noop, "handle", observed)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden_http)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-private-benchmark-value")
    before_tasks = asyncio.all_tasks()
    report = await benchmark.run_benchmark(samples=2, warmup=1)
    assert logger.disabled is False
    assert asyncio.all_tasks() == before_tasks
    assert benchmark.DEFAULT_COUNTS == (0, 1, 3, 8, 16, 32)
    assert [row["middleware_count"] for row in report["results"]] == list(benchmark.DEFAULT_COUNTS)
    assert len(visits) == sum(benchmark.DEFAULT_COUNTS) * 3
    assert all(owner is task for _, owner in visits)
    for pipeline in pipelines:
        assert (
            pipeline.metrics.registry.get_sample_value(
                "gateway7_provider_calls_total", {"provider": "fake", "outcome": "complete"}
            )
            == 3
        )
        for name in pipeline.plugins.instances:
            assert (
                pipeline.metrics.registry.get_sample_value(
                    "gateway7_middleware_steps_total",
                    {"middleware": name, "phase": "response", "outcome": "complete"},
                )
                == 3
            )
    for row in report["results"]:
        assert row["samples"] == 2 and row["warmup"] == 1
        assert row["provider_calls"] == 3 and row["measured_provider_calls"] == 2
        assert all(math.isfinite(row[key]) and row[key] >= 0 for key in ("p50_ms", "p95_ms"))
        assert row["p50_ms"] <= row["p95_ms"]
    assert report["mode"] == "sequential_in_process_pipeline"
    assert report["metrics_included"] is True and report["logging_io_included"] is False
    assert report["percentile_method"] == "nearest-rank"
    assert set(report["environment"]) == {
        "python",
        "implementation",
        "system",
        "release",
        "machine",
        "clock",
    }
    assert report["environment"]["clock"]["monotonic"] is True
    assert "synthetic-private-benchmark-value" not in json.dumps(report, allow_nan=False)
    assert report["includes"] and report["excludes"] and report["notes"]


async def test_upper_chain_bound_and_no_warmup_produce_a_complete_measurement():
    report = await benchmark.run_benchmark((64,), samples=1, warmup=0)
    row = report["results"][0]
    assert row["middleware_count"] == 64 and row["provider_calls"] == 1
    assert row["samples"] == row["measured_provider_calls"] == 1
    assert row["warmup"] == 0


@pytest.mark.parametrize(
    "options",
    [
        {"counts": ()},
        {"counts": (0, 0)},
        {"counts": (-1,)},
        {"counts": (65,)},
        {"counts": (True,)},
        {"counts": tuple(range(17))},
        {"samples": 0},
        {"samples": True},
        {"samples": 10001},
        {"warmup": -1},
        {"warmup": 1001},
        {"warmup": 1.5},
        {"timeout_seconds": 0},
        {"timeout_seconds": 301},
        {"timeout_seconds": True},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"counts": tuple(range(6)), "samples": 10000, "warmup": 0},
    ],
)
async def test_invalid_or_excessive_work_is_rejected_before_construction(monkeypatch, options):
    def forbidden_pipeline(_):
        raise AssertionError("Invalid options must not start work")

    monkeypatch.setattr(benchmark, "_pipeline", forbidden_pipeline)
    with pytest.raises(ValueError):
        await benchmark.run_benchmark(**options)


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_reports_complete_human_or_json_output(capsys, as_json):
    args = ["--counts", "0", "1", "--samples", "2", "--warmup", "1"]
    if as_json:
        args.append("--json")
    assert benchmark.main(args) == 0
    output = capsys.readouterr()
    assert output.err == ""
    if as_json:
        report = json.loads(output.out)
        assert report["schema_version"] == 1
        assert [row["provider_calls"] for row in report["results"]] == [3, 3]
    else:
        assert "p50_ms" in output.out and "p95_ms" in output.out
        assert "samples" in output.out and "warmup" in output.out
        assert "Metrics: included; log I/O: excluded" in output.out
        assert "Clock:" in output.out and "Excludes:" in output.out
        assert "no baseline is subtracted" in output.out


def test_cli_rejects_invalid_options_with_argument_error(capsys):
    with pytest.raises(SystemExit) as error:
        benchmark.main(["--samples", "0", "--json"])
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("failure", ["zero_calls", "two_calls", "unexpected"])
def test_wrong_call_counts_or_runtime_failure_never_emit_a_success_report(
    monkeypatch, capsys, failure
):
    async def broken(self, request):
        if failure == "unexpected":
            raise RuntimeError("synthetic-private-benchmark-failure")
        self.calls += 0 if failure == "zero_calls" else 2
        return self.response

    logger = logging.getLogger("gateway7")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(benchmark._ImmediateProvider, "complete", broken)
    assert benchmark.main(["--counts", "1", "--samples", "1", "--warmup", "0", "--json"]) == 1
    output = capsys.readouterr()
    assert output.out == "" and "Benchmark failed" in output.err
    assert "synthetic-private-benchmark-failure" not in output.err
    assert logger.disabled is False


@pytest.mark.parametrize("termination", ["cancel", "timeout"])
async def test_cancellation_and_time_budget_clean_up_awaited_work(monkeypatch, termination):
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked(self, request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    logger = logging.getLogger("gateway7")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(benchmark._ImmediateProvider, "complete", blocked)
    before_tasks = asyncio.all_tasks()
    work = asyncio.create_task(
        benchmark.run_benchmark((0,), samples=1, warmup=0, timeout_seconds=1)
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if termination == "cancel":
            work.cancel()
        expected = asyncio.CancelledError if termination == "cancel" else TimeoutError
        with pytest.raises(expected):
            await asyncio.wait_for(work, 5)
        assert cleaned.is_set() and logger.disabled is False
        assert asyncio.all_tasks() == before_tasks
    finally:
        if not work.done():
            work.cancel()
        await asyncio.gather(work, return_exceptions=True)


@pytest.mark.skipif(
    os.name != "posix", reason="Uses POSIX SIGINT; exit mapping is platform independent"
)
async def test_real_cli_sigint_exits_130_without_traceback_or_report():
    script = """
import asyncio
from demo import benchmark

async def blocked(self, request):
    print('READY', flush=True)
    await asyncio.Event().wait()

benchmark._ImmediateProvider.complete = blocked
raise SystemExit(benchmark.main(['--counts', '0', '--samples', '1', '--warmup', '0', '--json']))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-c",
        script,
        cwd=Path(__file__).resolve().parents[1],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 10) == b"READY\n"
        process.send_signal(signal.SIGINT)
        stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode == 130
        assert stdout == b"" and b"Benchmark interrupted" in stderr
        assert b"Traceback" not in stderr
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
