"""Dashboard input and interlock checks; all robot calls are mocked."""
from unittest.mock import MagicMock
import pygame as pg
import pytest
from elegoo_robot_car4.dashboard import Dashboard, DashboardState
from elegoo_robot_car4.elegoo_smartcar_control import GameEngine
from elegoo_robot_car4.analogue_drive import AnalogueDrive


def engine(mocker, axes=None):
    axes = {} if axes is None else axes
    e = GameEngine.__new__(GameEngine)
    e._GameEngine__car = MagicMock()
    e._GameEngine__analogue = AnalogueDrive()
    e._GameEngine__ui = DashboardState()
    e._GameEngine__dashboard = MagicMock()
    e._GameEngine__dashboard.action.side_effect = lambda event: event
    e._GameEngine__dry_run = False
    e._GameEngine__stop_held = False
    e._GameEngine__neutral_required = False
    pad = MagicMock()
    pad.attached.return_value = True
    pad.get_button.return_value = False
    pad.get_axis.side_effect = lambda axis: axes.get(axis, 0)
    e._GameEngine__joysticks = {1: pad}
    mocker.patch('pygame.key.get_focused', return_value=True)
    return e


def test_stop_latches_until_explicit_resume_and_current_neutral(mocker):
    axes = {pg.CONTROLLER_AXIS_TRIGGERRIGHT: 32767}
    e = engine(mocker, axes)
    e._GameEngine__handle_dashboard_events(['stop'])
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__stop_held
    assert not e._GameEngine__ui.can_resume
    e._GameEngine__car.drive_analogue.assert_called_with(0, 0, 0)
    axes.clear()
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__ui.can_resume and e._GameEngine__stop_held
    e._GameEngine__handle_dashboard_events(['resume'])
    # Pressing a trigger after the last UI render invalidates the resume attempt.
    axes[pg.CONTROLLER_AXIS_TRIGGERRIGHT] = 32767
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__stop_held
    e._GameEngine__handle_dashboard_events([])
    axes.clear()
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__stop_held
    e._GameEngine__handle_dashboard_events(['resume'])
    e._GameEngine__handle_analogue_actions()
    assert not e._GameEngine__stop_held
    assert e._GameEngine__ui.status == 'Ready'
    assert all(call.args[:2] == (0, 0) for call in e._GameEngine__car.drive_analogue.call_args_list)


def test_stop_wins_over_resume_and_survives_failed_stop_ack(mocker):
    e = engine(mocker)
    e._GameEngine__ui.can_resume = True
    e._GameEngine__car.stop.side_effect = TimeoutError()
    e._GameEngine__handle_dashboard_events(['resume', 'stop'])
    assert e._GameEngine__stop_held and e._GameEngine__neutral_required
    assert not e._GameEngine__resume_requested
    assert e._GameEngine__ui.status == 'Stop unconfirmed'


def test_resume_requires_successful_zero_ack(mocker):
    e = engine(mocker)
    e._GameEngine__handle_dashboard_events(['stop'])
    e._GameEngine__ui.can_resume = True
    e._GameEngine__handle_dashboard_events(['resume'])
    e._GameEngine__car.drive_analogue.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__stop_held
    assert e._GameEngine__ui.ack_at is None


@pytest.mark.parametrize('guard', ['stale', 'raised'])
def test_environment_guard_recovery_requires_neutral(mocker, guard):
    axes = {pg.CONTROLLER_AXIS_TRIGGERRIGHT: 32767}
    e = engine(mocker, axes)
    e._GameEngine__car.is_far_from_the_ground.side_effect = [guard=='raised', False]
    mocker.patch.object(e, '_GameEngine__render_dashboard')
    mocker.patch.object(e, '_GameEngine__display_new_frame', side_effect=[guard!='stale', True])
    mocker.patch('pygame.time.Clock')
    mocker.patch('pygame.display.set_caption')
    mocker.patch('pygame.event.get', side_effect=[[], [], [pg.event.Event(pg.QUIT)]])
    # Force sensor refresh on both iterations without depending on wall time.
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.time.monotonic', side_effect=lambda: 10+e._GameEngine__car.is_far_from_the_ground.call_count)
    e.run()
    assert e._GameEngine__neutral_required
    for call in e._GameEngine__car.drive_analogue.call_args_list:
        assert call.args[:2] == (0, 0)


