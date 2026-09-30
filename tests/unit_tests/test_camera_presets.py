from unittest.mock import MagicMock
import numpy as np
import pygame as pg
import pytest
import requests
from elegoo_robot_car4.camera_presets import PRESETS, apply_preset, CameraSettings
from elegoo_robot_car4.dashboard import Dashboard, DashboardState
from elegoo_robot_car4.elegoo_smartcar_control import GameEngine
from elegoo_robot_car4.analogue_drive import AnalogueDrive


@pytest.mark.parametrize('key,size,q,enum', [('fast',(320,240),20,5), ('drive',(640,480),15,8),
                                           ('detail',(1024,768),10,10), ('balanced',(800,600),10,9)])
def test_presets_write_expected_legacy_firmware_values_and_readback(key,size,q,enum):
    get=MagicMock()
    get.return_value.json.return_value={'quality':q,'framesize':enum}
    apply_preset('car.test',key,get)
    assert PRESETS[key].size == size
    assert get.call_args_list[0].kwargs['params']=={'var':'quality','val':q}
    assert get.call_args_list[1].kwargs['params']=={'var':'framesize','val':enum}
    assert get.call_args_list[2].args==('http://car.test/status',)
    assert all(c.kwargs['timeout']==(2,3) for c in get.call_args_list)


@pytest.mark.parametrize('status',[{'quality':10,'framesize':8},[],{}])
def test_mismatched_or_invalid_readback_is_failure(status):
    get=MagicMock();get.return_value.json.return_value=status
    with pytest.raises(ValueError):apply_preset('car.test','balanced',get)


def test_http_failure_stops_remaining_setting_requests():
    get=MagicMock();get.return_value.raise_for_status.side_effect=requests.HTTPError()
    with pytest.raises(requests.HTTPError):apply_preset('car.test','balanced',get)
    assert get.call_count==1


def engine():
    e=GameEngine.__new__(GameEngine)
    e._GameEngine__ui=DashboardState()
    e._GameEngine__car=MagicMock()
    e._GameEngine__analogue=AnalogueDrive(left=100,right=100)
    e._GameEngine__camera_settings=MagicMock()
    e._GameEngine__camera_settings.start.return_value=True
    e._GameEngine__camera_settings.poll.return_value=None
    e._GameEngine__stop_held=False
    e._GameEngine__preset_wait=None
    e._GameEngine__last_raw_frame=None
    e._GameEngine__video=None
    e._GameEngine__http_frames=0
    return e


def test_preset_selection_stops_before_request_and_disallows_duplicate():
    e=engine();events=[]
    e._GameEngine__car.stop.side_effect=lambda:events.append('stop')
    e._GameEngine__camera_settings.start.side_effect=lambda k:events.append(k) or True
    e._GameEngine__select_camera_preset('balanced')
    assert events==['stop','balanced']
    assert not e._GameEngine__stop_held and e._GameEngine__neutral_required
    assert e._GameEngine__ui.preset_pending and not e._GameEngine__ui.stopped
    assert e._GameEngine__analogue.left==0
    e._GameEngine__select_camera_preset('drive')
    assert events==['stop','balanced']


def test_failed_stop_does_not_change_camera():
    e=engine();e._GameEngine__car.stop.side_effect=TimeoutError()
    e._GameEngine__select_camera_preset('balanced')
    e._GameEngine__camera_settings.start.assert_not_called()
    assert e._GameEngine__ui.preset_error and not e._GameEngine__ui.preset_pending
    assert not e._GameEngine__stop_held and e._GameEngine__neutral_required


def test_http_success_waits_for_fresh_matching_frame(mocker):
    e=engine();e._GameEngine__ui.preset_pending=True
    e._GameEngine__camera_settings.poll.return_value=('balanced',None)
    now=mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.time.monotonic',return_value=10)
    e._GameEngine__poll_camera_settings()
    frame=np.zeros((600,800,3),dtype=np.uint8)
    e._GameEngine__confirm_camera_frame(frame)
    assert e._GameEngine__ui.preset_pending
    now.return_value=11
    e._GameEngine__confirm_camera_frame(np.zeros((480,640,3),dtype=np.uint8))
    assert e._GameEngine__ui.preset_pending
    e._GameEngine__last_raw_frame=frame
    e._GameEngine__confirm_camera_frame(frame)
    assert e._GameEngine__ui.preset_pending
    e._GameEngine__last_raw_frame=None
    e._GameEngine__confirm_camera_frame(frame)
    assert not e._GameEngine__ui.preset_pending and e._GameEngine__ui.preset=='balanced'


def test_no_matching_video_times_out_and_allows_lower_preset(mocker):
    e=engine();e._GameEngine__ui.preset_pending=True
    e._GameEngine__preset_wait=('balanced',10,18)
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.time.monotonic',return_value=19)
    e._GameEngine__poll_camera_settings()
    assert e._GameEngine__ui.preset_error and not e._GameEngine__ui.preset_pending
    e._GameEngine__select_camera_preset('drive')
    e._GameEngine__camera_settings.start.assert_called_once_with('drive')


