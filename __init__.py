#'''
# CC-BY-NC 2018 EMANUEL DEMETRESCU
# emanuel.demetrescu@gmail.com

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
    "version": (1,4.4),
    "blender": (2, 81, 0),
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
    import bpy.props as prop

    from bpy.props import (
            StringProperty,
            BoolProperty,
            FloatProperty,
            EnumProperty,
            IntProperty,
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
            import_Agisoft_xml,
            export_3DSC,
            functions,
            shift,
            QuickUtils,
            LODgenerator,
            ccTool,
            PhotogrTool,
            TexPatcher,
            PanoramaSuite,
            )

class RES_list(PropertyGroup):
    """ List of resolutions """

    res_num : IntProperty(
            name="Resolution",
            description="Resolution number",
            default=1)

class CAMTypeList(PropertyGroup):
    """ List of cameras """

    name_cam : StringProperty(
            name="Name",
            description="A name for this item",
            default="Untitled")

class PANOListItem(PropertyGroup):
    """ Group of properties representing an item in the list """

    name : StringProperty(
            name="Name",
            description="A name for this item",
            default="Untitled")

    icon : StringProperty(
            name="code for icon",
            description="",
            default="GROUP_UVS")

    resol_pano : IntProperty(
            name = "Res", 
            default = 1,
            description = "Resolution of Panoramic image for this bubble")
                    
class PANO_UL_List(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, resol_pano, index):
        #scene = context.scene
        layout.label(text = item.name, icon = item.icon)

class InterfaceVars(PropertyGroup):
    cc_nodes: EnumProperty(
        items=[
            ('RGB', 'RGB', 'RGB Curve', '', 0),
            ('BC', 'BC', 'Bright/Contrast', '', 1),
            ('HS', 'HS', 'Hue/Saturation', '', 2),
        ],
        default='RGB'
    )

class ccToolViewVar(PropertyGroup):
    cc_view: EnumProperty(
        items=[
            ('original', 'original', 'original texture', '', 0),
            ('cc_node', 'cc_node', 'dynamic editing', '', 1),
            ('cc_image', 'cc_image', 'final texture', '', 2),
        ],
        default='cc_node'
    )