def test_command_indicators_update_only_after_ack(mocker):
    e = engine(mocker)
    e._GameEngine__send_analogue(120, 60, -25)
    state = e._GameEngine__ui
    assert (state.left, state.right, state.head) == (120, 60, -25)
    assert state.ack_ms >= 0 and state.ack_at is not None
    e._GameEngine__car.drive_analogue.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        e._GameEngine__send_analogue(200, 200, 0)
    assert (state.left, state.right, state.head) == (120, 60, -25)
    e._GameEngine__dashboard_status('Error', 'Unknown output', 'error')
    assert state.left is None and state.right is None


@pytest.fixture
def dashboard(monkeypatch):
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    pg.init()
    d = Dashboard(preview=True)
    yield d
    pg.quit()


@pytest.mark.parametrize('size', [(1280, 960), (900, 700), (1600, 900)])
def test_stop_and_resume_hitboxes_follow_letterboxed_resize(dashboard, size):
    dashboard.action(pg.event.Event(pg.VIDEORESIZE, w=size[0], h=size[1]))
    for rect, expected in [(Dashboard.STOP, 'stop'), (Dashboard.RESUME, 'resume'), (Dashboard.RECONNECT, 'reconnect')]:
        point = tuple(round(p*dashboard.scale+o) for p,o in zip(rect.center, dashboard.offset))
        assert dashboard.action(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point)) == expected
    assert dashboard.action(pg.event.Event(pg.KEYDOWN, key=pg.K_SPACE)) == 'stop'
    assert dashboard.action(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(0,0))) is None


def test_camera_keeps_aspect_ratio_and_states_render_without_robot(dashboard):
    frame = pg.Surface((800, 600))
    frame.fill('blue')
    dashboard.set_frame(frame)
    rect = dashboard._scaled_frame[1]
    assert rect.w/rect.h == pytest.approx(4/3)
    for state in [DashboardState(), DashboardState(status='Ready', video_stale=False),
                  DashboardState(status='Stopped by you', stopped=True, can_resume=True),
                  DashboardState(status='Connection error', reason='No valid reply; driving blocked.', level='error')]:
        dashboard.draw(state, 1)
    assert Dashboard.pan_label(-35) == '35 deg right'


def immediate_camera_settings(mocker):
    """Acknowledge camera writes deterministically without real HTTP requests."""
    settings = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.CameraSettings').return_value
    settings.busy = False
    settings.quality = 10
    results = []
    settings.start.side_effect = lambda key: results.append((key, None)) or True
    settings.poll.side_effect = lambda: results.pop(0) if results else None
    return settings


def test_actual_dashboard_loop_uses_cached_udp_frame_and_stop_resume(dashboard, mocker):
    import numpy as np
    car = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Car').return_value
    car.vision_tracking_is_on = False
    car.is_far_from_the_ground.return_value = False
    video = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.UdpVideo').return_value
    video.latest.return_value = (np.zeros((600, 800, 3), dtype=np.uint8), .02)
    video.frames = 1
    mocker.patch('pygame.key.get_focused', return_value=True)
    immediate_camera_settings(mocker)
    now = [100.0]
    mocker.patch('time.monotonic', side_effect=lambda: now[0])
    mocker.patch('pygame.time.Clock').return_value.tick.side_effect = lambda *_: now.__setitem__(0, now[0]+.1)
    from tests.unit_tests.test_connection import ImmediateExecutor, SteppedConnection
    mocker.patch('elegoo_robot_car4.connection.ThreadPoolExecutor', return_value=ImmediateExecutor())
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Connection', SteppedConnection)
    with GameEngine('test.invalid', video='udp', analogue_drive=True) as e:
        pad = MagicMock()
        pad.name = 'Test controller'
        pad.attached.return_value = True
        pad.get_axis.return_value = 0
        pad.get_button.return_value = False
        e._GameEngine__joysticks = {1: pad}
        view = e._GameEngine__dashboard
        render_frame = mocker.spy(view, 'set_frame')
        point = tuple(round(p*view.scale+o) for p,o in zip(view.RESUME.center, view.offset))
        ticks = [0]
        cached_calls = []
        def events():
            ticks[0] += 1
            tick = ticks[0]
            if tick <= 7:
                video.latest.return_value = (np.zeros((600, 800, 3), dtype=np.uint8), .02)
            if tick == 8:
                assert e._GameEngine__ui.preset == 'balanced'
                cached_calls.append(render_frame.call_count)
            if tick == 10:
                return [pg.event.Event(pg.KEYDOWN, key=pg.K_SPACE)]
            if tick == 12:
                return [pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point)]
            return [pg.event.Event(pg.QUIT)] if tick == 14 else []
        mocker.patch('pygame.event.get', side_effect=events)
        e.run()
        assert e._GameEngine__ui.status == 'Ready'
        assert not e._GameEngine__stop_held
        assert render_frame.call_count == cached_calls[0]
        assert view.frame_size == (800, 600)
        assert all(call.args[:2] == (0, 0) for call in car.drive_analogue.call_args_list)
        car.capture.assert_not_called()
    video.close.assert_called_once()
    car.disconnect.assert_called_once()


