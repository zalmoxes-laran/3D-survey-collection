#'''
# CC-BY-NC 2024 EMANUEL DEMETRESCU
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
    "version": (1,6,1),
    "blender": (4, 2, 0),
    "location": "3D View > Toolbox",
    "description": "A collection of tools for 3D Survey activities",
    #"warning": "Alpha version of 1.6.1 3DSC dev4",
    "wiki_url": "",
    "devel_version": " 3DSC 1.6.1",  # Aggiunto campo devel_version
    "category": "Tools",
    }

def get_3dsc_bl_info():
    return bl_info

if "bpy" in locals():
    import importlib
    importlib.reload(import_3DSC)

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
            segmentation,
            LODgenerator,
            ccTool,
            PhotogrTool,
            TexPatcher,
            PanoramaSuite,
            report_data,
            addon_updater_ops,
            qualitycheck,
            external_modules_install,
            multimesh_manager,
            realitycapture,
            cesium_preprocessing
            )
    
    from .exporter_cesium import export_tile_model

from .external_modules_install import check_external_modules

# demo bare-bones preferences
@addon_updater_ops.make_annotations


class DemPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    # addon updater preferences

    # Path to file .exe
    exe_path: bpy.props.StringProperty(
        name="Path to .exe File",
        description="Path to the .exe file used by the exporter",
        subtype='FILE_PATH'
    ) # type: ignore # type: ignore

    auto_check_update : bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=False
                ) # type: ignore
    is_external_module : bpy.props.BoolProperty(
        name="Py3dtiles module (to convert cesium tiled files) is present",
        default=False
                ) # type: ignore # type: ignore
    updater_intrval_months : bpy.props.IntProperty(
        name='Months',
        description="Number of months between checking for updates",
        default=0,
        min=0
                ) # type: ignore
    updater_intrval_days : bpy.props.IntProperty(
        name='Days',
        description="Number of days between checking for updates",
        default=7,
        min=0,
        max=31
                ) # type: ignore
    updater_intrval_hours : bpy.props.IntProperty(
        name='Hours',
        description="Number of hours between checking for updates",
        default=0,
        min=0,
        max=23
                ) # type: ignore
    updater_intrval_minutes : bpy.props.IntProperty(
        name='Minutes',
        description="Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59
                ) # type: ignore
    def draw(self, context):
        layout = self.layout
        # col = layout.column() # works best if a column, or even just self.layout
        mainrow = layout.row()
        col = mainrow.column()
        # updater draw function
        # could also pass in col as third arg
        addon_updater_ops.update_settings_ui(self, context)
        # Alternate draw function, which is more condensed and can be
        # placed within an existing draw function. Only contains:
        #   1) check for update/update now buttons
        #   2) toggle for auto-check (interval will be equal to what is set above)
        # addon_updater_ops.update_settings_ui_condensed(self, context, col)
        # Adding another column to help show the above condensed ui as one column
        # col = mainrow.column()
        # col.scale_y = 2
        # col.operator("wm.url_open","Open webpage ").url=addon_updater_ops.updater.website
        layout = self.layout
        layout.label(text="Path to Obj2Tiles.exe")
        layout.prop(self, "exe_path")
        layout = self.layout
        layout.label(text="Export cesium tiles setup")
        #layout.prop(self, "filepath", text="Credentials path:")
        if self.is_external_module:
                layout.label(text="Py3dtiles module (to convert 3d tiles) is correctly installed")
        else:
                layout.label(text="Py3dtiles module is missing: install with the button below")
        row = layout.row()              
        op = row.operator("install_3dsc_missing.modules", icon="STICKY_UVS_DISABLE", text='Install Py3dtiles modules (waiting some minutes is normal)')
        op.is_install = True
        op.list_modules_to_install = "py3dtiles"
        row = layout.row()
        op = row.operator("install_3dsc_missing.modules", icon="STICKY_UVS_DISABLE", text='Uninstall Py3dtiles modules (waiting some minutes is normal)')
        op.is_install = False
        op.list_modules_to_install = "py3dtiles"

