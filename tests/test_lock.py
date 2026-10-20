from __future__ import annotations

import os

from lenovorgb.lock import InstanceLock


def test_second_instance_is_rejected(tmp_path):
    path = tmp_path / "instance.lock"
    first = InstanceLock(path)
    assert first.acquire(label="gui")
    try:
        second = InstanceLock(path)
        assert not second.acquire()
        assert second.holder_pid == os.getpid()
        assert second.holder_label == "gui"
    finally:
        first.release()


def test_lock_can_be_reacquired(tmp_path):
    path = tmp_path / "instance.lock"
    lock = InstanceLock(path)
    meta = path.with_name(path.name + ".meta")
    assert lock.acquire()
    assert meta.is_file()
    lock.release()
    assert not meta.exists()
    assert lock.acquire()
    lock.release()


def test_context_manager(tmp_path):
    path = tmp_path / "instance.lock"
    with InstanceLock(path) as lock:
        assert lock.held
    assert not lock.held