def test_active_preset_waits_for_zero_and_preserves_manual_stop(dashboard, mocker):
    import numpy as np
    from tests.unit_tests.test_connection import ImmediateExecutor, SteppedConnection
    car = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Car').return_value
    car.vision_tracking_is_on = False
    car.is_far_from_the_ground.return_value = False
    video = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.UdpVideo').return_value
    video.frames = 1
    settings = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.CameraSettings').return_value
    settings.busy = False
    settings.quality = 10
    results = []
    applied_at = []
    def start(key):
        assert car.drive_analogue.call_args.args[:2] == (0, 0)
        applied_at.append(len(car.drive_analogue.call_args_list))
        results.append((key, None))
        return True
    settings.start.side_effect = start
    settings.poll.side_effect = lambda: results.pop(0) if results else None
    mocker.patch('elegoo_robot_car4.connection.ThreadPoolExecutor', return_value=ImmediateExecutor())
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Connection', SteppedConnection)
    mocker.patch('pygame.key.get_focused', return_value=True)
    now = [100.0]
    mocker.patch('time.monotonic', side_effect=lambda: now[0])
    mocker.patch('pygame.time.Clock').return_value.tick.side_effect = lambda *_: now.__setitem__(0, now[0]+.1)
    with GameEngine('unused', video='udp', analogue_drive=True) as engine:
        pad = MagicMock()
        pad.attached.return_value = True
        pad.get_button.return_value = False
        axes = {}
        pad.get_axis.side_effect = lambda axis: axes.get(axis, 0)
        engine._GameEngine__joysticks = {1: pad}
        ticks = [0]
        def events():
            ticks[0] += 1
            tick = ticks[0]
            shape = (768, 1024, 3) if tick >= 14 else (600, 800, 3)
            video.latest.return_value = (np.zeros(shape, np.uint8), .02)
            if tick == 7:
                axes[pg.CONTROLLER_AXIS_TRIGGERRIGHT] = 32767
            if tick == 12:
                view = engine._GameEngine__dashboard
                point = tuple(round(pos*view.scale+offset) for pos, offset in zip(view.PRESET_RECTS['detail'].center, view.offset))
                return [pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point)]
            if tick == 14:
                return [pg.event.Event(pg.KEYDOWN, key=pg.K_SPACE)]
            if tick == 20:
                assert engine._GameEngine__ui.preset == 'detail'
                assert engine._GameEngine__stop_held
                axes.clear()
            if tick == 24:
                assert engine._GameEngine__ui.can_resume
                return [pg.event.Event(pg.QUIT)]
            return []
        mocker.patch('pygame.event.get', side_effect=events)
        engine.run()
        assert len(applied_at) == 2
        assert all(call.args[:2] == (0, 0) for call in car.drive_analogue.call_args_list[applied_at[1]:])


def test_preview_cli_does_not_construct_robot(mocker):
    from elegoo_robot_car4.elegoo_smartcar_control import main
    mocker.patch('sys.argv', ['elegoo-smartcar-control', '--dashboard-preview'])
    preview = mocker.patch('elegoo_robot_car4.dashboard.preview')
    car = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Car')
    video = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.UdpVideo')
    main()
    preview.assert_called_once()
    car.assert_not_called()
    video.assert_not_called()


