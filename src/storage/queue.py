"""storage/queue.py - 轻量消息队列（threading + queue，演示异步化）。

核心思想：耗时任务(如诊断 5.6s)不阻塞请求线程，提交后立即返回 task_id，
后台线程消费处理，结果落内存可查询。

生产环境用 Celery + Redis，这里用标准库演示同一套设计：
  提交任务(submit) -> 立即返回 task_id -> 后台消费 -> 查结果(get_result)
换 Celery 时，submit 对应 apply_async，get_result 对应 AsyncResult，语义一致。
"""
import queue
import threading
import uuid
from datetime import datetime

_task_queue = queue.Queue()
_results = {}          # task_id -> {"status": pending/done/error, "result": ...}
_worker_started = False


def _worker():
    """后台消费线程：循环取任务、执行、写结果。"""
    while True:
        task_id, fn, args = _task_queue.get()
        try:
            result = fn(*args)
            _results[task_id] = {
                "status": "done",
                "result": result,
                "finished_at": datetime.now().isoformat(),
            }
        except Exception as e:
            _results[task_id] = {"status": "error", "error": str(e)}
        finally:
            _task_queue.task_done()


def _ensure_worker():
    """确保后台消费线程只启动一次。"""
    global _worker_started
    if not _worker_started:
        threading.Thread(target=_worker, daemon=True).start()
        _worker_started = True


def submit(fn, *args):
    """提交一个任务(同步函数)，立即返回 task_id，后台异步执行。"""
    _ensure_worker()
    task_id = uuid.uuid4().hex[:8]
    _results[task_id] = {"status": "pending"}
    _task_queue.put((task_id, fn, args))
    return task_id


def get_result(task_id):
    """按 task_id 查任务结果。未提交返回 None。"""
    return _results.get(task_id)
