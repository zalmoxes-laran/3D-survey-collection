import bpy
import os
import re
import math
from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       EnumProperty,
                       CollectionProperty)
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator, Panel

class OBJECT_OT_IMPORTLINKABLEND(Operator):
    """Import linked meshes with LOD suffix from Blender files"""
    bl_idname = "import_linked.lod"
    bl_label = "Import Linked LOD Meshes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_file.linked_lod('INVOKE_DEFAULT')
        return {'FINISHED'}

class ImportLinkedLOD(Operator, ImportHelper):
    """Import linked meshes with LOD suffix from Blender files"""
    bl_idname = "import_file.linked_lod"
    bl_label = "Import Linked LOD"
    bl_options = {'PRESET', 'UNDO'}
    
    # ImportHelper mixin class uses this
    filename_ext = ".blend"
    filter_glob: StringProperty(
        default="*.blend",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # Directory selection option
    directory: StringProperty(
        name="Directory",
        description="Select a directory with Blender files",
        subtype='DIR_PATH',
    )
    
    # Selected files (when selecting multiple files)
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    
    # Import options
    lod_level: EnumProperty(
        name="LOD Level",
        description="Level of Detail to import",
        items=[
            ('0', "LOD0", "Import highest detail meshes (LOD0)"),
            ('1', "LOD1", "Import medium-high detail meshes (LOD1)"),
            ('2', "LOD2", "Import medium detail meshes (LOD2)"),
            ('3', "LOD3", "Import low detail meshes (LOD3)"),
            ('4', "LOD4", "Import lowest detail meshes (LOD4)"),
        ],
        default='2',
    )
    
    recursive: BoolProperty(
        name="Include Subfolders",
        description="Scan subfolders for Blender files",
        default=False,
    )
    
    relative_path: BoolProperty(
        name="Relative Path",
        description="Use relative paths for linked objects",
        default=True,
    )
    
    use_cursor_location: BoolProperty(
        name="Place at Cursor",
        description="Place imported objects at 3D cursor location",
        default=True,
    )
    
    arrange_objects: BoolProperty(
        name="Arrange Objects",
        description="Arrange imported objects in a grid or line",
        default=False,
    )
    
    arrangement_type: EnumProperty(
        name="Arrangement",
        description="How to arrange multiple objects",
        items=[
            ('LINE_X', "Line (X axis)", "Arrange in a line along X axis"),
            ('LINE_Y', "Line (Y axis)", "Arrange in a line along Y axis"),
            ('GRID_XY', "Grid (XY plane)", "Arrange in a grid on XY plane"),
        ],
        default='LINE_X',
    )
    
    spacing: FloatProperty(
        name="Spacing",
        description="Distance between arranged objects",
        default=2.0,
        min=0.1,
        soft_max=10.0,
        unit='LENGTH',
    )
    
    display_bounds: BoolProperty(
        name="Display as Bounds",
        description="Display objects as bounding boxes for better performance",
        default=True,
    )

    remove_lod_suffix_from_object_name: BoolProperty(
        name="Remove _LODx from Object Name",
        description="If enabled, imported object names will have trailing _LODx removed (mesh names are unchanged)",
        default=True,
    )
    
    bounds_threshold: IntProperty(
        name="Bounds Threshold",
        description="Number of objects above which to use bounds display mode",
        default=5,
        min=1,
        max=100,
    )
    
    def draw(self, context):
        layout = self.layout
        
        # LOD selection
        box = layout.box()
        box.label(text="LOD Selection:")
        box.prop(self, "lod_level", expand=True)
        
        # Path options
        box = layout.box()
        box.label(text="Path Options:")
        box.prop(self, "recursive")
        box.prop(self, "relative_path")
        
        # Placement options
        box = layout.box()
        box.label(text="Placement:")
        box.prop(self, "use_cursor_location")
        
        # Arrangement options
        box.prop(self, "arrange_objects")
        if self.arrange_objects:
            row = box.row()
            row.prop(self, "arrangement_type")
            row = box.row()
            row.prop(self, "spacing")
        
        # Display options
        box = layout.box()
        box.label(text="Display Options:")
        box.prop(self, "display_bounds")
        if self.display_bounds:
            box.prop(self, "bounds_threshold")

        box = layout.box()
        box.label(text="Naming:")
        box.prop(self, "remove_lod_suffix_from_object_name")
    
    def execute(self, context):
        def _is_blend_file(path):
            return os.path.isfile(path) and path.lower().endswith('.blend')

        def _normalize_selection_paths():
            normalized_blend_files = []
            skipped_inputs = []

            if self.files and len(self.files) > 0:
                base_dir = os.path.dirname(self.filepath)
                for file_item in self.files:
                    candidate_path = os.path.join(base_dir, file_item.name)
                    if _is_blend_file(candidate_path):
                        normalized_blend_files.append(candidate_path)
                    elif os.path.isdir(candidate_path):
                        normalized_blend_files.extend(self.find_blend_files(candidate_path))
                    else:
                        skipped_inputs.append(candidate_path)
            else:
                path = self.directory if self.directory else self.filepath
                if os.path.isdir(path):
                    normalized_blend_files = self.find_blend_files(path)
                elif _is_blend_file(path):
                    normalized_blend_files = [path]
                else:
                    skipped_inputs.append(path)

            return normalized_blend_files, skipped_inputs

        # Get selected file(s) or directory
        blend_files, skipped_inputs = _normalize_selection_paths()
        if skipped_inputs:
            self.report({'WARNING'}, f"Skipped {len(skipped_inputs)} invalid selection(s) (not .blend files).")
            print("\n=== Linked LOD Skipped Inputs ===")
            for skipped in skipped_inputs:
                print(f"- {skipped}")

        if not blend_files:
            self.report({'WARNING'}, "No valid .blend files found in the selection.")
            return {'CANCELLED'}
        
        # Check how many files will be imported and ask for confirmation if too many
        if len(blend_files) > 5:
            self.report({'WARNING'}, f"Found {len(blend_files)} blend files. This might take a while.")
            # Use confirmation dialog
            bpy.ops.wm.import_linked_lod_confirm_dialog('INVOKE_DEFAULT', 
                                                       num_files=len(blend_files),
                                                       filepath=self.filepath,
                                                       directory=self.directory,
                                                       lod_level=self.lod_level,
                                                       recursive=self.recursive,
                                                       relative_path=self.relative_path,
                                                       use_cursor_location=self.use_cursor_location,
                                                       arrange_objects=self.arrange_objects,
                                                       arrangement_type=self.arrangement_type,
                                                       spacing=self.spacing,
                                                       display_bounds=self.display_bounds,
                                                       bounds_threshold=self.bounds_threshold,
                                                       remove_lod_suffix_from_object_name=self.remove_lod_suffix_from_object_name)
            return {'FINISHED'}
        
        # Proceed with import
        self.import_linked_lod(context, blend_files)
        return {'FINISHED'}
    
    def find_blend_files(self, directory):
        """Find all .blend files in directory (and subdirectories if recursive is True)"""
        blend_files = []
        if self.recursive:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith('.blend'):
                        blend_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(directory):
                if file.lower().endswith('.blend'):
                    blend_files.append(os.path.join(directory, file))
        
        return blend_files
    
    def import_linked_lod(self, context, blend_files):
        """Import linked meshes with LOD suffix from blend files"""
        # Store original cursor location if needed
        original_cursor_location = context.scene.cursor.location.copy()
        lod_suffix = f"LOD{self.lod_level}"
        
        # Initialize variables for arranging objects
        imported_objects = []
        failed_unreadable_files = []
        failed_missing_lod_files = []
        failed_other_errors = []
        processed_files = 0
        
        # Process each blend file
        for file_idx, blend_file in enumerate(blend_files):
            processed_files += 1
            blend_file_label = os.path.basename(os.path.normpath(blend_file))
            if not blend_file_label:
                blend_file_label = blend_file
            try:
                # Make path relative if requested
                if self.relative_path:
                    library_path = bpy.path.relpath(blend_file)
                else:
                    library_path = blend_file
                
                # Link meshes with specific LOD suffix
                try:
                    with bpy.data.libraries.load(library_path, link=True) as (data_from, data_to):
                        # Find meshes with the specified LOD suffix
                        meshes_to_link = [name for name in data_from.meshes if name.endswith(lod_suffix)]

                        if not meshes_to_link:
                            failed_missing_lod_files.append(blend_file_label)
                            continue

                        # Link the found meshes
                        data_to.meshes = meshes_to_link
                except Exception as e:
                    failed_unreadable_files.append((blend_file_label, str(e)))
                    continue
                
                # Create objects for linked meshes
                for mesh in data_to.meshes:
                    if mesh is not None:
                        object_name = mesh.name
                        if self.remove_lod_suffix_from_object_name:
                            object_name = re.sub(r"_LOD\d+$", "", object_name)

                        # Create a new object with the linked mesh
                        obj = bpy.data.objects.new(object_name, mesh)
                        
                        # Link the object to the active collection
                        context.collection.objects.link(obj)
                        
                        # Set display mode if needed
                        if self.display_bounds and len(blend_files) >= self.bounds_threshold:
                            obj.display_type = 'BOUNDS'
                        
                        imported_objects.append(obj)
                
            except Exception as e:
                failed_other_errors.append((blend_file_label, str(e)))
        
        # Arrange objects if needed
        if self.arrange_objects and imported_objects:
            self.arrange_imported_objects(context, imported_objects)
        
        # Place at cursor if needed
        if self.use_cursor_location and imported_objects:
            for obj in imported_objects:
                obj.location = original_cursor_location
        
        # Select all imported objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in imported_objects:
            obj.select_set(True)
        
        if imported_objects:
            context.view_layer.objects.active = imported_objects[0]
            self.report({'INFO'}, f"Successfully imported {len(imported_objects)} objects with {lod_suffix} suffix")
        else:
            self.report({'WARNING'}, f"No objects with {lod_suffix} suffix were imported")

        # Final issues summary for UI and console output
        issues_total = len(failed_unreadable_files) + len(failed_missing_lod_files) + len(failed_other_errors)
        if issues_total > 0:
            self.report(
                {'WARNING'},
                f"Import completed with issues: {len(failed_unreadable_files)} unreadable files, "
                f"{len(failed_missing_lod_files)} files without {lod_suffix}, "
                f"{len(failed_other_errors)} other errors."
            )

            print("\n=== Linked LOD Import Issues ===")
            print(f"Processed files: {processed_files}")

            print(f"\nUnreadable files ({len(failed_unreadable_files)}):")
            for filename, error_msg in failed_unreadable_files:
                print(f"- {filename}: {error_msg}")

            print(f"\nMissing {lod_suffix} ({len(failed_missing_lod_files)}):")
            for filename in failed_missing_lod_files:
                print(f"- {filename}")

            print(f"\nOther errors ({len(failed_other_errors)}):")
            for filename, error_msg in failed_other_errors:
                print(f"- {filename}: {error_msg}")
        
        return {'FINISHED'}
    
    def arrange_imported_objects(self, context, objects):
        """Arrange imported objects in a line or grid"""
        if not objects:
            return
        
        count = len(objects)
        spacing = self.spacing
        
        if self.arrangement_type == 'LINE_X':
            for i, obj in enumerate(objects):
                obj.location.x = i * spacing
        
        elif self.arrangement_type == 'LINE_Y':
            for i, obj in enumerate(objects):
                obj.location.y = i * spacing
        
        elif self.arrangement_type == 'GRID_XY':
            # Calculate grid dimensions
            grid_size = math.ceil(math.sqrt(count))
            
            for i, obj in enumerate(objects):
                if i < count:
                    row = i // grid_size
                    col = i % grid_size
                    obj.location.x = col * spacing
                    obj.location.y = row * spacing


class OBJECT_OT_ImportLinkedLODConfirmDialog(Operator):
    """Confirm importing many linked LOD objects"""
    bl_idname = "wm.import_linked_lod_confirm_dialog"
    bl_label = "Confirm Import"
    
    num_files: IntProperty()
    filepath: StringProperty()
    directory: StringProperty()
    lod_level: StringProperty()
    recursive: BoolProperty()
    relative_path: BoolProperty()
    use_cursor_location: BoolProperty()
    arrange_objects: BoolProperty()
    arrangement_type: StringProperty()
    spacing: FloatProperty()
    display_bounds: BoolProperty()
    bounds_threshold: IntProperty()
    remove_lod_suffix_from_object_name: BoolProperty()
    
    def execute(self, context):
        # Create an instance of ImportLinkedLOD to call its methods
        importer = ImportLinkedLOD.bl_idname
        
        if hasattr(bpy.ops, importer.split('.')[0]) and hasattr(getattr(bpy.ops, importer.split('.')[0]), importer.split('.')[1]):
            op = getattr(getattr(bpy.ops, importer.split('.')[0]), importer.split('.')[1])
            
            # Find all blend files
            if os.path.isdir(self.directory):
                # Directory selected
                blend_files = []
                
                if self.recursive:
                    for root, dirs, files in os.walk(self.directory):
                        for file in files:
                            if file.lower().endswith('.blend'):
                                blend_files.append(os.path.join(root, file))
                else:
                    for file in os.listdir(self.directory):
                        if file.lower().endswith('.blend'):
                            blend_files.append(os.path.join(self.directory, file))
            else:
                # Single file selected
                blend_files = [self.filepath]
            
            # Create a temporary operator and call its import method
            temp_op = ImportLinkedLOD
            temp_op.lod_level = self.lod_level
            temp_op.relative_path = self.relative_path
            temp_op.use_cursor_location = self.use_cursor_location
            temp_op.arrange_objects = self.arrange_objects
            temp_op.arrangement_type = self.arrangement_type
            temp_op.spacing = self.spacing
            temp_op.display_bounds = self.display_bounds
            temp_op.bounds_threshold = self.bounds_threshold
            temp_op.remove_lod_suffix_from_object_name = self.remove_lod_suffix_from_object_name
            
            temp_op.import_linked_lod(temp_op, context, blend_files)
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Found {self.num_files} Blender files.")
        layout.label(text="This operation might take a while.")
        layout.label(text="Do you want to continue?")


class DXF_PT_ImportLinkedLODPanel(Panel):
    """Panel for importing linked LOD meshes from Blender files"""
    bl_label = "Linked LOD Import"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_parent_id = "VIEW3D_PT_Import_ToolBar"  # Connection to the Importers panel
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return True
    
    def draw(self, context):
        layout = self.layout
        
        # Main import button
        row = layout.row(align=True)
        row.operator("import_linked.lod", icon="IMPORT", text="Import Linked LOD Meshes")
        op = row.operator("e3dsc.help_popup", text="", icon='QUESTION')
        op.title = "Linked LOD Import"
        op.text = (
            "Import linked meshes with LOD suffix from .blend files. "
            "Use this to assemble scenes efficiently from external LOD libraries."
        )
        op.url = "3DSCstructure.html#importers"
        
        # Brief explanation
        box = layout.box()
        col = box.column()
        col.label(text="Import linked meshes with LOD suffix")
        col.label(text="from Blender files (.blend)")
        col.label(text="Use for efficient scene assembly")


# Registration

classes = (
    OBJECT_OT_IMPORTLINKABLEND,
    ImportLinkedLOD,
    OBJECT_OT_ImportLinkedLODConfirmDialog,
    DXF_PT_ImportLinkedLODPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