class RES_list(PropertyGroup):
    """ List of resolutions """

    res_num : IntProperty(
            name="Resolution",
            description="Resolution number",
            default=1) # type: ignore

class CAMTypeList(PropertyGroup):
    """ List of cameras """

    name_cam : StringProperty(
            name="Name",
            description="A name for this item",
            default="Untitled") # type: ignore

class AnalysisListItem(PropertyGroup):
    """ Group of properties representing an item in the list """

    res_tex : IntProperty(
            name = "Res",
            default = 0,
            description = "Resolution of Image Texture") # type: ignore

    res_counter : IntProperty(
            name = "Number of instances",
            default = 0,
            description = "Number of instances for a given resolution") # type: ignore

class StatisticsListItem(PropertyGroup):
    """ Group of properties representing an item in the list """

    name : StringProperty(
            name="Name",
            description="Name of the object",
            default="Untitled") # type: ignore

    context_col : StringProperty(
            name="context_col",
            description="Name of the context",
            default="Untitled") # type: ignore

    tiles_num : IntProperty(
            name = "Tiles",
            default = 0,
            description = "Number of tiles")     # type: ignore

    area_mesh : FloatProperty(
            name = "Area",
            default = 0, # type: ignore
            description = "Area of mesh")

    poly_num : IntProperty(
            name = "Polygons",
            default = 0,
            description = "Number of polygons") # type: ignore
    
    poly_res : FloatProperty(
            name = "Polyres",
            default = 0,
            description = "Area of mesh") # type: ignore

    res_tex : IntProperty(
            name = "Res",
            default = 0,
            description = "Resolution of Image Texture") # type: ignore

    res_counter : IntProperty(
            name = "Number of instances",
            default = 0,
            description = "Number of instances for a given resolution") # type: ignore
    
    uv_ratio : FloatProperty(
            name = "UVratio",
            default = 0.6,
            description = "Ratio coverage for UV") # type: ignore
    
    mean_res_tex : FloatProperty(
            name = "meanrestex",
            default = 0.0,
            description = "Mean texture resolution of this group") # type: ignore

class PANOListItem(PropertyGroup):
    """ Group of properties representing an item in the list """

    name : StringProperty(
            name="Name",
            description="A name for this item",
            default="Untitled") # type: ignore

    icon : StringProperty(
            name="code for icon",
            description="",
            default="GROUP_UVS") # type: ignore

    resol_pano : IntProperty(
            name = "Res",
            default = 1,
            description = "Resolution of Panoramic image for this bubble") # type: ignore

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
    ) # type: ignore

class SuffixVars(PropertyGroup):
    suffixnum: EnumProperty(
        items=[
            ('.001', '.001', '.001', '', 0),
            ('.002', '.002', '.002', '', 1),
            ('.003', '.003', '.003', '', 2),
        ],
        default='.001'
    ) # type: ignore

class ccToolViewVar(PropertyGroup):
    cc_view: EnumProperty(
        items=[
            ('original', 'original', 'original texture', '', 0),
            ('cc_node', 'cc_node', 'dynamic editing', '', 1),
            ('cc_image', 'cc_image', 'final texture', '', 2),
        ],
        default='cc_node'
    ) # type: ignore

class LODitemListItem(PropertyGroup):
    """ Group of properties representing an item in the list """

    name : StringProperty(
            name="object",
            description="object name",
            default="Untitled") # type: ignore

    libreria_lod : StringProperty(
            name="library",
            description="library name",
            default="Untitled") # type: ignore

