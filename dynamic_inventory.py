#!/usr/bin/env python3
"""
Dynamic inventory script for Ansible Automation Platform 2.6.

Reads the HOSTS inventory variable (set on the AAP inventory as a custom
variable) and emits a JSON inventory that AAP can consume.

Variable format (set on the AAP Inventory's "Variables" field):
  HOSTS: "host-a,host-b,host-c"

Optional per-host or group variables can also be set on the inventory:
  HOST_VARS: '{"host-a": {"ansible_user": "ec2-user"}, "host-b": {"ansible_port": 2222}}'
  GROUP:     "webservers"          # group name; defaults to "dynamic_hosts"
  GROUP_VARS: '{"ansible_user": "root"}'

Usage (AAP Custom Inventory Script):
  Script must be executable and accept --list / --host <hostname> flags.

  --list   Print full inventory JSON (used by Ansible/AAP at runtime)
  --host   Print vars for a specific host (returns empty dict; all vars in --list)
"""

import argparse
import json
import os
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    """Return stripped env var or default."""
    return os.environ.get(key, default).strip()


def _parse_hosts(raw: str) -> list[str]:
    """Split a comma-separated host string; skip empty tokens."""
    return [h.strip() for h in raw.split(",") if h.strip()]


def _parse_json_var(raw: str, var_name: str) -> dict:
    """Parse a JSON string variable; exit with a clear error on bad JSON."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            _die(f"{var_name} must be a JSON object, got {type(parsed).__name__}")
        return parsed
    except json.JSONDecodeError as exc:
        _die(f"Failed to parse {var_name} as JSON: {exc}")


def _die(message: str) -> None:
    print(json.dumps({"_error": message}), file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Inventory builder
# ---------------------------------------------------------------------------

def build_inventory() -> dict:
    """
    Construct the Ansible inventory dict from environment / inventory variables.

    AAP injects inventory-level variables into the script's environment when
    the inventory type is 'Custom Script'.  Variable names are uppercased and
    passed verbatim.
    """
    raw_hosts   = _env("HOSTS")
    raw_hvars   = _env("HOST_VARS")
    group_name  = _env("GROUP", "dynamic_hosts")
    raw_gvars   = _env("GROUP_VARS")

    if not raw_hosts:
        _die(
            "HOSTS variable is not set or empty. "
            "Set it on the AAP Inventory's Variables field as: HOSTS: \"host-a,host-b\""
        )

    hosts      = _parse_hosts(raw_hosts)
    host_vars  = _parse_json_var(raw_hvars, "HOST_VARS")
    group_vars = _parse_json_var(raw_gvars, "GROUP_VARS")

    # Validate: every key in HOST_VARS should reference a known host
    unknown = set(host_vars) - set(hosts)
    if unknown:
        # Non-fatal: warn on stderr so the job log shows it
        print(
            f"WARNING: HOST_VARS contains entries for unknown hosts: "
            f"{', '.join(sorted(unknown))}",
            file=sys.stderr,
        )

    inventory = {
        group_name: {
            "hosts": hosts,
        },
        "_meta": {
            "hostvars": {host: host_vars.get(host, {}) for host in hosts},
        },
    }

    if group_vars:
        inventory[group_name]["vars"] = group_vars

    return inventory


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AAP 2.6 dynamic inventory — hosts from HOSTS variable"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list",
        action="store_true",
        help="Output the full inventory as JSON",
    )
    group.add_argument(
        "--host",
        metavar="HOSTNAME",
        help="Output variables for a specific host (returns {} — all vars in --list)",
    )
    args = parser.parse_args()

    if args.list:
        print(json.dumps(build_inventory(), indent=2))
    else:
        # Per-host vars are embedded in _meta.hostvars inside --list, so
        # returning an empty dict here is correct and avoids a second API call.
        print(json.dumps({}))


if __name__ == "__main__":
    main()
