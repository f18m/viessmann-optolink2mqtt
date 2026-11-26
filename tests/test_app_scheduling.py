import os
import sched
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


def make_app():
    clock = FakeClock()
    app = Optolink2MqttApp()
    app.scheduler = sched.scheduler(clock.time, clock.sleep)
    app.optolink_interface = Mock()
    app.optolink_interface.sample_register.return_value = 42
    app.optolink_interface.write_register.return_value = True
    app.enhanced_mqtt_client = Mock()
    reg = OptolinkVS2Register(
        {
            "name": "dhw_temperature_set",
            "sampling_period_seconds": 600,
            "register": 0x6000,
            "length": 2,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        },
        "prefix/",
    )
    app.register_list_by_cmd_topic[reg.get_mqtt_command_topic()] = reg
    # same as what setup() does
    app.next_sampling_event_by_register[reg] = app.scheduler.enter(
        0.1,
        Optolink2MqttApp.NORMAL_SCHEDULER_PRIORITY,
        Optolink2MqttApp.on_schedule_timer,
        (app, reg),
    )
    return app, reg, clock


def events_for(app, reg):
    return [e for e in app.scheduler.queue if e.argument[1] is reg]


def test_periodic_sampling_keeps_a_single_event_per_register():
    app, reg, clock = make_app()

    for _ in range(3):
        app.scheduler.run(blocking=False)
        clock.now = app.scheduler.queue[0].time

    assert len(events_for(app, reg)) == 1


def test_mqtt_writes_do_not_add_periodic_sampling_chains():
    app, reg, clock = make_app()
    clock.now = 0.1
    app.scheduler.run(blocking=False)  # initial sampling
    assert app.optolink_interface.sample_register.call_count == 1

    for value in [b"40", b"45", b"50"]:
        msg = Mock(topic=reg.get_mqtt_command_topic(), payload=value)
        app._process_received_mqtt_message(msg)
        clock.now += 1
        app.scheduler.run(blocking=False)  # runs the read-back

    events = events_for(app, reg)
    assert len(events) == 1
    # the periodic sampling restarts from the last read-back
    assert events[0].time == clock.now + reg.get_next_occurrence_in_seconds()
    assert app.optolink_interface.write_register.call_count == 3
    assert app.optolink_interface.sample_register.call_count == 4
