"""Read-only observations of selected Linux sandbox-host capabilities.

This probe reports kernel/host facts only. It cannot certify isolation, network
policy, resource enforcement, or provider readiness and never changes the host.
"""

from collections.abc import Callable
from pathlib import Path
import os

ReadText = Callable[[str], str]
PathExists = Callable[[str], bool]
PathAccessible = Callable[[str], bool]

_NAMESPACE_PATHS = (
    "/proc/self/ns/cgroup",
    "/proc/self/ns/ipc",
    "/proc/self/ns/mnt",
    "/proc/self/ns/net",
    "/proc/self/ns/pid",
    "/proc/self/ns/uts",
)
_CGROUP_CONTROLLERS = "/sys/fs/cgroup/cgroup.controllers"
_SECCOMP_ACTIONS = "/sys/kernel/security/seccomp/actions_avail"
_APPARMOR_ENABLED = "/sys/module/apparmor/parameters/enabled"
_SELINUX_ENFORCE = "/sys/fs/selinux/enforce"
_KVM_DEVICE = "/dev/kvm"


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _exists(path: str) -> bool:
    return Path(path).exists()


def _accessible(path: str) -> bool:
    return os.access(path, os.R_OK | os.W_OK)


def _safe_read(read_text: ReadText, path: str) -> str | None:
    try:
        return read_text(path)
    except (OSError, UnicodeError):
        return None


def probe_linux_host_capabilities(
    *,
    read_text: ReadText = _read_text,
    exists: PathExists = _exists,
    accessible: PathAccessible = _accessible,
) -> dict[str, bool | None]:
    """Return sanitized observations; unavailable evidence is represented by None.

    Injected filesystem functions make the probe testable without root, KVM, or
    a real Linux host. No subprocesses or privileged operations are used.
    """
    os_type = _safe_read(read_text, "/proc/sys/kernel/ostype")
    linux = os_type.strip() == "Linux" if os_type is not None else None

    namespace_results = [exists(path) for path in _NAMESPACE_PATHS]
    namespaces = (
        all(namespace_results)
        if linux is True
        else None
    )

    controllers = _safe_read(read_text, _CGROUP_CONTROLLERS)
    cgroups_v2 = (
        bool(controllers.strip())
        if controllers is not None and linux is True
        else None
    )

    seccomp_actions = _safe_read(read_text, _SECCOMP_ACTIONS)
    seccomp = (
        "allow" in seccomp_actions.split()
        if seccomp_actions is not None and linux is True
        else None
    )

    apparmor = _safe_read(read_text, _APPARMOR_ENABLED)
    selinux = _safe_read(read_text, _SELINUX_ENFORCE)
    if linux is not True or (apparmor is None and selinux is None):
        mandatory_access_control = None
    else:
        apparmor_active = apparmor.strip().lower() == "y" if apparmor is not None else False
        selinux_active = selinux.strip() == "1" if selinux is not None else False
        mandatory_access_control = apparmor_active or selinux_active

    kvm_exists = exists(_KVM_DEVICE) if linux is True else None
    kvm_accessible = (
        accessible(_KVM_DEVICE)
        if kvm_exists is True
        else False if kvm_exists is False
        else None
    )

    return {
        "linux_host": linux,
        "linux_namespaces_present": namespaces,
        "cgroups_v2_present": cgroups_v2,
        "seccomp_kernel_support_observed": seccomp,
        "apparmor_or_selinux_active": mandatory_access_control,
        "kvm_device_present": kvm_exists,
        "kvm_device_accessible_to_probe": kvm_accessible,
    }
