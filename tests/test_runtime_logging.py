from tests.runtime_helpers import configure_runtime


def test_log_redaction_search_and_summary(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_logging import log_runtime_event, search_logs, summarize_run_logs
    log_runtime_event("r", "t", "INFO", "token=abc password=secret operation ok")
    rows = search_logs("r", "operation")
    assert rows and "abc" not in rows[0]["message"] and "secret" not in rows[0]["message"]
    assert summarize_run_logs("r")["count"] == 1
