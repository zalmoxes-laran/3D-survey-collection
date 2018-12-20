#'''
# CC-BY-NC 2018 EMANUEL DEMETRESCU
# emanuel.demetrescu@gmail.com

#Created by EMANUEL DEMETRESCU

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#'''

bl_info = {
    "name": "3D Survey Collection",
    "author": "Emanuel Demetrescu",
    "version": (1,4.0),
    "blender": (2, 80, 0),
    "location": "3D View > Toolbox",
    "description": "A collection of tools for 3D Survey activities",
#    "warning": "",
    "wiki_url": "",
#    "tracker_url": "",
    "category": "Tools",
    }


if "bpy" in locals():
    import importlib
    importlib.reload(import_3DSC)
#    importlib.reload(functions)
#    importlib.reload(mesh_helpers)
else:
    import math
    import bpy
    from bpy.props import (
            StringProperty,
            BoolProperty,
            FloatProperty,
            EnumProperty,
            PointerProperty,
            CollectionProperty,
            )
    from bpy.types import (
            AddonPreferences,
            PropertyGroup,
            )

    from . import (
            UI,
            import_3DSC,
            i_points_txt,
            #functions,
            )

# register
##################################

#import traceback


class InterfaceVars(PropertyGroup):
    cc_nodes = EnumProperty(
        items=[
            ('RGB', 'RGB', 'RGB Curve', '', 0),
            ('BC', 'BC', 'Bright/Contrast', '', 1),
            ('HS', 'HS', 'Hue/Saturation', '', 2),
        ],
        default='RGB'
    )


classes = (
    UI.VIEW3D_PT_Import_ToolBar,
    import_3DSC.ImportMultipleObjs,
    import_3DSC.OBJECT_OT_IMPORTPOINTS,
    i_points_txt.ImportCoorPoints,
    InterfaceVars,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

#    bpy.utils.register_class(InterfaceVars)
    bpy.types.WindowManager.interface_vars = bpy.props.PointerProperty(type=InterfaceVars)

    bpy.types.Scene.BL_undistorted_path = StringProperty(
      name = "Undistorted Path",
      default = "",
      description = "Define the root path of the undistorted images",
      subtype = 'DIR_PATH'
      )

    bpy.types.Scene.BL_x_shift = FloatProperty(
      name = "X shift",
      default = 0.0,
      description = "Define the shift on the x axis",
      )

    bpy.types.Scene.BL_y_shift = FloatProperty(
      name = "Y shift",
      default = 0.0,
      description = "Define the shift on the y axis",
      )

    bpy.types.Scene.BL_z_shift = FloatProperty(
      name = "Z shift",
      default = 0.0,
      description = "Define the shift on the z axis",
      )

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
