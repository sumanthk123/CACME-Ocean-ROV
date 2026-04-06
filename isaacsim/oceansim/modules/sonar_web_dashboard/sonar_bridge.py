"""Global sonar registry for bridging OceanSim sensors to the web API."""

_registered_sonars = {}
_sonar_params = {}


def register_sonar(name, sonar):
    _registered_sonars[name] = sonar
    _sonar_params[name] = {}


def unregister_sonar(name):
    _registered_sonars.pop(name, None)
    _sonar_params.pop(name, None)


def get_sonar(name):
    return _registered_sonars.get(name)


def list_sonars():
    return list(_registered_sonars.keys())


def get_params(name):
    return _sonar_params.get(name, {})


def set_params(name, params):
    if name in _sonar_params:
        _sonar_params[name].update(params)
