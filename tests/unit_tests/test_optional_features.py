import subprocess
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from elegoo_robot_car4 import Car
from elegoo_robot_car4 import elegoo_smartcar_control as controller


def test_default_imports_work_when_optional_dependencies_are_blocked():
    script = """
import importlib.abc
import sys

class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'torchvision', 'ultralytics', 'lap', 'scipy', 'pandas', 'matplotlib', 'seaborn'}:
            raise AssertionError('Default startup imported '+fullname)

sys.meta_path.insert(0, BlockOptional())
from elegoo_robot_car4.elegoo_smartcar_control import main
assert 'elegoo_robot_car4.person_follower' not in sys.modules
sys.argv = ['elegoo-smartcar-control', '--version']
main()
"""
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'Version:' in result.stdout


@pytest.mark.parametrize('legacy, arguments, analogue, video', [
    (False, [], True, 'udp'),
    (False, ['--analogue-drive', '--video', 'udp'], True, 'udp'),
    (False, ['--video', 'http'], True, 'http'),
    (True, [], False, 'http'),
    (True, ['--analogue-drive'], True, 'udp'),
])
def test_entry_points_select_expected_modes(mocker, legacy, arguments, analogue, video):
    mocker.patch('sys.argv', ['controller', '--robot-ip', 'test.invalid', *arguments])
    engine = mocker.patch.object(controller, 'GameEngine')
    mocker.patch('pygame.init')
    mocker.patch('pygame.quit')
    (controller.legacy_main if legacy else controller.main)()
    assert engine.call_args.kwargs['analogue_drive'] is analogue
    assert engine.call_args.kwargs['video'] == video
    engine.return_value.__enter__.return_value.run.assert_called_once()


def test_missing_vision_extra_leaves_tracking_disabled(monkeypatch):
    monkeypatch.setitem(sys.modules, 'ultralytics', None)
    with Car(dry_run=True) as car:
        with pytest.raises(RuntimeError, match='--extra vision'):
            car.toggle_vision_tracking()
        assert not car.vision_tracking_is_on
        assert car.track(None) == []


def test_optional_vision_loads_only_on_request(monkeypatch):
    module = ModuleType('ultralytics')
    module.YOLO = MagicMock()
    monkeypatch.setitem(sys.modules, 'ultralytics', module)
    with Car(dry_run=True) as car:
        module.YOLO.assert_not_called()
        car.toggle_vision_tracking()
        car.track('frame')
        module.YOLO.return_value.track.assert_called_once_with('frame')
        car.toggle_vision_tracking()
        module.YOLO.assert_called_once()
        assert not car.vision_tracking_is_on


def test_missing_navigation_extra_fails_before_robot_commands(monkeypatch, mocker):
    monkeypatch.setitem(sys.modules, 'scipy.integrate', None)
    with Car(dry_run=True) as car:
        send = mocker.patch.object(car, '_Car__send_cmd')
        with pytest.raises(RuntimeError, match='--extra navigation'):
            car.turn_by(90)
        send.assert_not_called()


@pytest.mark.parametrize('choice', ['4', '5'])
def test_missing_vision_in_legacy_menu_does_not_enable_autonomy(mocker, capsys, choice):
    engine = controller.GameEngine.__new__(controller.GameEngine)
    engine._GameEngine__car = MagicMock()
    engine._GameEngine__car.vision_tracking_is_on = False
    engine._GameEngine__car.toggle_vision_tracking.side_effect = RuntimeError('Install --extra vision')
    engine._GameEngine__autonomous_mode = False
    engine._GameEngine__run_person_follower = False
    mocker.patch('builtins.input', return_value=choice)
    engine._GameEngine__handle_terminal_input()
    assert not engine._GameEngine__autonomous_mode
    assert not engine._GameEngine__run_person_follower
    assert '--extra vision' in capsys.readouterr().out
