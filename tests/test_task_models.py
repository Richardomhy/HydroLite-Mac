def test_task_model_defaults():
    from hydrolite.task_models import TaskSpec
    spec = TaskSpec(stage_id="test", display_name="Test", command=["python", "-V"])
    assert spec.retry_policy.max_attempts == 1
    assert spec.timeout > 0
