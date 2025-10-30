# type: ignore

import bpy
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy.props import (FloatProperty, BoolProperty, EnumProperty, 
                       StringProperty, CollectionProperty, IntProperty, PointerProperty)
import bmesh
from mathutils import Matrix, Vector

# =====================================================================
# PROPERTY GROUPS
# =====================================================================

class TSM_ListItem(PropertyGroup):
    """Property group for TSM list items"""
    
    name: StringProperty(
        name="TSM Name",
        description="Name of the TSM system",
        default="TSM"
    ) # type: ignore
    
    obj_name: StringProperty(
        name="Object Name",
        description="Name of the TSM empty object in scene",
        default=""
    ) # type: ignore
    
    description: StringProperty(
        name="Description",
        description="Description for this TSM system",
        default="New TSM System",
        update=lambda self, context: update_tsm_description(self, context)
    ) # type: ignore


def update_tsm_description(self, context):
    """Update the custom property when description changes"""
    if self.obj_name in bpy.data.objects:
        obj = bpy.data.objects[self.obj_name]
        obj["tsm_description"] = self.description


def get_uv_layers(self, context):
    """Dynamic enum for UV layers"""
    items = [("NONE", "-- Select UV Layer --", "")]
    
    obj = context.active_object
    if obj and obj.type == 'MESH' and obj.data.uv_layers:
        for i, uv_layer in enumerate(obj.data.uv_layers):
            items.append((uv_layer.name, uv_layer.name, f"UV Layer: {uv_layer.name}"))
    
    return items


# =====================================================================
# OPERATORS
# =====================================================================

class OBJECT_OT_refresh_tsm_list(Operator):
    """Refresh the list of TSM systems in scene"""
    bl_idname = "object.refresh_tsm_list"
    bl_label = "Refresh TSM List"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        refresh_tsm_list(context)
        self.report({'INFO'}, "TSM list refreshed")
        return {'FINISHED'}


def refresh_tsm_list(context):
    """Scan scene for TSM systems and populate the list"""
    tsm_list = context.scene.tsm_list
    tsm_list.clear()
    
    for obj in bpy.data.objects:
        if obj.type == 'EMPTY' and obj.get("tsm_system") == True:
            item = tsm_list.add()
            item.name = obj.name
            item.obj_name = obj.name
            item.description = obj.get("tsm_description", "New TSM System")


class OBJECT_OT_select_tsm(Operator):
    """Select the TSM object in the scene"""
    bl_idname = "object.select_tsm"
    bl_label = "Select TSM"
    bl_options = {'REGISTER', 'UNDO'}
    
    tsm_name: StringProperty() # type: ignore

    def execute(self, context):
        if self.tsm_name in bpy.data.objects:
            obj = bpy.data.objects[self.tsm_name]
            
            # Check if object is in view layer
            if obj.name in context.view_layer.objects:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                self.report({'INFO'}, f"Selected {self.tsm_name}")
            else:
                self.report({'WARNING'}, f"{self.tsm_name} is not visible in current view layer")
        else:
            self.report({'ERROR'}, f"TSM {self.tsm_name} not found in scene")
        
        return {'FINISHED'}


