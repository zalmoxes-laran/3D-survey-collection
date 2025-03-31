import bpy
import os
import math
from mathutils import Vector
from bpy.props import EnumProperty, IntProperty, StringProperty, BoolProperty, FloatProperty
from bpy.types import Panel, Operator

# Constants
SIZE_CATEGORIES = [
    ("SMALL", "Small (≤ 50cm)", "Objects up to 50cm", 0.5),
    ("MEDIUM", "Medium (≤ 1m)", "Objects between 50cm and 1m", 1.0),
    ("LARGE", "Large (≤ 2m)", "Objects between 1m and 2m", 2.0),
    ("XLARGE", "Extra Large (> 2m)", "Objects larger than 2m", 3.0)
]

CAMERA_POSITIONS = [
    ("FR", "Front", "Front view (Y+)", (0, -1, 0), (0, 0, 0)),
    ("BA", "Back", "Back view (Y-)", (0, 1, 0), (0, 0, math.pi)),
    ("RI", "Right", "Right view (X+)", (-1, 0, 0), (0, 0, -math.pi/2)),
    ("LE", "Left", "Left view (X-)", (1, 0, 0), (0, 0, math.pi/2)),
    ("TO", "Top", "Top view (Z+)", (0, 0, -1), (-math.pi/2, 0, 0)),
    ("BO", "Bottom", "Bottom view (Z-)", (0, 0, 1), (math.pi/2, 0, 0))
]

RESOLUTION_PRESETS = [
    ("LOW", "Low (2000x2000)", "2000x2000 pixels", 2000),
    ("MED", "Medium (4000x4000)", "4000x4000 pixels", 4000),
    ("HIGH", "High (6000x6000)", "6000x6000 pixels", 6000)
]

