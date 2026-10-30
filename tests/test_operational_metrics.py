from app.models.sandbox_instance import SandboxInstance


def test_operational_metrics_are_admin_only(client, session_factory):
    from tests.helpers import create_user_and_token

    participant_token = create_user_and_token(client, "metrics-participant@example.com")
    response = client.get(
        "/api/v1/admin/operations/metrics",
        headers={"Authorization": f"Bearer {participant_token}"},
    )
    assert response.status_code == 403


def test_admin_receives_metrics_and_unavailable_provider_notice(client, session_factory):
    from tests.helpers import create_user_and_token

    token = create_user_and_token(
        client, "metrics-admin@example.com", role="admin"
    )
    response = client.get(
        "/api/v1/admin/operations/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["process_uptime_seconds"]["unit"] == "seconds"
    assert body["metrics"]["host_cpu_percent"]["observed_at"]
    assert body["provider_instance_resource_metrics"]["available"] is False
    assert body["cleanup_worker"]["scope"] == "current_api_process_only"
    assert isinstance(body["alerts"], list)


def test_metrics_include_sandbox_lifecycle_counts(client, session_factory):
    from tests.helpers import create_user_and_token

    token = create_user_and_token(client, "metrics-count-admin@example.com", role="admin")
    response = client.get(
        "/api/v1/admin/operations/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "running" in response.json()["sandbox_instances_by_state"]