classes = (
    UI.VIEW3D_PT_Export_ToolBar,
    UI.VIEW3D_PT_QuickUtils_ToolBar,
    UI.VIEW3D_PT_segmentation_pan,
    UI.VIEW3D_PT_ccTool,
    UI.Res_menu,
    UI.VIEW3D_PT_TexPatcher,
    # UI.VIEW3D_PT_SetupPanel,
    UI.VIEW3D_PT_mesh_analyze,
    export_3DSC.ExportCoordinates,
    export_3DSC.OBJECT_OT_exportbatch,
    export_3DSC.OBJECT_OT_ExportButtonName,
    export_3DSC.OBJECT_OT_ExportObjButton,
    export_3DSC.OBJECT_OT_fbxexp,
    export_3DSC.OBJECT_OT_fbxexportbatch,
    export_3DSC.OBJECT_OT_objexportbatch,
    #export_3DSC.OBJECT_OT_osgtexportbatch,
    export_3DSC.OBJECT_OT_gltfexportbatch,
    export_3DSC.OBJECT_OT_glbexportbatch,
    segmentation.OBJECT_OT_projectsegmentation,
    segmentation.OBJECT_OT_projectsegmentationinversed,
    segmentation.OBJECT_OT_setcutter,
    QuickUtils.OBJECT_OT_activatematerial,
    #QuickUtils.OBJECT_OT_CenterMass,
    QuickUtils.OBJECT_OT_CorrectMaterial,
    QuickUtils.OBJECT_OT_createpersonalgroups,
    QuickUtils.OBJECT_OT_cycles2bi,
    QuickUtils.OBJECT_OT_deactivatematerial,
    QuickUtils.OBJECT_OT_lightoff,
    QuickUtils.OBJECT_OT_LocalTexture,
    QuickUtils.OBJECT_OT_LOD0polyreducer,
    QuickUtils.OBJECT_OT_multimateriallayout,
    QuickUtils.OBJECT_OT_objectnamefromfilename,
    QuickUtils.OBJECT_OT_removealluvexcept1,
    QuickUtils.OBJECT_OT_removefromallgroups,
    QuickUtils.OBJECT_OT_renameGEobject,
    QuickUtils.OBJECT_OT_tiff2pngrelink,
    QuickUtils.OBJECT_OT_circumcenter,
    QuickUtils.OBJECT_OT_remove_suffixnumber,
    QuickUtils.OBJECT_OT_setmaterial_blend,
    QuickUtils.OBJECT_OT_diffuseprincipled,
    QuickUtils.OBJECT_OT_setroughness,
    QuickUtils.OBJECT_OT_setmetalness,
    QuickUtils.OBJECT_OT_invertcoordinates,
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
    SuffixVars,
    ccToolViewVar,
    PanoramaSuite.REMOVE_pano,
    PanoramaSuite.VIEW_pano,
    PanoramaSuite.VIEW_alignquad,
    PanoramaSuite.VIEW_setlens,
    PanoramaSuite.PANO_import,
    PanoramaSuite.ubermat_create,
    PanoramaSuite.ubermat_update,
    PanoramaSuite.SETpanoRES,
    qualitycheck.MESH_OT_info_area,
    qualitycheck.MESH_OT_info_texs,
    qualitycheck.MESH_OT_info_texres,
    qualitycheck.ExportStatistics,
    PANO_UL_List,
    PANOListItem,
    CAMTypeList,
    RES_list,
    LODitemListItem,
    DemPreferences,
    AnalysisListItem,
    StatisticsListItem,
)