def test_worker_serializes_requests_and_surfaces_errors(mocker):
    thread=mocker.patch('elegoo_robot_car4.camera_presets.Thread')
    apply=mocker.patch('elegoo_robot_car4.camera_presets.apply_preset',side_effect=requests.Timeout('offline'))
    settings=CameraSettings('car.test')
    assert settings.start('balanced')
    assert not settings.start('fast')
    assert settings.poll() is None
    thread.call_args.kwargs['target']()
    key,error=settings.poll()
    assert key=='balanced' and 'Timeout' in error
    assert not settings.busy
    apply.assert_called_once_with('car.test','balanced',settings._session.get,settings._cancel)


def test_pending_preset_blocks_resume_even_after_zero_ack(mocker):
    e=engine();e._GameEngine__dry_run=False
    e._GameEngine__stop_held=True;e._GameEngine__resume_requested=True
    e._GameEngine__ui.preset_pending=True
    pad=MagicMock();pad.attached.return_value=True;pad.get_axis.return_value=0
    e._GameEngine__joysticks={1:pad}
    mocker.patch('pygame.key.get_focused',return_value=True)
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__stop_held and not e._GameEngine__ui.can_resume
    e._GameEngine__car.drive_analogue.assert_called_once_with(0,0,0)


def test_preset_hitboxes_after_resize(monkeypatch):
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy');monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    pg.init()
    try:
        d=Dashboard(preview=True)
        d.action(pg.event.Event(pg.VIDEORESIZE,w=960,h=720))
        for key,rect in d.PRESET_RECTS.items():
            point=tuple(round(p*d.scale+o) for p,o in zip(rect.center,d.offset))
            assert d.action(pg.event.Event(pg.MOUSEBUTTONDOWN,button=1,pos=point))=='preset:'+key
        d.draw(DashboardState(preset='balanced',preset_message='Balanced active.'),1)
    finally:pg.quit()



def test_standalone_preset_reuses_one_session_for_all_requests(mocker):
    session=mocker.patch('elegoo_robot_car4.camera_presets.requests.Session').return_value.__enter__.return_value
    session.get.return_value.json.return_value={'quality':10,'framesize':9}
    apply_preset('car.test','balanced')
    assert session.get.call_count==3
    assert session.get.return_value.close.call_count==3


def test_worker_reuses_session_across_preset_selections_and_closes(mocker):
    session=mocker.patch('elegoo_robot_car4.camera_presets.requests.Session').return_value
    thread=mocker.patch('elegoo_robot_car4.camera_presets.Thread')
    apply=mocker.patch('elegoo_robot_car4.camera_presets.apply_preset')
    settings=CameraSettings('car.test')
    for key in ['fast','balanced','drive']:
        assert settings.start(key)
        thread.call_args.kwargs['target']()
        assert settings.poll()==(key,None)
        apply.assert_called_with('car.test',key,session.get,settings._cancel)
    session.close.assert_not_called()
    settings.close()
    session.close.assert_called_once()
    assert not settings.start('balanced')


def test_close_during_worker_defers_session_cleanup(mocker):
    session=mocker.patch('elegoo_robot_car4.camera_presets.requests.Session').return_value
    thread=mocker.patch('elegoo_robot_car4.camera_presets.Thread')
    mocker.patch('elegoo_robot_car4.camera_presets.apply_preset')
    settings=CameraSettings('car.test')
    assert settings.start('fast')
    settings.close()
    session.close.assert_not_called()
    thread.call_args.kwargs['target']()
    session.close.assert_called_once()
    assert not settings.start('drive')



def test_preset_recovers_without_resume_but_never_replays_held_throttle(mocker):
    e=engine();e._GameEngine__dry_run=False
    axes={pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767}
    pad=MagicMock();pad.attached.return_value=True;pad.get_button.return_value=False
    pad.get_axis.side_effect=lambda a:axes.get(a,0)
    e._GameEngine__joysticks={1:pad}
    mocker.patch('pygame.key.get_focused',return_value=True)
    mocker.patch('pygame.display.set_caption')
    e._GameEngine__select_camera_preset('balanced')
    axes.clear()
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__neutral_required and not e._GameEngine__stop_held
    assert e._GameEngine__ui.status=='Changing camera'
    e._GameEngine__ui.preset_pending=False
    axes[pg.CONTROLLER_AXIS_TRIGGERRIGHT]=32767
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__neutral_required
    axes.clear()
    e._GameEngine__handle_analogue_actions()
    assert not e._GameEngine__neutral_required
    assert e._GameEngine__ui.status=='Ready'
    assert all(c.args[:2]==(0,0) for c in e._GameEngine__car.drive_analogue.call_args_list)
    axes[pg.CONTROLLER_AXIS_TRIGGERRIGHT]=32767
    e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__car.drive_analogue.call_args.args[0]>0


def test_preset_does_not_clear_an_explicit_manual_stop():
    e=engine();e._GameEngine__stop_held=True;e._GameEngine__ui.stopped=True
    e._GameEngine__select_camera_preset('drive')
    assert e._GameEngine__stop_held and e._GameEngine__ui.stopped
