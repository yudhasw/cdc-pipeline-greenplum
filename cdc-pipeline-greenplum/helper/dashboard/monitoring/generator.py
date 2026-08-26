"""Kontrol generator trafik uji + pengukur latensi, dijalankan sebagai thread
background di dalam proses dashboard sendiri - bukan proses/container
terpisah.

Kenapa bisa begini: dashboard sudah punya koneksi psycopg2 langsung ke cutidev
(config.SOURCE_PG_*, dipakai monitoring/health.py untuk cek replication lag)
dan ke Greenplum target (config.PG_*, dipakai backend analytics). Generator
dan pengukur latensi cukup thread Python biasa yang pakai koneksi sama,
tidak perlu docker exec ke container lain.

Versi standalone (bisa dijalankan manual di luar dashboard, tanpa web UI) ada
di helper/testing/generator.py dan helper/testing/measure_latency.py - logic
intinya sama, sengaja tidak di-share/di-import supaya dua konteks (script CLI
vs thread web server) tetap independen dan gampang dibaca terpisah.

Batasan yang sama seperti versi standalone: cuma INSERT dan UPDATE ke cutidev
(tidak ada DELETE, hindari risiko FK), user_id/role_id tetap (2065/1, sudah
terbukti valid), baris ditandai "[GEN-TEST]" di leaving_reason.
"""

import random
import threading
import time
from collections import deque
from datetime import datetime, timezone

import psycopg2

import config

USER_ID = 2065
ROLE_ID = 1
TAG = "[GEN-TEST]"
STATUSES = ["On Progress", "Approved", "Rejected"]
MAX_SAMPLES = 200

_lock = threading.Lock()
_state = {
    "running": False,
    "thread": None,
    "stop_event": None,
    "tick": 0,
    "last_action": None,
    "error": None,
}
_latency = {
    "seen_ids": set(),
    "samples": deque(maxlen=MAX_SAMPLES),
    "monitor_started": False,
}


def _source_conn():
    return psycopg2.connect(
        host=config.SOURCE_PG_HOST, port=config.SOURCE_PG_PORT, dbname=config.SOURCE_PG_DATABASE,
        user=config.SOURCE_PG_USER, password=config.SOURCE_PG_PASSWORD, connect_timeout=10,
    )


def _target_conn():
    return psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DATABASE,
        user=config.PG_USER, password=config.PG_PASSWORD, connect_timeout=10,
    )


def _generator_loop(stop_event, interval_seconds):
    conn = None
    try:
        while not stop_event.is_set():
            try:
                if conn is None:
                    conn = _source_conn()
                    conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO leave_leavedocument
                            (created, document_type, need_trip_period, leaving_reason, status,
                             max_step, cur_step, is_admin_approve_to_cancel, user_id, role_id)
                        VALUES (now(), 'TEST_CDC', 1, %s, 'Draft', 1, 1, false, %s, %s)
                        RETURNING id
                        """,
                        (f"{TAG} generator {datetime.now(timezone.utc).isoformat()}", USER_ID, ROLE_ID),
                    )
                    new_id = cur.fetchone()[0]

                    with _lock:
                        _state["tick"] += 1
                        tick = _state["tick"]
                        _state["last_action"] = f"INSERT id={new_id}"

                    if tick % 3 == 0:
                        cur.execute(
                            "SELECT id FROM leave_leavedocument WHERE leaving_reason LIKE %s "
                            "ORDER BY random() LIMIT 1",
                            (f"{TAG}%",),
                        )
                        row = cur.fetchone()
                        if row:
                            upd_id = row[0]
                            new_status = random.choice(STATUSES)
                            cur.execute(
                                "UPDATE leave_leavedocument SET status = %s WHERE id = %s",
                                (new_status, upd_id),
                            )
                            with _lock:
                                _state["last_action"] = f"UPDATE id={upd_id} status={new_status}"
            except Exception as e:
                with _lock:
                    _state["error"] = str(e)
                # Koneksi mungkin sudah rusak (mis. timeout/putus di tengah
                # jalan) - buang dan bikin baru di siklus berikutnya, bukan
                # terus dipakai ulang dalam keadaan rusak.
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
            stop_event.wait(interval_seconds)
    finally:
        if conn is not None:
            conn.close()


def start(interval_seconds=5.0):
    with _lock:
        if _state["running"]:
            return {"ok": False, "detail": "generator sudah jalan"}
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_generator_loop, args=(stop_event, interval_seconds), daemon=True
        )
        _state.update(running=True, thread=thread, stop_event=stop_event, tick=0, error=None)
        thread.start()
    _ensure_latency_monitor()
    return {"ok": True, "detail": f"generator dimulai, interval {interval_seconds}s"}


def stop():
    with _lock:
        if not _state["running"]:
            return {"ok": False, "detail": "generator tidak sedang jalan"}
        _state["stop_event"].set()
        thread = _state["thread"]
    thread.join(timeout=10)
    with _lock:
        _state.update(running=False, thread=None, stop_event=None)
    return {"ok": True, "detail": "generator dihentikan"}


def _latency_monitor_loop():
    conn = _target_conn()
    conn.autocommit = True
    try:
        while True:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT id, __source_ts_ms FROM {config.PG_SCHEMA}.leave_leavedocument "
                        "WHERE leaving_reason LIKE %s",
                        (f"{TAG}%",),
                    )
                    rows = cur.fetchall()
                now = time.time()
                with _lock:
                    for rid, ts_ms in rows:
                        if rid in _latency["seen_ids"] or ts_ms is None:
                            continue
                        _latency["seen_ids"].add(rid)
                        _latency["samples"].append(now - ts_ms / 1000.0)
            except Exception:
                pass
            time.sleep(2)
    finally:
        conn.close()


def _ensure_latency_monitor():
    with _lock:
        if _latency["monitor_started"]:
            return
        _latency["monitor_started"] = True
    threading.Thread(target=_latency_monitor_loop, daemon=True).start()


def status():
    with _lock:
        running = _state["running"]
        tick = _state["tick"]
        last_action = _state["last_action"]
        error = _state["error"]
        samples = list(_latency["samples"])

    latency_stats = None
    if samples:
        latency_stats = {
            "count": len(samples),
            "min": round(min(samples), 2),
            "max": round(max(samples), 2),
            "avg": round(sum(samples) / len(samples), 2),
            "last": round(samples[-1], 2),
        }

    return {
        "running": running,
        "tick": tick,
        "last_action": last_action,
        "error": error,
        "latency": latency_stats,
    }