class OBJECT_OT_add_uv_map(Operator):
    """Add a new UV map to the active mesh object"""
    bl_idname = "object.add_tsm_uv_map"
    bl_label = "Add New UV Map"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_name: StringProperty(
        name="UV Map Name",
        description="Name for the new UV map",
        default="TSM_UVMap"
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        mesh_obj = context.active_object
        
        # Check if name already exists
        if self.uv_name in mesh_obj.data.uv_layers:
            self.report({'WARNING'}, f"UV map '{self.uv_name}' already exists")
            return {'CANCELLED'}
        
        # Add new UV map
        new_uv = mesh_obj.data.uv_layers.new(name=self.uv_name)
        new_uv.active = True
        
        # Update the enum to show the new UV
        context.scene.tsm_uv_layer = self.uv_name
        
        self.report({'INFO'}, f"Created UV map '{self.uv_name}'")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


# =====================================================================
# OPERATOR: Create New TSM
# =====================================================================

class OBJECT_OT_create_tsm(Operator):
    """Create a new Texture Smart Mapping system with 6 oriented planes"""
    bl_idname = "object.create_tsm"
    bl_label = "Create New TSM"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    plane_size: FloatProperty(
        name="Plane Size",
        description="Size of each plane (in meters)",
        default=2.0,
        min=0.1,
        max=100.0
    ) # type: ignore

    inward_faces: BoolProperty(
        name="Faces Inward",
        description="Orient plane faces toward the center (inward) or outward",
        default=False
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.mode == 'OBJECT'

    def execute(self, context):
        # Get the selected object
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}
        
        selected_obj = context.active_object
        
        # Get base name and create unique TSM name
        base_name = "TSM"
        tsm_name = self.get_unique_name(base_name)
        
        # Store original location, rotation, scale
        orig_location = selected_obj.location.copy()
        orig_rotation = selected_obj.rotation_euler.copy()
        orig_scale = selected_obj.scale.copy()
        
        # Create the main empty object (TSM container)
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=orig_location)
        tsm_empty = context.active_object
        tsm_empty.name = tsm_name
        tsm_empty.rotation_euler = orig_rotation
        tsm_empty.scale = orig_scale
        
        # Add custom properties to identify this as a TSM system
        tsm_empty["tsm_system"] = True
        tsm_empty["tsm_description"] = "New TSM System"
        
        # Define the 6 plane orientations with LOCAL offsets and rotations
        # Each tuple: (name, local_rotation_X, local_rotation_Y, local_rotation_Z, local_offset_direction)
        # Offset direction is in LOCAL space of the TSM empty (before parenting)
        plane_data = [
            ("top", 0, 0, 0, Vector((0, 0, self.plane_size/2))),              # +Z local
            ("bottom", 3.14159, 0, 0, Vector((0, 0, -self.plane_size/2))),    # -Z local (flip 180°)
            ("front", 1.5708, 0, 0, Vector((0, self.plane_size/2, 0))),       # +Y local (rot 90° X)
            ("rear", -1.5708, 0, 0, Vector((0, -self.plane_size/2, 0))),      # -Y local (rot -90° X)
            ("right", 0, -1.5708, 0, Vector((self.plane_size/2, 0, 0))),      # +X local (rot -90° Y)
            ("left", 0, 1.5708, 0, Vector((-self.plane_size/2, 0, 0))),       # -X local (rot 90° Y)
        ]
        
        created_planes = []
        
        # Get ONLY the rotation matrix (without scale) to transform local vectors to world space
        base_rotation_matrix = orig_rotation.to_matrix()
        
        for plane_name, rot_x, rot_y, rot_z, local_offset in plane_data:
            # Transform the local offset to world space using only rotation
            world_offset = base_rotation_matrix @ local_offset
            plane_world_location = orig_location + world_offset
            
            # Create plane at world location
            bpy.ops.mesh.primitive_plane_add(
                size=self.plane_size,
                location=plane_world_location
            )
            plane = context.active_object
            
            # Name the plane
            plane.name = f"{tsm_name}_{plane_name}"
            
            # Create rotation matrix for this specific plane in local space
            from mathutils import Euler
            local_plane_rotation = Euler((rot_x, rot_y, rot_z), 'XYZ')
            local_plane_matrix = local_plane_rotation.to_matrix()
            
            # Combine base rotation with plane's local rotation
            final_rotation_matrix = base_rotation_matrix @ local_plane_matrix
            
            # If faces should point inward, apply 180° flip
            if self.inward_faces:
                flip_matrix = Euler((3.14159, 0, 0), 'XYZ').to_matrix()
                final_rotation_matrix = final_rotation_matrix @ flip_matrix
            
            # Convert back to Euler angles
            plane.rotation_euler = final_rotation_matrix.to_euler()
            
            # Ensure scale is (1, 1, 1)
            plane.scale = (1.0, 1.0, 1.0)
            
            # Parent to TSM empty (this will maintain the relative position/rotation)
            plane.parent = tsm_empty
            plane.matrix_parent_inverse = tsm_empty.matrix_world.inverted()
            
            created_planes.append(plane)
        
        # Select the TSM empty at the end
        bpy.ops.object.select_all(action='DESELECT')
        tsm_empty.select_set(True)
        context.view_layer.objects.active = tsm_empty
        
        # Auto-refresh the TSM list
        refresh_tsm_list(context)
        
        self.report({'INFO'}, f"Created {tsm_name} with 6 planes")
        return {'FINISHED'}

    def get_unique_name(self, base_name):
        """Generate a unique name with numerical suffix starting from _01"""
        existing_names = [obj.name for obj in bpy.data.objects]
        
        # Always start from _01
        counter = 1
        while True:
            new_name = f"{base_name}_{counter:02d}"
            if new_name not in existing_names:
                return new_name
            counter += 1


