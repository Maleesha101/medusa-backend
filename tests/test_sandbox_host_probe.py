from app.services.sandbox_host_probe import probe_linux_host_capabilities


def host_facts() -> dict[str, str]:
    return {
        "/proc/sys/kernel/ostype": "Linux\n",
        "/sys/fs/cgroup/cgroup.controllers": "cpu memory pids\n",
        "/sys/kernel/security/seccomp/actions_avail": "kill_process kill_thread trap errno user_notif trace log allow",
        "/sys/module/apparmor/parameters/enabled": "Y\n",
    }


def test_probe_reports_only_observed_linux_capabilities() -> None:
    facts = host_facts()
    namespaces = {
        "/proc/self/ns/cgroup",
        "/proc/self/ns/ipc",
        "/proc/self/ns/mnt",
        "/proc/self/ns/net",
        "/proc/self/ns/pid",
        "/proc/self/ns/uts",
        "/dev/kvm",
    }

    report = probe_linux_host_capabilities(
        read_text=lambda path: facts[path],
        exists=lambda path: path in namespaces,
        accessible=lambda path: path == "/dev/kvm",
    )

    assert report == {
        "linux_host": True,
        "linux_namespaces_present": True,
        "cgroups_v2_present": True,
        "seccomp_kernel_support_observed": True,
        "apparmor_or_selinux_active": True,
        "kvm_device_present": True,
        "kvm_device_accessible_to_probe": True,
    }


def test_missing_or_inaccessible_observations_are_not_assumed_true() -> None:
    report = probe_linux_host_capabilities(
        read_text=lambda _path: (_ for _ in ()).throw(PermissionError()),
        exists=lambda _path: False,
        accessible=lambda _path: False,
    )

    assert all(value is None for value in report.values())


def test_non_linux_host_does_not_report_linux_features() -> None:
    report = probe_linux_host_capabilities(
        read_text=lambda path: "Darwin\n" if path == "/proc/sys/kernel/ostype" else "",
        exists=lambda _path: True,
        accessible=lambda _path: True,
    )

    assert report["linux_host"] is False
    assert report["linux_namespaces_present"] is None
    assert report["cgroups_v2_present"] is None
    assert report["kvm_device_present"] is None


def test_kvm_presence_does_not_imply_device_access() -> None:
    facts = host_facts()
    report = probe_linux_host_capabilities(
        read_text=lambda path: facts[path],
        exists=lambda path: path in {
            "/proc/self/ns/cgroup",
            "/proc/self/ns/ipc",
            "/proc/self/ns/mnt",
            "/proc/self/ns/net",
            "/proc/self/ns/pid",
            "/proc/self/ns/uts",
            "/dev/kvm",
        },
        accessible=lambda _path: False,
    )

    assert report["kvm_device_present"] is True
    assert report["kvm_device_accessible_to_probe"] is False
