"""The manual acceptance harness must not select a user's actual installation."""

import pytest
from dev.lab_scope import lab_entry


@pytest.mark.parametrize(
    "domain,title",
    [("lg_rs232_ip", "LG Split Test"), ("av_companion", "AV Split Test")],
)
def test_lab_selection_ignores_other_devices_and_wrong_domains(domain, title):
    target = {"domain": domain, "title": title, "entry_id": "lab"}
    entries = [
        {"domain": domain, "title": "Living room", "entry_id": "actual-device"},
        {"domain": "another", "title": title, "entry_id": "wrong-domain"},
        target,
    ]
    assert lab_entry(entries, domain) is target


@pytest.mark.parametrize("domain", ["lg_rs232_ip", "av_companion"])
def test_missing_lab_never_falls_back_to_first_device(domain):
    entries = [{"domain": domain, "title": "Living room", "entry_id": "actual-device"}]
    with pytest.raises(ValueError, match="Missing test entry"):
        lab_entry(entries, domain)
    assert lab_entry(entries, domain, required=False) is None


@pytest.mark.parametrize("required", [True, False])
def test_duplicate_names_fail_before_configuration_or_disable(required):
    entries = [
        {"domain": "av_companion", "title": "AV Split Test", "entry_id": value}
        for value in ("a", "b")
    ]
    with pytest.raises(ValueError, match="Multiple test entries"):
        lab_entry(entries, "av_companion", required=required)