# =====================================================================
# OPERATOR: Apply TSM Mapping
# =====================================================================

class OBJECT_OT_apply_tsm_mapping(Operator):
    """Apply UV Project modifier with 6 projectors from selected TSM system"""
    bl_idname = "object.apply_tsm_mapping"
    bl_label = "Apply TSM Mapping"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Need an active mesh object and a selected TSM in the list
        return (context.active_object is not None and 
                context.active_object.type == 'MESH' and
                context.scene.tsm_list_index >= 0 and
                len(context.scene.tsm_list) > 0)

    def execute(self, context):
        scene = context.scene
        mesh_obj = context.active_object
        
        # Get selected TSM from list
        if scene.tsm_list_index >= len(scene.tsm_list):
            self.report({'ERROR'}, "No TSM selected in list")
            return {'CANCELLED'}
        
        tsm_item = scene.tsm_list[scene.tsm_list_index]
        tsm_name = tsm_item.obj_name
        
        # Check if TSM exists
        if tsm_name not in bpy.data.objects:
            self.report({'ERROR'}, f"TSM {tsm_name} not found in scene")
            return {'CANCELLED'}
        
        tsm_empty = bpy.data.objects[tsm_name]
        
        # Check if mesh already has UV Project modifier
        for mod in mesh_obj.modifiers:
            if mod.type == 'UV_PROJECT':
                self.report({'WARNING'}, f"{mesh_obj.name} already has a UV Project modifier. Skipping.")
                return {'CANCELLED'}
        
        # Get UV layer selection
        uv_layer_name = scene.tsm_uv_layer
        if uv_layer_name == "NONE" or not uv_layer_name:
            self.report({'ERROR'}, "Please select a UV layer or create a new one")
            return {'CANCELLED'}
        
        # Check if UV layer exists
        if uv_layer_name not in mesh_obj.data.uv_layers:
            self.report({'ERROR'}, f"UV layer '{uv_layer_name}' not found in {mesh_obj.name}")
            return {'CANCELLED'}
        
        # Find the 6 plane projectors
        projector_names = ["top", "bottom", "front", "rear", "left", "right"]
        projectors = []
        
        for proj_name in projector_names:
            full_name = f"{tsm_name}_{proj_name}"
            if full_name in bpy.data.objects:
                projectors.append(bpy.data.objects[full_name])
            else:
                self.report({'ERROR'}, f"Projector {full_name} not found")
                return {'CANCELLED'}
        
        # Add UV Project modifier
        uv_mod = mesh_obj.modifiers.new(name=f"TSM_UVProject_{tsm_name}", type='UV_PROJECT')
        
        # Set UV layer
        uv_mod.uv_layer = uv_layer_name
        
        # CRITICAL: Set the number of projectors to 6
        uv_mod.projector_count = 6
        
        # Now assign the 6 projectors objects
        for i, proj_obj in enumerate(projectors):
            if i < len(uv_mod.projectors):
                uv_mod.projectors[i].object = proj_obj
        
        self.report({'INFO'}, f"Applied TSM mapping from {tsm_name} to {mesh_obj.name} with 6 projectors")
        return {'FINISHED'}


# =====================================================================
# UI LIST
# =====================================================================