def register():

    addon_updater_ops.register(bl_info)
    import_3DSC.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    functions.register()
    shift.register()
    external_modules_install.register()
    export_3DSC.register()
    #exporter_cesium.export_tile_model.register()
    PhotogrTool.register()
    multimesh_manager.register()
    #realitycapture.register()
    
    #cesium_preprocessing.register()

    LODgenerator.register()

    check_external_modules()
    bpy.types.WindowManager.interface_vars = bpy.props.PointerProperty(type=InterfaceVars)
    bpy.types.WindowManager.ccToolViewVar = bpy.props.PointerProperty(type=ccToolViewVar)
    bpy.types.WindowManager.suffix_num = bpy.props.PointerProperty(type=SuffixVars)  

    #def initSceneProperties(scn):


    bpy.types.Scene.SHIFT_OBJ_on = BoolProperty(
        name = "Shifting obj export",
        default = False,
        description = "Shifting obj export: slow with big models"
        )

    bpy.types.Scene.collgerarchy_to_foldtree = BoolProperty(
        name = "Use collection gerarchy",
        default = False,
        description = "Collection gerarchy will be used to create a tree of subfolders (usefull for GE like Unreal)"
        )

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

    bpy.types.Scene.author_sign_model = StringProperty(
      name = "Credits of the model",
      default = "",
      description = "Define the author of the exported models (only gltf, glb)",
      )

    bpy.types.Scene.instanced_export = BoolProperty(
        name="Enable instances export",
        default=False,
        description="Enable instances export: select a group of objects and it will generate a single file [name]-inst.txt using the name of the active object."
    )

    bpy.types.Scene.info_log = []

# panoramic
    bpy.types.Scene.camera_list = CollectionProperty(type = CAMTypeList)
    bpy.types.Scene.resolution_list = CollectionProperty(type = RES_list)
    bpy.types.Scene.pano_list = CollectionProperty(type = PANOListItem)
    bpy.types.Scene.pano_list_index = IntProperty(name = "Index for my_list", default = 0)
    bpy.types.Scene.lod_list_item = CollectionProperty(type = LODitemListItem)
    bpy.types.Scene.analysis_list = CollectionProperty(type = AnalysisListItem)
    bpy.types.Scene.statistics_list = CollectionProperty(type = StatisticsListItem)

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

    bpy.types.Scene.model_export_dir = StringProperty(
    name = "Export folder",
    default = "",
    description = "Define the path to the export folder",
    subtype = 'DIR_PATH'
    )


    bpy.types.Scene.TILE_square_meters = IntProperty(
    name="Tile square meters",
    default=100,
    description="Define the area of the tiles",
    )

    bpy.types.Scene.gltf_export_quality = IntProperty(
    name="export quality",
    default=100,
    description="Define the quality of the output images",
    )

    bpy.types.Scene.gltf_export_maxres = IntProperty(
    name="export max resolution",
    default=2048,
    description="Define the resolution of the output images",
    )

    
def unregister():

    addon_updater_ops.unregister(bl_info)
    shift.unregister()
    for cls in classes:
        try:
                bpy.utils.unregister_class(cls)
        except RuntimeError:
                pass
        
    import_3DSC.unregister()
    external_modules_install.unregister()
    export_3DSC.unregister()
    PhotogrTool.unregister()
    #exporter_cesium.export_tile_model.unregister()
    multimesh_manager.unregister()
    #realitycapture.unregister()
    functions.unregister()
    #cesium_preprocessing.unregister()
    LODgenerator.unregister()


    del bpy.types.WindowManager.interface_vars
    del bpy.types.WindowManager.suffix_num
    del bpy.types.WindowManager.ccToolViewVar

    del bpy.types.Scene.BL_undistorted_path

    del bpy.types.Scene.RES_pano
    del bpy.types.Scene.camera_type
    del bpy.types.Scene.camera_lens
    del bpy.types.Scene.pano_list
    del bpy.types.Scene.pano_list_index
    del bpy.types.Scene.PANO_file
    del bpy.types.Scene.PANO_dir
    del bpy.types.Scene.PANO_cam_lens
    del bpy.types.Scene.lod_list_item
    del bpy.types.Scene.analysis_list
    del bpy.types.Scene.statistics_list
    del bpy.types.Scene.model_export_dir
    del bpy.types.Scene.TILE_square_meters
    del bpy.types.Scene.SHIFT_OBJ_on
    del bpy.types.Scene.author_sign_model
    del bpy.types.Scene.gltf_export_quality
    del bpy.types.Scene.gltf_export_maxres
    del bpy.types.Scene.instanced_export
    del bpy.types.Scene.collgerarchy_to_foldtree
