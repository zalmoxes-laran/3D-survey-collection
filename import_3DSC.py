import bpy
import os

from bpy.types import Panel
from bpy.types import Operator
from bpy.types import PropertyGroup

from bpy_extras.io_utils import ImportHelper

from bpy.props import (BoolProperty,
                       FloatProperty,
                       IntProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )

from .import_Agisoft_xml import *

from .functions import *

# import points section ----------------------------------------------------------

class OBJECT_OT_IMPORTPOINTS(Operator):
    """Import points as empty objects from a txt file"""
    bl_idname = "import_points.txt"
    bl_label = "ImportPoints"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_test.some_data('INVOKE_DEFAULT')
        return {'FINISHED'}

class ImportCoorPoints(Operator, ImportHelper):
        """Tool to import coordinate points from a txt file"""
        bl_idname = "import_test.some_data"  # important since its how bpy.ops.import_test.some_data is constructed
        bl_label = "Import Coordinate Points"

        # ImportHelper mixin class uses this
        filename_ext = ".txt"

        filter_glob: StringProperty(
                default="*.txt",
                options={'HIDDEN'},
                maxlen=255,  # Max internal buffer length, longer would be clamped.
                ) # type: ignore

        # List of operator properties, the attributes will be assigned
        # to the class instance from the operator settings before calling.
        shift: BoolProperty(
                name="Shift coordinates",
                description="Shift coordinates using the General Shift Value (GSV)",
                default=False,
                ) # type: ignore

        col_name: EnumProperty(
                name="Name",
                description="Column with the name",
                items=(('0', "Column 1", "Column 1"),
                        ('1', "Column 2", "Column 2"),
                        ('2', "Column 3", "Column 3"),
                        ('3', "Column 4", "Column 4")),
                default='0',
                ) # type: ignore

        col_x: EnumProperty(
                name="X",
                description="Column with coordinate X",
                items=(('0', "Column 1", "Column 1"),
                        ('1', "Column 2", "Column 2"),
                        ('2', "Column 3", "Column 3"),
                        ('3', "Column 4", "Column 4")),
                default='1',
                )  # type: ignore

        col_y: EnumProperty(
                name="Y",
                description="Column with coordinate X",
                items=(('0', "Column 1", "Column 1"),
                        ('1', "Column 2", "Column 2"),
                        ('2', "Column 3", "Column 3"),
                        ('3', "Column 4", "Column 4")),
                default='2',
                ) # type: ignore

        col_z: EnumProperty(
                name="Z",
                description="Column with coordinate X",
                items=(('0', "Column 1", "Column 1"),
                        ('1', "Column 2", "Column 2"),
                        ('2', "Column 3", "Column 3"),
                        ('3', "Column 4", "Column 4")),
                default='3',
                )      # type: ignore

        separator: EnumProperty(
                name="separator",
                description="Separator type",
                items=((',', "comma", "comma"),
                        (' ', "space", "space"),
                        (';', "semicolon", "semicolon")),
                default=',',
                ) # type: ignore

        def execute(self, context):
                return self.read_point_data(context, self.filepath, self.shift, self.col_name, self.col_x, self.col_y, self.col_z, self.separator)
       
        def namefile_from_path(self, filepath):
                o_filepath_abs = bpy.path.abspath(filepath)
                o_imagedir, o_filename = os.path.split(o_filepath_abs)
                filename = os.path.splitext(o_filename)[0]
                return filename

        def create_new_col_from_file_name(self, filename):
                newcol = bpy.data.collections.new(filename)
                bpy.context.collection.children.link(newcol)
                return newcol

        def read_point_data(self, context, filepath, shift, name_col, x_col, y_col, z_col, separator):
                print("running read point file...")
                f = open(filepath, 'r', encoding='utf-8')
                #data = f.read()
                arr=f.readlines()  # store the entire file in a variable
                f.close()

                counter = 0

                for p in arr:
                        p0 = p.split(separator)  # use separator variable as separator
                        ItemName = p0[int(name_col)]
                        x_coor = float(p0[int(x_col)])
                        y_coor = float(p0[int(y_col)])
                        z_coor = float(p0[int(z_col)])
                        
                        if shift == True:
                                shift_x = context.scene.BL_x_shift
                                shift_y = context.scene.BL_y_shift
                                shift_z = context.scene.BL_z_shift
                                x_coor = x_coor-shift_x
                                y_coor = y_coor-shift_y
                                z_coor = z_coor-shift_z  

                        # Generate object at x = lon and y = lat (and z = 0 )
                        o = bpy.data.objects.new( ItemName, None )
                        if counter == 0:
                                newcol = self.create_new_col_from_file_name(self.namefile_from_path(filepath))
                                counter += 1

                        newcol.objects.link(o)
                        o.location.x = x_coor
                        o.location.y = y_coor
                        o.location.z = z_coor
                        o.show_name = True

                return {'FINISHED'}

