"""Dependencies loaded only when an optional feature is explicitly requested."""


def load_yolo(model_name):
    try:
        from ultralytics import YOLO
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Vision is unavailable. Install the 'vision' extra with "
            "uv sync --extra vision (or pip install '.[vision]') in the repository."
        ) from exc
    return YOLO(model_name)


def navigation_integrator():
    try:
        from scipy.integrate import trapezoid
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Gyro navigation is unavailable. Install the 'navigation' extra with "
            "uv sync --extra navigation (or pip install '.[navigation]') in the repository."
        ) from exc
    return trapezoid
