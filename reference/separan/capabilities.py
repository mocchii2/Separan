"""Host-controlled capability boundary for Separan side effects."""

from dataclasses import dataclass
from pathlib import Path
import shutil

from .errors import error


@dataclass(frozen=True)
class RuntimeCapabilities:
    root: Path
    read_files: bool = True
    write_files: bool = True
    discover_paths: bool = True
    read_environment: bool = True
    write_environment: bool = True
    import_modules: bool = True
    readable_environment: frozenset | None = None
    writable_environment: frozenset | None = None
    run_processes: bool = True
    run_shell: bool = False
    inherit_process_environment: bool = False
    allowed_commands: frozenset | None = None
    max_process_timeout_ms: int = 300_000
    max_process_output_bytes: int = 1_048_576
    network: bool = False
    inspect_network: bool = False
    configure_network: bool = False
    bind_network: bool = False
    network_schemes: frozenset = frozenset({"https"})
    network_hosts: frozenset | None = None
    network_ports: frozenset | None = None
    network_bind_hosts: frozenset | None = frozenset({"127.0.0.1", "::1"})
    network_bind_ports: frozenset | None = frozenset({0})
    allow_private_network: bool = False
    max_http_timeout_ms: int = 300_000
    max_http_response_bytes: int = 67_108_864
    max_socket_timeout_ms: int = 300_000
    max_socket_receive_bytes: int = 67_108_864
    send_mail: bool = False
    allowed_mail_senders: frozenset | None = None
    allowed_mail_recipients: frozenset | None = None
    max_mail_recipients: int = 50
    max_mail_message_bytes: int = 10_000_000
    max_mail_timeout_ms: int = 300_000
    read_secrets: bool = False
    allowed_secrets: frozenset | None = None
    host_http: bool = False
    http_bind_hosts: frozenset = frozenset({"127.0.0.1"})
    http_bind_ports: frozenset | None = None
    database: bool = True
    database_drivers: frozenset = frozenset({"sqlite"})
    embedded_io: bool = False
    embedded_boards: frozenset | None = None

    @classmethod
    def local(cls, root): return cls(Path(root).resolve())
    @classmethod
    def none(cls, root):
        return cls(Path(root).resolve(), read_files=False, write_files=False, discover_paths=False,
                   read_environment=False, write_environment=False, import_modules=False,
                   run_processes=False, run_shell=False, network=False, send_mail=False, database=False,
                   inspect_network=False, configure_network=False, bind_network=False, embedded_io=False)

    def require(self, allowed, action, position):
        if not allowed: raise error("E720", "Permission error", f"Host capability does not allow {action}.", position, actual=action)

    def path(self, value, action, position):
        if type(value) is not str: raise error("E201", "Type error", f"{action} path must be a string.", position, expected="string", actual=type(value).__name__)
        path = Path(value)
        if path.is_absolute() or ".." in path.parts: raise error("E721", "Invalid capability path", "Paths must be relative and cannot contain '..'.", position, actual=value)
        resolved = (self.root / path).resolve()
        if resolved != self.root and self.root not in resolved.parents: raise error("E721", "Capability root escape", "Path escapes the capability root.", position, actual=value)
        return resolved

    def environment(self, name, write, position):
        allowed = self.write_environment if write else self.read_environment
        names = self.writable_environment if write else self.readable_environment
        self.require(allowed, ("write" if write else "read") + " environment", position)
        if names is not None and name not in names: raise error("E720", "Permission error", f"Environment variable '{name}' is outside the host allowlist.", position, actual=name)

    def command(self, name, position):
        self.require(self.run_processes, "run processes", position)
        if type(name) is not str or not name or "\0" in name: raise error("E801", "Invalid command", "Command must be a non-empty string without NUL.", position, actual=repr(name))
        resolved = shutil.which(name)
        if resolved is None and Path(name).is_absolute() and Path(name).is_file(): resolved = name
        if resolved is None: return None
        canonical = str(Path(resolved).resolve())
        if self.allowed_commands is not None:
            allowed = {str(Path(item).resolve()) for item in self.allowed_commands}
            if canonical not in allowed: return None
        return canonical