def test_raised_stop_timeout_keeps_dashboard_alive_and_drive_blocked(mocker):
    e = engine(mocker)
    e._GameEngine__car.is_far_from_the_ground.return_value = True
    e._GameEngine__car.stop.side_effect = TimeoutError()
    mocker.patch.object(e, '_GameEngine__render_dashboard')
    mocker.patch.object(e, '_GameEngine__display_new_frame', return_value=True)
    mocker.patch('pygame.time.Clock')
    mocker.patch('pygame.display.set_caption')
    mocker.patch('pygame.event.get', side_effect=[[], [pg.event.Event(pg.QUIT)]])
    e.run()
    assert e._GameEngine__ui.status == 'Stop unconfirmed'
    assert e._GameEngine__neutral_required
    e._GameEngine__car.drive_analogue.assert_not_called()


@pytest.mark.parametrize('manual_stop', [False, True])
@pytest.mark.parametrize('reconnect_button', [False, True])
def test_reboot_retries_without_replaying_held_trigger(dashboard, mocker, manual_stop, reconnect_button):
    import numpy as np
    from tests.unit_tests.test_connection import ImmediateExecutor, SteppedConnection
    car1, car2 = MagicMock(), MagicMock()
    for car in (car1, car2):
        car.vision_tracking_is_on = False
        car.is_far_from_the_ground.return_value = False
    factory = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Car', side_effect=[car1, TimeoutError('booting'), car2])
    video = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.UdpVideo').return_value
    video.latest.side_effect = lambda: (np.zeros((600, 800, 3), dtype=np.uint8), .02)
    settings = immediate_camera_settings(mocker)
    video.frames = 1
    mocker.patch('elegoo_robot_car4.connection.ThreadPoolExecutor', return_value=ImmediateExecutor())
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Connection', SteppedConnection)
    mocker.patch('pygame.key.get_focused', return_value=True)
    now = [100.0]
    mocker.patch('time.monotonic', side_effect=lambda: now[0])
    clock = mocker.patch('pygame.time.Clock').return_value
    clock.tick.side_effect = lambda *_: now.__setitem__(0, now[0]+.1)
    with GameEngine('test.invalid', video='udp', analogue_drive=True) as e:
        pad = MagicMock()
        pad.attached.return_value = True
        pad.get_button.return_value = False
        held = [False]
        pad.get_axis.side_effect = lambda axis: 32767 if held[0] and axis == pg.CONTROLLER_AXIS_TRIGGERRIGHT else 0
        e._GameEngine__joysticks = {1: pad}
        ticks = [0]
        def events():
            ticks[0] += 1
            tick = ticks[0]
            if tick == 7:
                held[0] = True
            if tick == 12:
                # Break the old TCP connection after some successful driving.
                actions = [pg.event.Event(pg.KEYDOWN, key=pg.K_SPACE)] if manual_stop else []
                if reconnect_button:
                    view = e._GameEngine__dashboard
                    point = tuple(round(p*view.scale+o) for p,o in zip(view.RECONNECT.center, view.offset))
                    actions.append(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point))
                else:
                    car1.is_far_from_the_ground.side_effect = ConnectionResetError('reboot')
                return actions
            if tick == 60:
                assert factory.call_count == 3  # one failed retry, then recovered
                assert car2.drive_analogue.call_count > 0
                assert all(c.args[:2] == (0, 0) for c in car2.drive_analogue.call_args_list)
                assert e._GameEngine__stop_held == manual_stop
                held[0] = False
            if tick == 65 and manual_stop:
                assert e._GameEngine__ui.can_resume
                view = e._GameEngine__dashboard
                point = tuple(round(p*view.scale+o) for p,o in zip(view.RESUME.center, view.offset))
                return [pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=point)]
            if tick == 68:
                held[0] = True
            if tick == 72:
                return [pg.event.Event(pg.QUIT)]
            return []
        mocker.patch('pygame.event.get', side_effect=events)
        e.run()
        assert any(c.args[0] > 0 for c in car1.drive_analogue.call_args_list)
        assert any(c.args[0] > 0 for c in car2.drive_analogue.call_args_list)
        assert not e._GameEngine__stop_held
        assert e._GameEngine__ui.preset == 'balanced'
        assert settings.start.call_count == 2