classes = (
    UI.VIEW3D_PT_Shift_ToolBar,
    UI.VIEW3D_PT_Import_ToolBar,
    UI.VIEW3D_PT_Export_ToolBar,
    UI.VIEW3D_PT_QuickUtils_ToolBar,
    UI.VIEW3D_PT_LODgenerator,
    UI.VIEW3D_PT_ccTool,
    UI.VIEW3D_PT_PhotogrTool,
    UI.Camera_menu,
    UI.Res_menu,
    UI.VIEW3D_PT_TexPatcher,
    UI.VIEW3D_PT_SetupPanel,
    import_3DSC.ImportMultipleObjs,
    import_3DSC.OBJECT_OT_IMPORTPOINTS,
    import_3DSC.ImportCoorPoints,
    export_3DSC.ExportCoordinates,
    import_3DSC.OBJECT_OT_IMPORTAGIXML,
    import_3DSC.ImportCamAgiXML,
    export_3DSC.OBJECT_OT_ExportButtonName,
    export_3DSC.OBJECT_OT_ExportObjButton,
    export_3DSC.OBJECT_OT_fbxexp,
    export_3DSC.OBJECT_OT_fbxexportbatch,
    export_3DSC.OBJECT_OT_objexportbatch,
    export_3DSC.OBJECT_OT_osgtexportbatch,
    functions.OBJECT_OT_createcyclesmat,
    functions.OBJECT_OT_savepaintcam,
    shift.OBJECT_OT_IMPORTPOINTS,
    QuickUtils.OBJECT_OT_activatematerial,
    QuickUtils.OBJECT_OT_CenterMass,
    QuickUtils.OBJECT_OT_CorrectMaterial,
    QuickUtils.OBJECT_OT_createpersonalgroups,
    QuickUtils.OBJECT_OT_cycles2bi,
    QuickUtils.OBJECT_OT_deactivatematerial,
    QuickUtils.OBJECT_OT_lightoff,
    QuickUtils.OBJECT_OT_LocalTexture,
    QuickUtils.OBJECT_OT_LOD0polyreducer,
    QuickUtils.OBJECT_OT_multimateriallayout,
    QuickUtils.OBJECT_OT_objectnamefromfilename,
    QuickUtils.OBJECT_OT_projectsegmentation,
    QuickUtils.OBJECT_OT_projectsegmentationinversed,
    QuickUtils.OBJECT_OT_removealluvexcept1,
    QuickUtils.OBJECT_OT_removefromallgroups,
    QuickUtils.OBJECT_OT_renameGEobject,
    QuickUtils.OBJECT_OT_tiff2pngrelink,
    QuickUtils.OBJECT_OT_circumcenter,
    LODgenerator.OBJECT_OT_CreateGroupsLOD,
    LODgenerator.OBJECT_OT_ExportGroupsLOD,
    LODgenerator.OBJECT_OT_LOD,
    LODgenerator.OBJECT_OT_LOD0,
    LODgenerator.OBJECT_OT_RemoveGroupsLOD,
    PhotogrTool.OBJECT_OT_applypaintcam,
    PhotogrTool.OBJECT_OT_BetterCameras,
    PhotogrTool.OBJECT_OT_NoBetterCameras,
    PhotogrTool.OBJECT_OT_paintcam,
    PhotogrTool.OBJECT_OT_CreateCameraImagePlane,
    PhotogrTool.XML_CAM_parse,
    PhotogrTool.set_camera_type,
    ccTool.OBJECT_OT_createccsetup,
    ccTool.OBJECT_OT_bakecyclesdiffuse,
    ccTool.OBJECT_OT_removeccsetup,
    ccTool.OBJECT_OT_applyccsetup,
    ccTool.OBJECT_OT_setccview,
    TexPatcher.OBJECT_OT_applyoritexset,
    TexPatcher.OBJECT_OT_applysptexset,
    TexPatcher.OBJECT_OT_exitsetup,
    TexPatcher.OBJECT_OT_paintsetup,
    TexPatcher.OBJECT_OT_removepaintsetup,
    TexPatcher.OBJECT_OT_textransfer,
    InterfaceVars,
    ccToolViewVar,
    PanoramaSuite.REMOVE_pano,
    PanoramaSuite.VIEW_pano,
    PanoramaSuite.VIEW_alignquad,
    PanoramaSuite.VIEW_setlens,
    PanoramaSuite.PANO_import,
    PanoramaSuite.ubermat_create,
    PanoramaSuite.ubermat_update,
    PanoramaSuite.SETpanoRES,
    PANO_UL_List,
    PANOListItem,
    CAMTypeList,
    RES_list,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.WindowManager.interface_vars = bpy.props.PointerProperty(type=InterfaceVars)
    bpy.types.WindowManager.ccToolViewVar = bpy.props.PointerProperty(type=ccToolViewVar)


#def initSceneProperties(scn):
    bpy.types.Scene.LODnum = IntProperty(
        name = "LODs", 
        default = 1,
        min = 1,
        max = 3,
        description = "Enter desired number of LOD (Level of Detail)")
    
    bpy.types.Scene.LOD1_tex_res = IntProperty(
        name = "Resolution Texture of the LOD1", 
        default = 2048,
        description = "Enter the resolution for the texture of the LOD1")

    bpy.types.Scene.LOD2_tex_res = IntProperty(
        name = "Resolution Texture of the LOD2", 
        default = 512,
        description = "Enter the resolution for the texture of the LOD2")

    bpy.types.Scene.LOD3_tex_res = IntProperty(
        name = "Resolution Texture of the LOD3", 
        default = 128,
        description = "Enter the resolution for the texture of the LOD3")

    bpy.types.Scene.LOD1_dec_ratio = FloatProperty(
        name = "LOD1 decimation ratio",
        default = 0.5,
        description = "Define the decimation ratio of the LOD 1",
        )    
    
    bpy.types.Scene.LOD2_dec_ratio = FloatProperty(
        name = "LOD2 decimation ratio",
        default = 0.1,
        description = "Define the decimation ratio of the LOD 2",
        )    

    bpy.types.Scene.LOD3_dec_ratio = FloatProperty(
        name = "LOD3 decimation ratio",
        default = 0.035,
        description = "Define the decimation ratio of the LOD 3",
        )

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

    bpy.types.Scene.RES_pano = IntProperty(
        name = "Res", 
        default = 1,
        description = "Resolution of Panoramic image for bubbles")
    
    bpy.types.Scene.camera_type = StringProperty(
        name = "Camera type",
        default = "Not set",
        description = "Current camera type"
        )

    bpy.types.Scene.camera_lens = IntProperty(
        name = "Camera Lens",
        default = 35,
        description = "Lens camera",
        )

# panoramic
    bpy.types.Scene.camera_list = CollectionProperty(type = CAMTypeList)
    bpy.types.Scene.resolution_list = CollectionProperty(type = RES_list)
    bpy.types.Scene.pano_list = CollectionProperty(type = PANOListItem)
    bpy.types.Scene.pano_list_index = IntProperty(name = "Index for my_list", default = 0)

    bpy.types.Scene.PANO_file = StringProperty(
    name = "TXT",
    default = "",
    description = "Define the path to the PANO file",
    subtype = 'FILE_PATH'
    )

    bpy.types.Scene.PANO_dir = StringProperty(
    name = "DIR",
    default = "",
    description = "Define the path to the PANO file",
    subtype = 'DIR_PATH'
    )

    bpy.types.Scene.PANO_cam_lens = IntProperty(
    name = "Cam Lens",
    default = 21,
    description = "Define the lens of the cameras",
    )

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.WindowManager.interface_vars
    del bpy.types.WindowManager.ccToolViewVar
    del bpy.types.Scene.LODnum
    del bpy.types.Scene.LOD1_tex_res
    del bpy.types.Scene.LOD2_tex_res
    del bpy.types.Scene.LOD3_tex_res
    del bpy.types.Scene.LOD1_dec_ratio
    del bpy.types.Scene.LOD2_dec_ratio
    del bpy.types.Scene.LOD3_dec_ratio
    del bpy.types.Scene.BL_undistorted_path
    del bpy.types.Scene.BL_x_shift
    del bpy.types.Scene.BL_y_shift
    del bpy.types.Scene.BL_z_shift
    del bpy.types.Scene.RES_pano
    del bpy.types.Scene.camera_type
    del bpy.types.Scene.camera_lens
    del bpy.types.Scene.pano_list
    del bpy.types.Scene.pano_list_index
    del bpy.types.Scene.PANO_file
    del bpy.types.Scene.PANO_dir
    del bpy.types.Scene.PANO_cam_lens