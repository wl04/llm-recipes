"""Incremental run storage that survives interruption."""

import threading
from pathlib import Path

import pytest
from baseline import rawlog


def test_writer_refuses_to_reuse_an_existing_run_directory(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()

    with pytest.raises(ValueError, match="already exists"):
        rawlog.RunWriter(tmp_path / "run")


def test_read_run_returns_meta_requests_and_samples_in_order(tmp_path: Path) -> None:
    writer = rawlog.RunWriter(tmp_path / "run")
    writer.write_meta({"recipe": "r"})
    writer.append_request({"case": "a"})
    writer.append_request({"case": "b"})
    writer.append_sample({"t": 1.0})

    run = rawlog.read_run(tmp_path / "run")

    assert run.meta == {"recipe": "r"}
    assert [r["case"] for r in run.requests] == ["a", "b"]
    assert run.samples == [{"t": 1.0}]


def test_write_meta_replaces_previous_content(tmp_path: Path) -> None:
    writer = rawlog.RunWriter(tmp_path / "run")
    writer.write_meta({"run": {"status": "failed"}})

    writer.write_meta({"run": {"status": "complete"}})

    assert rawlog.read_run(tmp_path / "run").meta["run"]["status"] == "complete"
    assert not list((tmp_path / "run").glob("*.tmp"))


def test_read_run_ignores_a_truncated_final_line(tmp_path: Path) -> None:
    writer = rawlog.RunWriter(tmp_path / "run")
    writer.write_meta({"recipe": "r"})
    writer.append_request({"case": "a"})
    with (tmp_path / "run" / "requests.jsonl").open("a") as handle:
        handle.write('{"case": "b", "usa')

    run = rawlog.read_run(tmp_path / "run")

    assert [r["case"] for r in run.requests] == ["a"]


def test_read_run_rejects_a_malformed_line_in_the_middle(tmp_path: Path) -> None:
    writer = rawlog.RunWriter(tmp_path / "run")
    writer.write_meta({"recipe": "r"})
    (tmp_path / "run" / "requests.jsonl").write_text('{"case": "a"}\nnot json\n{"case": "c"}\n')

    with pytest.raises(ValueError, match=r"requests\.jsonl line 2"):
        rawlog.read_run(tmp_path / "run")


def test_read_run_rejects_directory_without_meta(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()

    with pytest.raises(ValueError, match=r"meta\.json"):
        rawlog.read_run(tmp_path / "run")


def test_concurrent_appends_keep_every_line_intact(tmp_path: Path) -> None:
    writer = rawlog.RunWriter(tmp_path / "run")
    writer.write_meta({"recipe": "r"})

    def work(worker: int) -> None:
        for index in range(50):
            writer.append_sample({"t": float(index), "worker": worker})

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(rawlog.read_run(tmp_path / "run").samples) == 200
