import bpy
import os
import subprocess


class GeometryExporterOperator(bpy.types.Operator):
    bl_idname = "object.geometry_exporter"
    bl_label = "Export Geometry"

    # Enum Property
    stage: bpy.props.EnumProperty(
        name="Stage",
        description="Stage to stop at",
        items=[('DECIMATION', "Decimation", ""),
               ('SPLITTING', "Splitting", ""),
               ('TILING', "Tiling", "")],
        default='TILING'
    ) # type: ignore

    divisions: bpy.props.IntProperty(
        name="Divisions",
        description="Number of tile divisions",
        default=2,
        min=1
    ) # type: ignore

    zsplit: bpy.props.BoolProperty(
        name="Split along Z-axis",
        description="Splits along z-axis too",
        default=False
    ) # type: ignore

    lods: bpy.props.IntProperty(
        name="Levels of Details",
        description="How many levels of details",
        default=3,
        min=1
    )

    keeptextures: bpy.props.BoolProperty(
        name="Keep Original Textures",
        description="Keeps original textures",
        default=False
    )

    latitude: bpy.props.FloatProperty(
        name="Latitude",
        description="Latitude of the mesh",
        default=0.0
    )

    longitude: bpy.props.FloatProperty(
        name="Longitude",
        description="Longitude of the mesh",
        default=0.0
    )

    altitude: bpy.props.FloatProperty(
        name="Altitude",
        description="Altitude of the mesh (meters)",
        default=0.0
    )

    scale: bpy.props.FloatProperty(
        name="Scale",
        description="Scale for data if using units other than meters",
        default=1.0
    )

    error: bpy.props.FloatProperty(
        name="Base Error",
        description="Base error for root node",
        default=100.0
    )

    usesystemtemp: bpy.props.BoolProperty(
        name="Use System Temp Folder",
        description="Uses the system temp folder",
        default=False
    )

    keepintermediate: bpy.props.BoolProperty(
        name="Keep Intermediate Files",
        description="Keeps the intermediate files",
        default=False
    ) # type: ignore

    # Metodo execute
    def execute(self, context):
        # Creare un'istanza di GeometryExporter con i parametri necessari
        exporter = GeometryExporter(some_parameters=self.some_operator_property)
        exporter.execute_export()
        return {'FINISHED'}

class GeometryExporter:
    def __init__(self, addon_preferences):
        self.temp_folder = addon_preferences.temp_folder
        self.exe_path = addon_preferences.exe_path

    def duplicate_objects(self):
        duplicated_objects = []
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH':
                obj_copy = obj.copy()
                obj_copy.data = obj.data.copy()
                bpy.context.collection.objects.link(obj_copy)
                duplicated_objects.append(obj_copy)
        return duplicated_objects

    def crop_uv_coordinates(self, obj):
        if obj.data.uv_layers.active is not None:
            for uv_loop in obj.data.uv_layers.active.data:
                for loop_index in range(len(uv_loop.uv)):
                    uv_loop.uv[loop_index] = max(0, min(uv_loop.uv[loop_index], 0.99))

    def export_and_cleanup(self, objects):
        for obj in objects:
            self.crop_uv_coordinates(obj)
            file_path = os.path.join(self.temp_folder, f"{obj.name}.obj")
            bpy.ops.export_scene.obj(filepath=file_path, use_selection=True)
            bpy.data.objects.remove(obj, do_unlink=True)

    def run_exe(self):
        subprocess.run([self.exe_path, self.temp_folder], shell=True)

    def execute(self):
        duplicated_objects = self.duplicate_objects()
        self.export_and_cleanup(duplicated_objects)
        self.run_exe()

class GeometryExporterPanel(bpy.types.Panel):
    bl_label = "3D tiles exporter"
    bl_idname = "OBJECT_PT_geometry_exporter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'

    def draw(self, context):
        layout = self.layout
        operator = layout.operator(GeometryExporterOperator.bl_idname)

        layout.prop(operator, "stage")
        layout.prop(operator, "divisions")
        layout.prop(operator, "zsplit")
        layout.prop(operator, "lods")
        layout.prop(operator, "keeptextures")
        layout.prop(operator, "latitude")
        layout.prop(operator, "longitude")
        layout.prop(operator, "altitude")
        layout.prop(operator, "scale")
        layout.prop(operator, "error")
        layout.prop(operator, "usesystemtemp")
        layout.prop(operator, "keepintermediate")


def register():
    bpy.utils.register_class(GeometryExporterOperator)
    bpy.utils.register_class(GeometryExporterPanel)

def unregister():
    bpy.utils.unregister_class(GeometryExporterOperator)
    bpy.utils.unregister_class(GeometryExporterPanel)

if __name__ == "__main__":
    register()
