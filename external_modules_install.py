"""Bundled-dependency status for 3DSC.

As a Blender extension, 3DSC ships its required Python dependencies as wheels
declared in ``blender_manifest.toml`` (ezdxf, pyproj and their pure-Python
deps). Blender installs them into the extension environment at enable time, so
there is no runtime ``pip install`` anymore (the old subprocess-based installer
and ``blender_pip`` helper have been removed).

This module now only reports whether the bundled dependencies import correctly,
exposing the result through the ``is_external_module`` add-on preference, which
a few operator ``poll()`` methods still consult.
"""

import bpy

import logging
log = logging.getLogger(__name__)

# Dependencies bundled as wheels in the extension manifest.
BUNDLED_MODULES = ("ezdxf", "pyproj")


def check_external_modules():
    """Set the ``is_external_module`` preference from bundled-dependency status."""
    addon_prefs = bpy.context.preferences.addons.get(__package__, None)
    if addon_prefs is None:
        return

    available = True
    for module_name in BUNDLED_MODULES:
        try:
            __import__(module_name)
        except ImportError:
            available = False
            log.warning("3DSC: bundled dependency '%s' is not importable", module_name)

    addon_prefs.preferences.is_external_module = available
    if available:
        log.info("3DSC: bundled dependencies are available")


# No operators to register anymore (runtime pip install removed). The empty
# list keeps register()/unregister() valid so __init__ can call them unchanged.
classes = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
