from __future__ import annotations

import os

from lenovorgb.lock import InstanceLock


def test_second_instance_is_rejected(tmp_path):
    path = tmp_path / "instance.lock"
    first = InstanceLock(path)
    assert first.acquire()
    try:
        second = InstanceLock(path)
        assert not second.acquire()
        assert second.holder_pid == os.getpid()
    finally:
        first.release()


def test_lock_can_be_reacquired(tmp_path):
    path = tmp_path / "instance.lock"
    lock = InstanceLock(path)
    assert lock.acquire()
    lock.release()
    assert lock.acquire()
    lock.release()


def test_context_manager(tmp_path):
    path = tmp_path / "instance.lock"
    with InstanceLock(path) as lock:
        assert lock.held
    assert not lock.held