# import multiple objs section ---------------------------------------------------

class ImportMultipleObjs(Operator, ImportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "import_scene.multiple_objs"
    bl_label = "Import multiple OBJ's"
    bl_options = {'PRESET', 'UNDO'}

    # ImportHelper mixin class uses this
    filename_ext = ".obj"

    filter_glob: StringProperty(
            default="*.obj", 
            options={'HIDDEN'},
            ) # type: ignore

    # Selected files
    files: CollectionProperty(type=PropertyGroup) # type: ignore

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    ngons_setting: BoolProperty(
            name="NGons",
            description="Import faces with more than 4 verts as ngons",
            default=True,
            ) # type: ignore
    edges_setting: BoolProperty(
            name="Lines",
            description="Import lines and faces with 2 verts as edge",
            default=True,
            ) # type: ignore
    smooth_groups_setting: BoolProperty(
            name="Smooth Groups",
            description="Surround smooth groups by sharp edges",
            default=True,
            ) # type: ignore

    split_objects_setting: BoolProperty(
            name="Object",
            description="Import OBJ Objects into Blender Objects",
            default=True,
            ) # type: ignore
    split_groups_setting: BoolProperty(
            name="Group",
            description="Import OBJ Groups into Blender Objects",
            default=True,
            ) # type: ignore

    groups_as_vgroups_setting: BoolProperty(
            name="Poly Groups",
            description="Import OBJ groups as vertex groups",
            default=False,
            ) # type: ignore

    image_search_setting: BoolProperty(
            name="Image Search",
            description="Search subdirs for any associated images "
                        "(Warning, may be slow)",
            default=True,
            ) # type: ignore

    split_mode_setting: EnumProperty(
            name="Split",
            items=(('ON', "Split", "Split geometry, omits unused verts"),
                   ('OFF', "Keep Vert Order", "Keep vertex order from file"),
                   ),
            ) # type: ignore

    clamp_size_setting: FloatProperty(
            name="Clamp Size",
            description="Clamp bounds under this value (zero to disable)",
            min=0.0, max=1000.0,
            soft_min=0.0, soft_max=1000.0,
            default=0.0,
            ) # type: ignore
    axis_forward_setting: EnumProperty(
            name="Forward",
            items=(('X', "X Forward", ""),
                   ('Y', "Y Forward", ""),
                   ('Z', "Z Forward", ""),
                   ('-X', "-X Forward", ""),
                   ('-Y', "-Y Forward", ""),
                   ('-Z', "-Z Forward", ""),
                   ),
            default='Y',
            ) # type: ignore

    axis_up_setting: EnumProperty(
            name="Up",
            items=(('X', "X Up", ""),
                   ('Y', "Y Up", ""),
                   ('Z', "Z Up", ""),
                   ('-X', "-X Up", ""),
                   ('-Y', "-Y Up", ""),
                   ('-Z', "-Z Up", ""),
                   ),
            default='Z',
            ) # type: ignore


    enable_shift_coordinates: BoolProperty(
            name="shifting coordinates",
            description="Option to shift large coordinates",
            default=True,
            ) # type: ignore

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(self, "ngons_setting")
        row.prop(self, "edges_setting")

        layout.prop(self, "smooth_groups_setting")

        box = layout.box()
        row = box.row()
        row.prop(self, "split_mode_setting", expand=True)

        row = box.row()
        if self.split_mode_setting == 'ON':
            row.label(text="Split by:")
            row.prop(self, "split_objects_setting")
            row.prop(self, "split_groups_setting")
        else:
            row.prop(self, "groups_as_vgroups_setting")

        #layout = self.layout.column_flow(2)

        row.prop(self, "clamp_size_setting")
        layout.prop(self, "axis_forward_setting")
        layout.prop(self, "axis_up_setting")

        layout.prop(self, "image_search_setting")
        layout.prop(self, "enable_shift_coordinates")
        

    def execute(self, context):

        # Ottieni la versione corrente di Blender
        versione_blender = bpy.app.version

        # La versione è una tupla (major, minor, patch), per esempio (3, 6, 0) per la versione 3.6.0
        major, minor, _ = versione_blender

        # get the folder
        folder = (os.path.dirname(self.filepath))

        if self.enable_shift_coordinates:
                x_shift = context.scene.BL_x_shift
                y_shift = context.scene.BL_y_shift
                z_shift = context.scene.BL_z_shift
        else:
                x_shift = 0.0
                y_shift = 0.0
                z_shift = 0.0               

        # iterate through the selected files
        for i in self.files:
        
                print(i)
                path_to_file = (os.path.join(folder, i.name))

                if major >= 4:
                        # Codice per Blender 4.0 e versioni successive
                        #print("Stai eseguendo Blender versione 4.0 o successiva.")
                        bpy.ops.wm.obj_import(filepath= path_to_file,filter_glob='*.obj;*.mtl', forward_axis = self.axis_forward_setting, up_axis = self.axis_up_setting)#, global_shift_x = x_shift, global_shift_y = y_shift, global_shift_z = z_shift)
                elif major == 3 and minor >= 6:
                        # Codice specifico per Blender 3.6
                        bpy.ops.import_scene.obj(filepath= path_to_file,filter_glob='*.obj;*.mtl', axis_forward = self.axis_forward_setting, axis_up = self.axis_up_setting, use_edges = self.edges_setting, use_smooth_groups = self.smooth_groups_setting, use_split_objects = self.split_objects_setting, use_split_groups = self.split_groups_setting, use_groups_as_vgroups = self.groups_as_vgroups_setting, use_image_search = self.image_search_setting, split_mode = self.split_mode_setting)
                        #print("Stai eseguendo Blender versione 3.6.")
                else:
                        # Codice per versioni precedenti
                        #print("Stai eseguendo una versione di Blender precedente alla 3.6.")
                        pass

                # Imposta la visualizzazione degli oggetti importati a BOUNDS
                imported_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
                for obj in imported_objects:
                        obj.display_type = 'BOUNDS'

        return {'FINISHED'}

# import agisoft xml section ----------------------------------------------------------

class OBJECT_OT_IMPORTAGIXML(Operator):
    """Import cams from an xml file"""
    bl_idname = "import_cams.agixml"
    bl_label = "ImportAgiXML"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_cam.agixml('INVOKE_DEFAULT')
        return {'FINISHED'}

class ImportCamAgiXML(Operator, ImportHelper):
        """Tool to import cams and cams parameters from an Agisoft xml file"""
        bl_idname = "import_cam.agixml"  # important since its how bpy.ops.import_test.some_data is constructed
        bl_label = "Import Agisoft XML cams"

        # ImportHelper mixin class uses this
        filename_ext = ".xml"

        filter_glob: StringProperty(
                default="*.xml",
                options={'HIDDEN'},
                maxlen=255,  # Max internal buffer length, longer would be clamped.
                ) # type: ignore

        # List of operator properties, the attributes will be assigned
        # to the class instance from the operator settings before calling.
        shift: BoolProperty(
                name="Shift coordinates",
                description="Shift coordinates using the General Shift Value (GSV)",
                default=False,
                ) # type: ignore

        allchunks: BoolProperty(
                name="from all chunks",
                description="Import cams from all the chunks",
                default=False,
                ) # type: ignore

        PSchunks: IntProperty(
                name="chunk number",
                default=1,
                description="number of chunk",
                ) # type: ignore


        def execute(self, context):
                return self.read_agixml_data(context, self.filepath, self.shift, self.PSchunks, self.allchunks)


        def read_agixml_data(self, context, filepath, shift, chunk, allchunks):
                print("reading agisoft xml file...")
                load_create_cameras(filepath)
                
                return {'FINISHED'}

class ToolsPanelImport:
    from .__init__ import get_3dsc_bl_info

    bl_3dsc_info = get_3dsc_bl_info()
    devel_version = bl_3dsc_info.get('devel_version', 'Unknown version')

    bl_label = "Importers " +  devel_version
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        obj = context.object

        row = layout.row()
        self.layout.operator("import_points.txt", icon="STICKY_UVS_DISABLE", text='Coordinates')
        row = layout.row()
        self.layout.operator("import_scene.multiple_objs", icon="DUPLICATE", text='Multiple objs')
        row = layout.row()
        self.layout.operator("import_cam.agixml", icon="DUPLICATE", text='Agisoft xml cams')
        
class VIEW3D_PT_Import_ToolBar(Panel, ToolsPanelImport):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_Import_ToolBar"
    bl_context = "objectmode"

classes = [
    VIEW3D_PT_Import_ToolBar,
    OBJECT_OT_IMPORTPOINTS,
    ImportCoorPoints,
    ImportMultipleObjs,
    OBJECT_OT_IMPORTAGIXML,
    ImportCamAgiXML
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