class OBJECT_OT_setup_orthogonal_render(Operator):
    """Setup orthogonal rendering for the selected object with standardized views"""
    bl_idname = "object.setup_orthogonal_render"
    bl_label = "Setup Orthogonal Render"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        
        # Get the object's bounding box dimensions
        bbox_dims = self.get_object_bbox_dimensions(obj)
        max_dim = max(bbox_dims)
        
        # Determine the size category
        size_category = self.determine_size_category(max_dim, context)
        scene.ortho_render_size_category = size_category
        
        # Set appropriate resolution based on size
        self.set_resolution_from_size(size_category, context)
        
        # Create camera if it doesn't exist
        camera = self.ensure_camera(context)
        
        # Set the camera to orthographic and adjust scale
        camera.data.type = 'ORTHO'
        ortho_scale = self.get_orthographic_scale(size_category)
        camera.data.ortho_scale = ortho_scale
        
        # Create an empty as a target at the object's center
        target = self.create_target_empty(obj, context)
        
        # Set camera constraint to track to the empty
        self.setup_camera_constraints(camera, target)
        
        # Position camera for each view and set keyframes
        self.setup_camera_positions(camera, target, obj, context)
        
        # Set render settings
        self.setup_render_settings(context)
        
        self.report({'INFO'}, f"Orthogonal render setup complete. Object size: {size_category}, ortho scale: {ortho_scale:.2f}m")
        return {'FINISHED'}
    
    def get_object_bbox_dimensions(self, obj):
        # Get the object's bounding box in world space
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        # Calculate the dimensions
        min_x = min(corner.x for corner in bbox_corners)
        max_x = max(corner.x for corner in bbox_corners)
        min_y = min(corner.y for corner in bbox_corners)
        max_y = max(corner.y for corner in bbox_corners)
        min_z = min(corner.z for corner in bbox_corners)
        max_z = max(corner.z for corner in bbox_corners)
        
        width = max_x - min_x
        depth = max_y - min_y
        height = max_z - min_z
        
        return (width, depth, height)
    
    def determine_size_category(self, max_dimension, context):
        """Determine the size category based on the maximum dimension"""
        
        # Get the size category cutoffs from the properties
        small_cutoff = context.scene.ortho_render_small_cutoff
        medium_cutoff = context.scene.ortho_render_medium_cutoff
        large_cutoff = context.scene.ortho_render_large_cutoff
        
        if max_dimension <= small_cutoff:
            return 'SMALL'
        elif max_dimension <= medium_cutoff:
            return 'MEDIUM'
        elif max_dimension <= large_cutoff:
            return 'LARGE'
        else:
            return 'XLARGE'
    
    def set_resolution_from_size(self, size_category, context):
        """Set rendering resolution based on the size category"""
        scene = context.scene
        
        # Map size categories to resolution presets
        resolution_mapping = {
            'SMALL': scene.ortho_render_small_resolution,
            'MEDIUM': scene.ortho_render_medium_resolution,
            'LARGE': scene.ortho_render_large_resolution,
            'XLARGE': scene.ortho_render_xlarge_resolution
        }
        
        # Get the resolution value from the preset
        resolution = resolution_mapping.get(size_category, 2000)
        
        # Set render resolution
        scene.render.resolution_x = resolution
        scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
    
    def get_orthographic_scale(self, size_category):
        """Get the orthographic scale based on the size category"""
        scale_mapping = {
            'SMALL': 0.5,   # 50cm
            'MEDIUM': 1.0,  # 1m
            'LARGE': 2.0,   # 2m
            'XLARGE': 3.0   # 3m
        }
        
        return scale_mapping.get(size_category, 1.0)
    
    def ensure_camera(self, context):
        """Create a camera if it doesn't exist, or use the existing one"""
        camera_name = "OrthoRenderCamera"
        
        # Check if the camera already exists
        if camera_name in bpy.data.objects:
            camera = bpy.data.objects[camera_name]
        else:
            # Create new camera
            camera_data = bpy.data.cameras.new(camera_name)
            camera = bpy.data.objects.new(camera_name, camera_data)
            context.collection.objects.link(camera)
        
        # Set as active camera
        context.scene.camera = camera
        return camera
    
    def create_target_empty(self, obj, context):
        """Create an empty object as a target for the camera"""
        target_name = "OrthoRenderTarget"
        
        # Check if the target already exists
        if target_name in bpy.data.objects:
            target = bpy.data.objects[target_name]
            # Update location to the object's center
            target.location = obj.matrix_world.translation
        else:
            # Create new empty
            target = bpy.data.objects.new(target_name, None)
            target.empty_display_type = 'PLAIN_AXES'
            target.empty_display_size = 0.2
            target.location = obj.matrix_world.translation
            context.collection.objects.link(target)
        
        return target
    
    def setup_camera_constraints(self, camera, target):
        """Set up camera constraints to track the target"""
        # Clear existing constraints
        camera.constraints.clear()
        
        # Add track to constraint
        track = camera.constraints.new('TRACK_TO')
        track.target = target
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'
    
    def setup_camera_positions(self, camera, target, obj, context):
        """Set up camera positions for each standard view"""
        # Get object dimensions for calculating distance
        bbox_dims = self.get_object_bbox_dimensions(obj)
        max_dim = max(bbox_dims)
        
        # Calculate camera distance (this might need adjusting based on ortho scale)
        camera_distance = max_dim * 2.5
        
        # Clear any existing animation data
        if camera.animation_data:
            camera.animation_data_clear()
        
        # Set up animation data
        scene = context.scene
        scene.frame_start = 1
        scene.frame_end = len(CAMERA_POSITIONS)
        
        for i, (code, name, desc, direction, rotation) in enumerate(CAMERA_POSITIONS, 1):
            # Set the current frame
            scene.frame_set(i)
            
            # Position the camera
            camera.location = target.location + Vector(direction) * camera_distance
            camera.rotation_euler = rotation
            
            # Insert keyframes
            camera.keyframe_insert(data_path="location", frame=i)
            camera.keyframe_insert(data_path="rotation_euler", frame=i)
            
            # Name the marker
            if scene.timeline_markers.find(code) == -1:
                marker = scene.timeline_markers.new(code, frame=i)
            else:
                scene.timeline_markers[code].frame = i
    
    def setup_render_settings(self, context):
        """Set up render settings for transparency"""
        scene = context.scene
        
        # Make sure we're using a render engine that supports alpha
        if scene.render.engine not in ['CYCLES', 'BLENDER_EEVEE_NEXT']:
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        
        # Set up transparency settings
        scene.render.film_transparent = True
        
        # Set the file format to PNG with transparency
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.compression = 0  # No compression
        
        # Set the output path template
        if not scene.ortho_render_output_path:
            scene.ortho_render_output_path = "//ortho_renders/"
        
        scene.render.filepath = scene.ortho_render_output_path


