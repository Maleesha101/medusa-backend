from app.models.user import User


def _register_and_login(client, email: str) -> str:
    password = "a-very-long-test-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_operational_metrics_are_admin_only(client):
    token = _register_and_login(client, "metrics-participant@example.com")
    response = client.get(
        "/api/v1/admin/operations/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_admin_receives_metrics_and_unavailable_provider_notice(client, session_factory):
    token = _register_and_login(client, "metrics-admin@example.com")
    with session_factory() as db:
        user = db.query(User).filter_by(email="metrics-admin@example.com").one()
        user.role = "admin"
        db.commit()

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
    assert body["sandbox_instances_by_state"] == {}


def test_operational_metrics_require_authentication(client):
    response = client.get("/api/v1/admin/operations/metrics")
    assert response.status_code == 401


def test_operational_alert_thresholds_are_deterministic():
    from types import SimpleNamespace

    from app.services.operational_metrics import _alerts

    settings = SimpleNamespace(
        ops_cpu_warning_percent=80,
        ops_cpu_critical_percent=95,
        ops_memory_warning_percent=80,
        ops_memory_critical_percent=95,
        ops_disk_warning_percent=80,
        ops_disk_critical_percent=95,
        ops_cleanup_warning_count=5,
        ops_cleanup_critical_count=20,
    )
    metrics = {
        "host_cpu_percent": {"value": 85, "unit": "percent", "observed_at": "now"},
        "memory_percent": {"value": 96, "unit": "percent", "observed_at": "now"},
        "disk_percent": {"value": 30, "unit": "percent", "observed_at": "now"},
        "sandbox_cleanup_failed": {"value": 5, "unit": "instances", "observed_at": "now"},
    }

    alerts = _alerts(metrics, settings)

    assert [(alert["id"], alert["severity"]) for alert in alerts] == [
        ("medusa.cpu", "warning"),
        ("medusa.memory", "critical"),
        ("medusa.cleanup_failures", "warning"),
    ]
