"""Provisioning d'une instance : les règles par défaut ne vont qu'aux associations."""
import pytest

from app.services import instance_provisioning


@pytest.fixture()
def commands(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(instance_provisioning, "_run", lambda cmd, url: ran.append(cmd[1:]))
    return lambda chart: instance_provisioning.provision_sqlite_database(
        f"sqlite:///{tmp_path / chart}.db", chart=chart) or ran


def test_asso_gets_default_rules(commands):
    assert commands("asso") == [["-m", "flask", "db", "upgrade"], ["seed_accounts.py", "asso"],
                                ["seed_rules.py"]]


def test_sci_starts_without_rules(commands):
    assert commands("sci") == [["-m", "flask", "db", "upgrade"], ["seed_accounts.py", "sci"]]