class RENDER_OT_orthogonal_views(Operator):
    """Render orthogonal views of the selected object"""
    bl_idname = "render.orthogonal_views"
    bl_label = "Render Orthogonal Views"
    bl_options = {'REGISTER'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.camera is not None and 
                "OrthoRenderCamera" in bpy.data.objects and 
                context.active_object is not None)
    
    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        
        # Check that camera and timeline markers are set up
        if "OrthoRenderCamera" not in bpy.data.objects:
            self.report({'ERROR'}, "Orthogonal camera setup not found. Please run Setup Orthogonal Render first.")
            return {'CANCELLED'}
        
        if len(scene.timeline_markers) < len(CAMERA_POSITIONS):
            self.report({'ERROR'}, "Camera positions not set up correctly. Please run Setup Orthogonal Render first.")
            return {'CANCELLED'}
        
        # Create output directory if it doesn't exist
        output_path = bpy.path.abspath(scene.ortho_render_output_path)
        os.makedirs(output_path, exist_ok=True)
        
        # Store original frame for restoring later
        original_frame = scene.frame_current
        
        # Render each view
        for code, name, desc, _, _ in CAMERA_POSITIONS:
            # Find the marker
            marker = scene.timeline_markers.get(code)
            if not marker:
                continue
            
            # Set the frame to the marker position
            scene.frame_set(marker.frame)
            
            # Set the output file path
            output_file = f"{obj.name}_{code}"
            scene.render.filepath = os.path.join(output_path, output_file)
            
            # Render the view
            bpy.ops.render.render(write_still=True)
            
            self.report({'INFO'}, f"Rendered {name} view to {scene.render.filepath}")
        
        # Restore original frame
        scene.frame_set(original_frame)
        
        self.report({'INFO'}, f"All orthogonal views rendered to {output_path}")
        return {'FINISHED'}


class VIEW3D_PT_orthogonal_render(Panel):
    """Panel for orthogonal rendering setup"""
    bl_label = "Orthogonal Render"
    bl_idname = "VIEW3D_PT_orthogonal_render"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Object selection
        if context.active_object is None:
            layout.label(text="Select an object to render", icon='ERROR')
            return
        
        if context.active_object.type != 'MESH':
            layout.label(text="Selected object must be a mesh", icon='ERROR')
            return
        
        # Show the selected object
        box = layout.box()
        row = box.row()
        row.label(text=f"Object: {context.active_object.name}", icon='OBJECT_DATA')
        
        # Size categories settings
        box = layout.box()
        box.label(text="Size Categories", icon='DRIVER_DISTANCE')
        
        col = box.column(align=True)
        col.prop(scene, "ortho_render_small_cutoff", text="Small (≤)")
        col.prop(scene, "ortho_render_medium_cutoff", text="Medium (≤)")
        col.prop(scene, "ortho_render_large_cutoff", text="Large (≤)")
        
        # Resolution settings
        box = layout.box()
        box.label(text="Resolution Settings", icon='IMAGE_DATA')
        
        col = box.column(align=True)
        col.prop(scene, "ortho_render_small_resolution", text="Small")
        col.prop(scene, "ortho_render_medium_resolution", text="Medium")
        col.prop(scene, "ortho_render_large_resolution", text="Large")
        col.prop(scene, "ortho_render_xlarge_resolution", text="X-Large")
        
        # Output path
        box = layout.box()
        box.label(text="Output Settings", icon='FOLDER_REDIRECT')
        box.prop(scene, "ortho_render_output_path", text="")
        
        # Setup and render buttons
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("object.setup_orthogonal_render", icon='CAMERA_DATA')
        
        # Only show render button if camera is set up
        if "OrthoRenderCamera" in bpy.data.objects:
            row = layout.row(align=True)
            row.scale_y = 1.5
            row.operator("render.orthogonal_views", icon='RENDER_STILL')
            
            # Show current size category if it exists
            if hasattr(scene, "ortho_render_size_category") and scene.ortho_render_size_category:
                box = layout.box()
                
                # Find the size category info from the SIZE_CATEGORIES list
                size_info = next((item for item in SIZE_CATEGORIES if item[0] == scene.ortho_render_size_category), None)
                if size_info:
                    box.label(text=f"Current Size: {size_info[1]}")
                else:
                    box.label(text=f"Current Size: {scene.ortho_render_size_category}")
                    
                box.label(text=f"Resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")


