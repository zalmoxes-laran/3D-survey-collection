import bpy
import math
import mathutils
from bpy.props import FloatVectorProperty, StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel

class OBJECT_OT_record_cursor_location(Operator):
    """Record the current 3D cursor location"""
    bl_idname = "view3d.record_cursor_location"
    bl_label = "Record Current Cursor Location"
    bl_options = {'REGISTER', 'UNDO'}
    
    location_prop: StringProperty(
        name="Property Name",
        description="Scene property to store the location",
        default=""
    )
    
    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'
    
    def execute(self, context):
        # Store the cursor location in the specified property
        cursor_location = context.scene.cursor.location.copy()
        setattr(context.scene, self.location_prop, cursor_location)
        
        self.report({'INFO'}, f"Recorded cursor location at {cursor_location}")
        return {'FINISHED'}

class OBJECT_OT_create_alignment_orientation(Operator):
    """Create a custom orientation from two recorded points"""
    bl_idname = "view3d.create_alignment_orientation"
    bl_label = "Create Alignment Orientation"
    bl_options = {'REGISTER', 'UNDO'}
    
    orientation_name: StringProperty(
        name="Orientation Name",
        description="Name for the custom orientation and reference object",
        default="D.x.x_alignment"
    )
    
    alignment_type: EnumProperty(
        name="Alignment Type",
        description="How to align the orientation",
        items=[
            ('XYZ', "XYZ from Points", "Point 1 to Point 2 defines the X axis, Z is calculated assuming X and Y are at the same level"),
            ('XY', "XY axis from Points - Z not modified", "Point 1 is origin, Point 2 defines x direction, Z axis remains as Global"),
        ],
        default='XY'
    ) # type: ignore

    keep_object: BoolProperty(
        name="Keep Reference Object",
        description="Keep the created alignment object in the scene",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        # Check if we have both points defined
        return (hasattr(context.scene, 'alignment_point_1') and 
                hasattr(context.scene, 'alignment_point_2') and
                context.scene.alignment_point_1 is not None and
                context.scene.alignment_point_2 is not None)
    
    def execute(self, context):
        point1 = context.scene.alignment_point_1
        point2 = context.scene.alignment_point_2
        
        # Make sure the points are different
        if (point1 - point2).length < 0.0001:
            self.report({'ERROR'}, "The two points must be different")
            return {'CANCELLED'}

        # Create a collection for the extractor objects if it doesn't exist
        if "Extractors" not in bpy.data.collections:
            extractors_collection = bpy.data.collections.new("Extractors")
            context.scene.collection.children.link(extractors_collection)
        else:
            extractors_collection = bpy.data.collections["Extractors"]
            
        # Find a unique name for the alignment object
        # Use the orientation name for the object
        obj_name = self.orientation_name
        # If the name already exists, add a suffix
        counter = 1
        original_name = obj_name
        while obj_name in bpy.data.objects:
            obj_name = f"{original_name}_{counter}"
            counter += 1

        # Calculate the direction vector
        direction = (point2 - point1).normalized()
        
        # Create an empty object at the first point
        bpy.ops.object.empty_add(type='ARROWS', location=point1)
        alignment_obj = context.active_object
        alignment_obj.name = obj_name
        
        # Remove from current collection and add to Extractors collection
        for collection in alignment_obj.users_collection:
            collection.objects.unlink(alignment_obj)
        extractors_collection.objects.link(alignment_obj)

        # Set up the orientation based on the selected type
        if self.alignment_type == 'XY':
            # Use the direction vector as X axis
            up_vector = mathutils.Vector((0, 0, 1))
            y_axis = up_vector.cross(direction).normalized()
            z_axis = direction.cross(y_axis).normalized()
            
            # Create rotation matrix
            rotation_matrix = mathutils.Matrix((
                direction,
                y_axis,
                z_axis
            )).transposed().to_4x4()
            
        else:  # XYZ type
            # Calculate a suitable up vector (try to avoid parallel vectors)
            if abs(direction.z) < 0.9:
                up_vector = mathutils.Vector((0, 0, 1))
            else:
                up_vector = mathutils.Vector((0, 1, 0))
                
            # Calculate X, Y, and Z axes
            y_axis = up_vector.cross(direction).normalized()
            z_axis = direction.cross(y_axis).normalized()
            
            # Create rotation matrix
            rotation_matrix = mathutils.Matrix((
                direction,
                y_axis,
                z_axis
            )).transposed().to_4x4()
        
        # Apply rotation to the empty
        alignment_obj.matrix_world = rotation_matrix.copy()
        alignment_obj.location = point1
        
        # Create a custom transform orientation
        bpy.ops.transform.create_orientation(
            name=self.orientation_name,
            use=True,
            use_view=False
        )
        
        # The create_orientation operator should make the new orientation active
        # No need to manually set it in newer Blender versions
        # This avoids the enum error by letting Blender handle the orientation selection
        
        # If the user doesn't want to keep the reference object, delete it
        if not self.keep_object:
            bpy.data.objects.remove(alignment_obj, do_unlink=True)
        else:
            # Select the object again
            bpy.ops.object.select_all(action='DESELECT')
            alignment_obj.select_set(True)
            context.view_layer.objects.active = alignment_obj
        
        self.report({'INFO'}, f"Created custom orientation '{self.orientation_name}'")
        return {'FINISHED'}

class OBJECT_OT_clear_alignment_points(Operator):
    """Clear the recorded alignment points"""
    bl_idname = "view3d.clear_alignment_points"
    bl_label = "Clear Alignment Points"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Check if at least one point is defined
        return (hasattr(context.scene, 'alignment_point_1') or 
                hasattr(context.scene, 'alignment_point_2'))
    
    def execute(self, context):
        if hasattr(context.scene, 'alignment_point_1'):
            context.scene.alignment_point_1 = mathutils.Vector((0, 0, 0))
        if hasattr(context.scene, 'alignment_point_2'):
            context.scene.alignment_point_2 = mathutils.Vector((0, 0, 0))
            
        self.report({'INFO'}, "Cleared alignment points")
        return {'FINISHED'}

class VIEW3D_PT_alignment_orientation(Panel):
    """Panel for creating custom orientation from points"""
    bl_label = "Alignment Orientation"
    bl_idname = "VIEW3D_PT_alignment_orientation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 33
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Instructions
        box = layout.box()
        box.label(text="Define alignment points:")
        box.label(text="1. Position 3D cursor")
        box.label(text="2. Record position")
        box.label(text="3. Repeat for second point")
        
        # First point
        row = layout.row()
        row.label(text="Point 1:")
        
        col = row.column(align=True)
        if hasattr(scene, 'alignment_point_1') and scene.alignment_point_1 is not None:
            # Display the recorded location
            point = scene.alignment_point_1
            col.label(text=f"({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})")
        else:
            col.label(text="Not set")
        
        # Button to record first point
        op_props = row.operator("view3d.record_cursor_location", text="Record", icon='MOUSE_LMB')
        op_props.location_prop = "alignment_point_1"
        
        # Second point
        row = layout.row()
        row.label(text="Point 2:")
        
        col = row.column(align=True)
        if hasattr(scene, 'alignment_point_2') and scene.alignment_point_2 is not None:
            # Display the recorded location
            point = scene.alignment_point_2
            col.label(text=f"({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})")
        else:
            col.label(text="Not set")
        
        # Button to record second point
        op_props = row.operator("view3d.record_cursor_location", text="Record", icon='MOUSE_LMB')
        op_props.location_prop = "alignment_point_2"
        
        # Clear button
        layout.operator("view3d.clear_alignment_points", icon='X')
        
        # Separator
        layout.separator()
        
        # Create orientation settings
        if (hasattr(scene, 'alignment_point_1') and scene.alignment_point_1 is not None and
            hasattr(scene, 'alignment_point_2') and scene.alignment_point_2 is not None):
            
            # Create box for orientation settings and object name
            box = layout.box()
            box.label(text="Create Orientation:")
            
            col = box.column(align=True)
            col.prop(context.scene, "custom_orientation_name", text="Name")
            col.prop(context.scene, "custom_orientation_type", text="Type")
            col.prop(context.scene, "keep_alignment_object", text="Keep Object")
            
            # Create button
            row = box.row()
            row.scale_y = 1.5
            op_props = row.operator("view3d.create_alignment_orientation", text="Create Orientation", icon='ORIENTATION_GLOBAL')
            op_props.orientation_name = context.scene.custom_orientation_name
            op_props.alignment_type = context.scene.custom_orientation_type
            op_props.keep_object = context.scene.keep_alignment_object

def register():
    bpy.utils.register_class(OBJECT_OT_record_cursor_location)
    bpy.utils.register_class(OBJECT_OT_create_alignment_orientation)
    bpy.utils.register_class(OBJECT_OT_clear_alignment_points)
    bpy.utils.register_class(VIEW3D_PT_alignment_orientation)
    
    # Register properties
    bpy.types.Scene.alignment_point_1 = FloatVectorProperty(
        name="First Point",
        description="First point for alignment",
        subtype='XYZ'
    )
    
    bpy.types.Scene.alignment_point_2 = FloatVectorProperty(
        name="Second Point",
        description="Second point for alignment",
        subtype='XYZ'
    )
    
    bpy.types.Scene.custom_orientation_name = StringProperty(
        name="Orientation Name",
        description="Name for the custom orientation and reference object",
        default="D.x.x_alignment"
    )
    
    bpy.types.Scene.custom_orientation_type = EnumProperty(
        name="Alignment Type",
        description="How to align the orientation",
        items=[
            ('XYZ', "XYZ from Points", "Point 1 to Point 2 defines the X axis, Z is calculated assuming X and Y are at the same level"),
            ('XY', "XY axis from Points - Z not modified", "Point 1 is origin, Point 2 defines x direction, Z axis remains as Global"),
        ],
        default='XY'
    )
    
    bpy.types.Scene.keep_alignment_object = BoolProperty(
        name="Keep Reference Object",
        description="Keep the created alignment object in the scene",
        default=True
    )

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_alignment_orientation)
    bpy.utils.unregister_class(OBJECT_OT_clear_alignment_points)
    bpy.utils.unregister_class(OBJECT_OT_create_alignment_orientation)
    bpy.utils.unregister_class(OBJECT_OT_record_cursor_location)
    
    # Remove properties
    del bpy.types.Scene.keep_alignment_object
    del bpy.types.Scene.custom_orientation_type
    del bpy.types.Scene.custom_orientation_name
    del bpy.types.Scene.alignment_point_2
    del bpy.types.Scene.alignment_point_1

if __name__ == "__main__":
    register()
