"""Read-only observations of selected Linux sandbox-host capabilities."""

import os
from collections.abc import Callable
from pathlib import Path

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

    Injected filesystem functions allow tests without root, KVM, or a real VPS.
    The probe performs no subprocesses, privileged operations, or host changes.
    """
    os_type = _safe_read(read_text, "/proc/sys/kernel/ostype")
    linux = os_type.strip() == "Linux" if os_type is not None else None

    if linux is True:
        namespaces = all(exists(path) for path in _NAMESPACE_PATHS)
        controllers = _safe_read(read_text, "/sys/fs/cgroup/cgroup.controllers")
        cgroups_v2 = bool(controllers.strip()) if controllers is not None else None
        actions = _safe_read(read_text, "/proc/sys/kernel/seccomp/actions_avail")
        seccomp = "allow" in actions.split() if actions is not None else None
        apparmor = _safe_read(read_text, "/sys/module/apparmor/parameters/enabled")
        selinux = _safe_read(read_text, "/sys/fs/selinux/enforce")
        apparmor_active = (
            apparmor.strip().lower() == "y" if apparmor is not None else False
        )
        selinux_active = selinux.strip() == "1" if selinux is not None else False
        if apparmor_active or selinux_active:
            mac_active = True
        elif apparmor is not None and selinux is not None:
            mac_active = False
        else:
            mac_active = None
        kvm_present = exists("/dev/kvm")
        kvm_accessible = accessible("/dev/kvm") if kvm_present else False
    else:
        namespaces = cgroups_v2 = seccomp = mac_active = None
        kvm_present = kvm_accessible = None

    return {
        "linux_host": linux,
        "linux_namespaces_present": namespaces,
        "cgroups_v2_present": cgroups_v2,
        "seccomp_kernel_support_observed": seccomp,
        "apparmor_or_selinux_active": mac_active,
        "kvm_device_present": kvm_present,
        "kvm_device_accessible_to_probe": kvm_accessible,
    }
