from custom_components.av_companion.standby import StandbyGuard
import pytest


@pytest.mark.parametrize(
    "state", ["off", "standby", "idle", "playing", "paused", "unavailable", None]
)
def test_confirmed_no_signal_overrides_stale_player(state):
    g = StandbyGuard()
    assert g.observe(0, state, False, eligible=True) is None
    assert g.observe(14, state, False, eligible=True) is None
    assert g.observe(15, state, False, eligible=True) == "no_signal"


@pytest.mark.parametrize(
    "state",
    ["off", "standby", "playing", "paused", "buffering", "on", "unavailable", None],
)
def test_unknown_signal_is_not_standby(state):
    g = StandbyGuard()
    for t in (0, 900, 10000):
        assert g.observe(t, state, None, eligible=True) is None


def test_idle_fallback_and_disabled_timeout():
    g = StandbyGuard()
    assert g.observe(0, "idle", None, eligible=True) is None
    assert g.observe(899, "idle", None, eligible=True) is None
    assert g.observe(900, "idle", None, eligible=True) == "idle_timeout"
    assert g.observe(901, "idle", None, eligible=True, idle_seconds=0) is None


@pytest.mark.parametrize("state", ["off", "standby", "idle", "playing", "paused"])
def test_present_signal_protects_picture(state):
    g = StandbyGuard()
    for t in (0, 900, 10000):
        assert g.observe(t, state, True, eligible=True) is None


@pytest.mark.parametrize("reset", ["signal", "input", "playback", "unknown"])
def test_interrupted_evidence_starts_again(reset):
    g = StandbyGuard()
    g.observe(0, "idle", False, eligible=True)
    args = {
        "signal": ("idle", True, True),
        "input": ("idle", False, False),
        "playback": ("playing", None, True),
        "unknown": (None, None, True),
    }[reset]
    assert g.observe(119, args[0], args[1], eligible=args[2]) is None
    assert g.observe(120, "idle", False, eligible=True) is None
    assert g.observe(240, "idle", False, eligible=True) == "no_signal"


@pytest.mark.parametrize("state", ["off", "standby"])
def test_false_off_requires_configured_continuous_signal_loss(state):
    g = StandbyGuard()
    assert g.observe(0, state, False, eligible=True, no_signal_seconds=30) is None
    assert g.observe(10, state, False, eligible=True, no_signal_seconds=30) is None
    assert (
        g.observe(30, state, False, eligible=True, no_signal_seconds=30) == "no_signal"
    )
    assert g.observe(31, state, None, eligible=True, low_power=True) is None
    assert g.observe(9999, state, None, eligible=True, low_power=True) is None


@pytest.mark.parametrize("state", ["off", "standby", "idle"])
def test_disabled_signal_loss_timer_never_uses_player_off_as_shortcut(state):
    g = StandbyGuard()
    for now in (0, 10, 120, 10000):
        assert g.observe(now, state, False, eligible=True, no_signal_seconds=0) is None


def test_intermitttent_signal_query_does_not_prevent_idle_fallback():
    g = StandbyGuard()
    for t in range(0, 900, 60):
        assert (
            g.observe(t, "idle", False if t % 120 == 0 else None, eligible=True) is None
        )
    assert g.observe(900, "idle", None, eligible=True) == "idle_timeout"


def test_power_evidence_needs_idle_and_confirmation():
    g = StandbyGuard()
    assert g.observe(0, "idle", None, eligible=True, low_power=True) is None
    assert g.observe(119, "idle", None, eligible=True, low_power=True) is None
    assert (
        g.observe(120, "idle", None, eligible=True, low_power=True) == "idle_low_power"
    )
    assert g.observe(121, "playing", None, eligible=True, low_power=True) is None
    assert g.observe(122, "idle", True, eligible=True, low_power=True) is None