def register():
    bpy.utils.register_class(OBJECT_OT_setup_orthogonal_render)
    bpy.utils.register_class(RENDER_OT_orthogonal_views)
    bpy.utils.register_class(VIEW3D_PT_orthogonal_render)
    
    # Register properties
    bpy.types.Scene.ortho_render_size_category = EnumProperty(
        items=[(id, name, desc) for id, name, desc, _ in SIZE_CATEGORIES],
        name="Size Category",
        description="Size category of the object"
    )
    
    # Size cutoffs
    bpy.types.Scene.ortho_render_small_cutoff = FloatProperty(
        name="Small Cutoff",
        description="Maximum size for small objects (meters)",
        default=0.5,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    
    bpy.types.Scene.ortho_render_medium_cutoff = FloatProperty(
        name="Medium Cutoff",
        description="Maximum size for medium objects (meters)",
        default=1.0,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    
    bpy.types.Scene.ortho_render_large_cutoff = FloatProperty(
        name="Large Cutoff",
        description="Maximum size for large objects (meters)",
        default=2.0,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    
    # Resolution settings
    bpy.types.Scene.ortho_render_small_resolution = IntProperty(
        name="Small Resolution",
        description="Resolution for small objects (pixels)",
        default=2000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_medium_resolution = IntProperty(
        name="Medium Resolution",
        description="Resolution for medium objects (pixels)",
        default=4000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_large_resolution = IntProperty(
        name="Large Resolution",
        description="Resolution for large objects (pixels)",
        default=6000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_xlarge_resolution = IntProperty(
        name="X-Large Resolution",
        description="Resolution for extra large objects (pixels)",
        default=8000,
        min=500,
        max=10000
    )
    
    bpy.types.Scene.ortho_render_output_path = StringProperty(
        name="Output Path",
        description="Path to save rendered images",
        default="//ortho_renders/",
        subtype='DIR_PATH'
    )


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_orthogonal_render)
    bpy.utils.unregister_class(RENDER_OT_orthogonal_views)
    bpy.utils.unregister_class(OBJECT_OT_setup_orthogonal_render)
    
    # Unregister properties
    del bpy.types.Scene.ortho_render_size_category
    del bpy.types.Scene.ortho_render_small_cutoff
    del bpy.types.Scene.ortho_render_medium_cutoff
    del bpy.types.Scene.ortho_render_large_cutoff
    del bpy.types.Scene.ortho_render_small_resolution
    del bpy.types.Scene.ortho_render_medium_resolution
    del bpy.types.Scene.ortho_render_large_resolution
    del bpy.types.Scene.ortho_render_xlarge_resolution
    del bpy.types.Scene.ortho_render_output_path


if __name__ == "__main__":
    register()