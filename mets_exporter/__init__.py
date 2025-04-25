"""
3D Survey Collection - METS Metadata Exporter

This module provides METS XML metadata export functionality for the 3D Survey Collection addon.
It allows users to generate standardized METS XML files for 3D models, capturing technical, 
descriptive, rights, and source metadata along with file information.
"""

bl_info = {
    "name": "METS Metadata Exporter",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "3D View > 3DSC panel > METS Export",
    "description": "Export standardized METS metadata XML for 3D models",
    "warning": "",
    "wiki_url": "",
    "category": "3D Survey Collection",
}

# Import necessary modules
import bpy
import importlib
import sys
import os

# Import modules
from . import properties
from . import utils
from . import operators
from . import ui
from . import export

# Function to force reload the modules during development
def force_reload():
    try:
        importlib.reload(properties)
        importlib.reload(utils)
        importlib.reload(operators)
        importlib.reload(ui)
        importlib.reload(export)
    except:
        pass

# Register function
def register():
    # Force reload during development
    force_reload()
    
    # Register the modules
    properties.register()
    utils.register()
    operators.register()
    ui.register()
    export.register()

# Unregister function
def unregister():
    # Unregister the modules in reverse order
    export.unregister()
    ui.unregister()
    operators.unregister()
    utils.unregister()
    properties.unregister()

# Auto-run register when running as an individual script
if __name__ == "__main__":
    register()