class TSM_UL_List(UIList):
    """UIList for displaying TSM systems"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            # TSM name
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon='EMPTY_AXIS')
            
            # Select button
            op = row.operator("object.select_tsm", text="", icon='RESTRICT_SELECT_OFF')
            op.tsm_name = item.obj_name
            
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.prop(item, "name", text="", emboss=False, icon='EMPTY_AXIS')


# =====================================================================
# PANEL: TSM UI
# =====================================================================

class VIEW3D_PT_TSM_ToolBar(Panel):
    """Texture Smart Mapping Tools"""
    bl_label = "Texture Smart Mapping"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_parent_id = "VIEW3D_PT_QuickUtils_ToolBar"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # ============ TSM CREATION SECTION ============
        box = layout.box()
        box.label(text="Create TSM System:", icon='MESH_CUBE')
        
        col = box.column(align=True)
        col.prop(scene, "tsm_plane_size")
        col.prop(scene, "tsm_inward_faces")
        
        row = box.row()
        row.scale_y = 1.5
        row.operator("object.create_tsm", icon='ADD')
        
        layout.separator()
        
        # ============ TSM LIST SECTION ============
        box = layout.box()
        row = box.row()
        row.label(text="TSM Systems in Scene:", icon='OUTLINER')
        row.operator("object.refresh_tsm_list", text="", icon='FILE_REFRESH')
        
        # UIList
        row = box.row()
        row.template_list("TSM_UL_List", "", scene, "tsm_list", scene, "tsm_list_index", rows=3)
        
        # Description field for selected TSM
        if scene.tsm_list and scene.tsm_list_index >= 0 and scene.tsm_list_index < len(scene.tsm_list):
            selected_tsm = scene.tsm_list[scene.tsm_list_index]
            col = box.column()
            col.prop(selected_tsm, "description", text="Description")
            
            # Get TSM object to show scale
            if selected_tsm.obj_name in bpy.data.objects:
                tsm_obj = bpy.data.objects[selected_tsm.obj_name]
                
                col.separator()
                col.label(text="TSM Scale (affects UV):", icon='EMPTY_DATA')
                col.prop(tsm_obj, "scale", text="")
        
        layout.separator()
        
        # ============ APPLY MAPPING SECTION ============
        box = layout.box()
        box.label(text="Apply UV Project Mapping:", icon='MOD_UVPROJECT')
        
        # Check if we have an active mesh object
        if context.active_object and context.active_object.type == 'MESH':
            mesh_obj = context.active_object
            
            col = box.column()
            col.label(text=f"Target: {mesh_obj.name}", icon='MESH_DATA')
            
            # UV Layer management
            row = col.row(align=True)
            
            if mesh_obj.data.uv_layers:
                row.prop(scene, "tsm_uv_layer", text="UV Layer")
            else:
                row.label(text="No UV layers!", icon='ERROR')
            
            # Always show "Add UV Map" button
            row.operator("object.add_tsm_uv_map", text="", icon='ADD')
            
            # Apply button
            row = box.row()
            row.scale_y = 1.5
            op = row.operator("object.apply_tsm_mapping", icon='CHECKMARK')
            
            # Enable only if TSM is selected and UV layer is chosen
            if not (scene.tsm_list and scene.tsm_list_index >= 0 and scene.tsm_list_index < len(scene.tsm_list)):
                row.enabled = False
            elif scene.tsm_uv_layer == "NONE" or not mesh_obj.data.uv_layers:
                row.enabled = False
        else:
            box.label(text="Select a mesh object", icon='INFO')


# =====================================================================
# REGISTRATION
# =====================================================================

classes = (
    TSM_ListItem,
    OBJECT_OT_create_tsm,
    OBJECT_OT_refresh_tsm_list,
    OBJECT_OT_select_tsm,
    OBJECT_OT_add_uv_map,
    OBJECT_OT_apply_tsm_mapping,
    TSM_UL_List,
    VIEW3D_PT_TSM_ToolBar,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register scene properties for TSM creation
    bpy.types.Scene.tsm_plane_size = FloatProperty(
        name="Plane Size",
        description="Size of each plane in meters",
        default=2.0,
        min=0.1,
        max=100.0
    )
    
    bpy.types.Scene.tsm_inward_faces = BoolProperty(
        name="Faces Inward",
        description="Orient plane faces toward center (inward) or outward",
        default=False
    )
    
    # Register TSM list properties
    bpy.types.Scene.tsm_list = CollectionProperty(type=TSM_ListItem)
    bpy.types.Scene.tsm_list_index = IntProperty(default=0)
    
    # Register UV layer selector
    bpy.types.Scene.tsm_uv_layer = EnumProperty(
        name="UV Layer",
        description="Select UV layer to apply projection",
        items=get_uv_layers
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Unregister scene properties
    del bpy.types.Scene.tsm_plane_size
    del bpy.types.Scene.tsm_inward_faces
    del bpy.types.Scene.tsm_list
    del bpy.types.Scene.tsm_list_index
    del bpy.types.Scene.tsm_uv_layer


if __name__ == "__main__":
    register()