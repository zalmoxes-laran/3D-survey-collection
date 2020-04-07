# Report info.

_inform = []

def update(*args):
    _inform[:] = args


def info():
    return tuple(_inform)
