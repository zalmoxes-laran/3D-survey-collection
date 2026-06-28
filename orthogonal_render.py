import bpy
import os
import math
from mathutils import Vector, Matrix
from bpy.props import EnumProperty, IntProperty, StringProperty, BoolProperty, FloatProperty
from bpy.types import Panel, Operator
from .functions import make_path_relative

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

# Three-point "TriLamp" light rig, reproduced from Rachele's reference
# Luci.blend (the lights parented to the base OrthoRenderCamera, ortho_scale
# 1.0 -> calibrated for a ~1m object). Transforms are LOCAL to the camera:
# +X right, +Y up, -Z toward the subject. The rig is parented to the camera
# so it orbits with the viewpoint; positions/energies are scaled to the
# object size at setup time (see LIGHT_RIG_SIZE_REF) and keyframed on every
# pose so each of the six views can be fine-tuned manually afterwards.
LIGHT_RIG_COLLECTION = "OrthoRender_Lights"
LIGHT_RIG_SIZE_REF = 1.0  # meters: object size the reference rig was tuned for

TRILAMP_RIG = [
    {
        "name": "OrthoRender_TriLamp-Key",
        "type": "POINT",
        "energy": 150.0,
        "color": (1.0, 1.0, 1.0),
        "location": (-1.1485, -1.5719, 0.7455),
        "rotation": (0.0, 0.0, 0.0),
    },
    {
        "name": "OrthoRender_TriLamp-Fill",
        "type": "POINT",
        "energy": 250.0,
        "color": (1.0, 1.0, 1.0),
        "location": (1.6853, -0.4644, 0.5145),
        "rotation": (0.7014, 1.2025, 0.5929),
    },
    {
        "name": "OrthoRender_TriLamp-Back",
        "type": "AREA",
        "energy": 200.0,
        "color": (1.0, 1.0, 1.0),
        "location": (-4.1669, 0.3039, 0.8412),
        "rotation": (0.0, 0.0, 0.0),
        "shape": "SQUARE",
        "size": 1.0,
        "size_y": 0.25,
    },
]


def compute_render_resolution(obj_m, family='FIXED_SHEET', scale_denom=10, dpi=300):
    """Compute optimal render resolution in pixels for a given template configuration.

    For FIXED_SHEET: uses 1:10 equivalent resolution (high-res for on-screen zoom).
    For FIXED_SCALE: uses the actual declared scale at the given DPI.
    """
    if family == 'FIXED_SHEET':
        image_mm = obj_m * 1000 / 10  # Always 1:10 equivalent
    else:
        image_mm = obj_m * 1000 / scale_denom
    return int(round(image_mm / 25.4 * dpi))


def get_text_dimensions(text, font, draw=None):
    """Get text dimensions in a way that works with any PIL version"""
    try:
        # Nuove versioni di PIL
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Versione di transizione
        elif hasattr(font, "getsize"):
            return font.getsize(text)
        # Metodo più vecchio con ImageDraw 
        elif draw and hasattr(draw, "textsize"):
            return draw.textsize(text, font=font)
        # Ancora più recente (se cambia l'API in futuro)
        elif hasattr(font, "getlength"):
            return font.getlength(text), font.getsize_multiline("X")[1]
        else:
            # Fallback
            return len(text) * 20, 40
    except Exception as e:
        print(f"Error getting text dimensions: {e}")
        # Fallback a valori ragionevoli
        return len(text) * 20, 40


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

        # Create the three-point light rig parented to the camera
        light_msg = ""
        if getattr(scene, "ortho_render_create_lights", True):
            max_dim = max(self.get_object_bbox_dimensions(obj))
            n_lights = self.setup_light_rig(camera, max_dim, context)
            light_msg = f", {n_lights} lights"

        # Restore to the first pose
        scene.frame_set(scene.frame_start)

        # Set render settings
        self.setup_render_settings(context)

        self.report({'INFO'}, f"Orthogonal render setup complete. Object size: {size_category}, ortho scale: {ortho_scale:.2f}m{light_msg}")
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
        """Create an empty object as a target for the camera at the bounding box center"""
        target_name = "OrthoRenderTarget"
        
        # Calculate the center of the bounding box in world space
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        bbox_center = sum(bbox_corners, Vector()) / 8  # Average of all 8 corners
        
        # Check if the target already exists
        if target_name in bpy.data.objects:
            target = bpy.data.objects[target_name]
            # Update location to the bounding box center
            target.location = bbox_center
        else:
            # Create new empty
            target = bpy.data.objects.new(target_name, None)
            target.empty_display_type = 'PLAIN_AXES'
            target.empty_display_size = 0.2
            target.location = bbox_center
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
    
    def _get_light_rig_collection(self, context):
        """Return (creating if needed) the collection that holds the rig lights."""
        coll = bpy.data.collections.get(LIGHT_RIG_COLLECTION)
        if coll is None:
            coll = bpy.data.collections.new(LIGHT_RIG_COLLECTION)
            context.scene.collection.children.link(coll)
        return coll

    def setup_light_rig(self, camera, max_dim, context):
        """Create/refresh the three-point light rig parented to the camera.

        The rig reproduces Rachele's reference Luci.blend (Key/Fill/Back).
        Positions and area-light size scale linearly with the object size,
        and energy scales with the square of that factor (inverse-square law),
        using LIGHT_RIG_SIZE_REF as the reference. Each light's LOCAL transform
        is keyframed on every pose so each of the six views can be fine-tuned
        by hand afterwards; because the lights are parented to the camera they
        otherwise orbit rigidly with the viewpoint.
        """
        scene = context.scene
        factor = max(max_dim, 1e-4) / LIGHT_RIG_SIZE_REF
        coll = self._get_light_rig_collection(context)
        identity = Matrix.Identity(4)

        light_objs = []
        for spec in TRILAMP_RIG:
            name = spec["name"]
            light_obj = bpy.data.objects.get(name)
            if light_obj is None or light_obj.type != 'LIGHT':
                light_data = bpy.data.lights.new(name, type=spec["type"])
                light_obj = bpy.data.objects.new(name, light_data)
            light_data = light_obj.data

            # Link into the rig collection (and nowhere else)
            for c in list(light_obj.users_collection):
                c.objects.unlink(light_obj)
            coll.objects.link(light_obj)

            # Light data
            light_data.type = spec["type"]
            light_data.color = spec["color"]
            light_data.energy = spec["energy"] * factor * factor
            if spec["type"] == 'AREA':
                light_data.shape = spec.get("shape", 'SQUARE')
                light_data.size = spec.get("size", 1.0) * factor
                if "size_y" in spec:
                    light_data.size_y = spec["size_y"] * factor

            # Clear any previous animation so re-running gives a clean rig
            if light_obj.animation_data:
                light_obj.animation_data_clear()

            # Parent to the camera with local transform == the spec offset
            light_obj.parent = camera
            light_obj.matrix_parent_inverse = identity
            light_obj.location = Vector(spec["location"]) * factor
            light_obj.rotation_euler = spec["rotation"]
            light_objs.append(light_obj)

        # Keyframe the local transform on every pose for per-view fine-tuning
        for i in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(i)
            for light_obj in light_objs:
                light_obj.keyframe_insert(data_path="location", frame=i)
                light_obj.keyframe_insert(data_path="rotation_euler", frame=i)

        return len(light_objs)

    def setup_render_settings(self, context):
        """Set up render settings for transparency"""
        scene = context.scene
        
        # Make sure we're using a render engine that supports alpha
        if scene.render.engine not in ['CYCLES', 'BLENDER_EEVEE']:
            scene.render.engine = 'BLENDER_EEVEE'
        
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
        # Check if blend file is saved
        if not bpy.data.filepath:
            return False
            
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


class RENDER_OT_create_orthogonal_svg(Operator):
    """Create an SVG file with the orthogonal renders"""
    bl_idname = "render.create_orthogonal_svg"
    bl_label = "Create SVG Layout"
    bl_options = {'REGISTER'}
    
    document_name: StringProperty(
        name="Document Name",
        description="Name of the SVG document",
        default="orthogonal_renders"
    ) # type: ignore
    
    project_title: StringProperty(
        name="Project Title",
        description="Title of the project",
        default=""
    ) # type: ignore
    
    measurement_unit: EnumProperty(
        name="Measurement Unit",
        description="Unit for dimensions",
        items=[('cm', "Centimeters", "Use centimeters"),
               ('m', "Meters", "Use meters"),
               ('mm', "Millimeters", "Use millimeters")],
        default='cm'
    ) # type: ignore
    
    template_name: StringProperty(
        name="Template Name",
        description="Name of the SVG template file to use (without extension)",
        default="MASTER_1m"
    ) # type: ignore

    # Aggiungere questa variabile come attributo della classe
    last_checked_paths = []  # Per tenere traccia dei percorsi controllati durante la ricerca

    # Dinamicamente popolare la lista dei template disponibili
    def get_available_templates(self, context):
        import re
        templates_dict = {}  # Per evitare duplicati

        # Get the current family filter
        family = context.scene.ortho_template_family if hasattr(context.scene, 'ortho_template_family') else 'LEGACY'

        # Percorsi possibili in cui cercare i template (user folders first)
        possible_paths = get_template_search_paths()

        for path in possible_paths:
            if os.path.exists(path):
                for file in os.listdir(path):
                    if not file.endswith(".svg"):
                        continue
                    name = os.path.splitext(file)[0]

                    # Determine which family this template belongs to
                    if name.startswith('FIXED_'):
                        tmpl_family = 'FIXED_SHEET'
                    elif name.startswith('SCALE_'):
                        tmpl_family = 'FIXED_SCALE'
                    else:
                        tmpl_family = 'LEGACY'

                    # Filter by selected family
                    if tmpl_family != family:
                        continue

                    # Extract scale info for sorting and description
                    if tmpl_family == 'FIXED_SHEET':
                        # Pattern: FIXED_A3_50cm or FIXED_A3_50cm_compact
                        m = re.search(r'FIXED_A3_(\d+)(cm|m)(?:_compact)?$', name)
                        if m:
                            val = float(m.group(1))
                            unit = m.group(2)
                            scale_meters = val / 100 if unit == 'cm' else val
                            compact = '_compact' in name
                            description = f"A3 {m.group(1)}{unit}" + (" compact" if compact else "")
                        else:
                            scale_meters = 1.0
                            description = name
                    elif tmpl_family == 'FIXED_SCALE':
                        # Pattern: SCALE_1-10_A2_1m
                        m = re.search(r'SCALE_1-(\d+)_A(\d)_(\d+)(cm|m)$', name)
                        if m:
                            denom = int(m.group(1))
                            paper = f"A{m.group(2)}"
                            val = float(m.group(3))
                            unit = m.group(4)
                            scale_meters = val / 100 if unit == 'cm' else val
                            description = f"1:{denom} {paper} {m.group(3)}{unit}"
                        else:
                            scale_meters = 1.0
                            description = name
                    else:
                        # Legacy: MASTER_*
                        scale_match = re.search(r'(\d+(?:\.\d+)?)(m|cm|mm)$', name, re.IGNORECASE)
                        if scale_match:
                            sv = float(scale_match.group(1))
                            su = scale_match.group(2).lower()
                            scale_meters = sv / 100 if su == 'cm' else (sv / 1000 if su == 'mm' else sv)
                            description = f"Legacy {scale_match.group(1)}{su}"
                        else:
                            scale_meters = 1.0
                            description = f"Legacy: {name}"

                    if name not in templates_dict:
                        templates_dict[name] = (name, name, description, scale_meters)

        # Sort by scale and build final list
        templates = sorted(templates_dict.values(), key=lambda x: x[3])
        templates = [(t[0], t[1], t[2]) for t in templates]

        if not templates:
            templates.append(("MASTER_1m", "MASTER_1m", "Default template (1:1m)"))

        return templates
    
    template_select: EnumProperty(
        name="Template",
        description="Select SVG template to use",
        items=get_available_templates,
    )
    
    auto_select_template: BoolProperty(
        name="Auto-select Template",
        description="Automatically select the best template based on object size",
        default=True
    )
    
    open_file: BoolProperty(
        name="Open SVG After Export",
        description="Open the SVG file with the default application after export",
        default=False
    ) # type: ignore

    open_folder: BoolProperty(
        name="Open Folder After Export",
        description="Open the folder containing the exported file",
        default=True
    ) # type: ignore

    create_pdf: BoolProperty(
        name="Create PDF",
        description="Also create a PDF version of the SVG (requires Inkscape or similar)",
        default=False
    ) # type: ignore
    
    @classmethod
    def poll(cls, context):
        # Check if the blend file is saved
        if not bpy.data.filepath:
            return False
        
        output_path = bpy.path.abspath(context.scene.ortho_render_output_path)
        
        # Check if output directory exists and contains rendered images
        if not os.path.exists(output_path):
            return False
        
        # Check if we have a camera and target set up
        return "OrthoRenderCamera" in bpy.data.objects and context.active_object is not None
    
    def invoke(self, context, event):
        # Set default name based on active object
        if context.active_object:
            self.document_name = context.active_object.name
            self.project_title = context.active_object.name
        
        # Determina automaticamente il template migliore basato sulla dimensione
        if self.auto_select_template:
            obj = context.active_object
            if obj:
                bbox_dims = self.get_object_dimensions(obj)
                max_dim = max(bbox_dims)
                family = context.scene.ortho_template_family if hasattr(context.scene, 'ortho_template_family') else 'LEGACY'

                if family == 'FIXED_SHEET':
                    if max_dim <= 0.5:
                        target = "FIXED_A3_50cm"
                    elif max_dim <= 1.0:
                        target = "FIXED_A3_1m"
                    else:
                        target = "FIXED_A3_2m"
                    self.template_select = target if self.template_exists(target) else "MASTER_1m"

                elif family == 'FIXED_SCALE':
                    if max_dim <= 0.5:
                        target = "SCALE_1-5_A2_50cm"
                    elif max_dim <= 1.0:
                        target = "SCALE_1-10_A2_1m"
                    else:
                        target = "SCALE_1-20_A2_2m"
                    self.template_select = target if self.template_exists(target) else "MASTER_1m"

                else:  # LEGACY
                    if max_dim <= 0.5:
                        self.template_select = "MASTER_50cm" if self.template_exists("MASTER_50cm") else "MASTER_1m"
                    elif max_dim <= 1.0:
                        self.template_select = "MASTER_1m"
                    elif max_dim <= 2.0:
                        self.template_select = "MASTER_2m" if self.template_exists("MASTER_2m") else "MASTER_1m"
                    else:
                        self.template_select = "MASTER_5m" if self.template_exists("MASTER_5m") else "MASTER_1m"
        
        return context.window_manager.invoke_props_dialog(self)
    
    def template_exists(self, template_name):
        """Verifica se esiste un template con il nome specificato"""
        template_paths = self.find_template_paths(template_name)
        return len(template_paths) > 0
    
    def find_template_paths(self, template_name):        
        """Find all possible paths for a given template"""
        template_paths = []
        self.last_checked_paths = []  # Resetta la lista

        # Possible paths (user resource folders first, bundled last)
        possible_paths = get_template_search_paths()

        # Log possible paths
        print("Cercando template SVG in:")
        for path in possible_paths:
            if os.path.exists(path):
                full_path = os.path.join(path, f"{template_name}.svg")
                self.last_checked_paths.append(full_path)
                if os.path.exists(full_path):
                    template_paths.append(full_path)
                    print(f"✓ Trovato template: {full_path}")
                else:
                    print(f"✗ Template non trovato: {full_path}")
            else:
                print(f"✗ Cartella non esistente: {path}")
        
        return template_paths
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="SVG Document Settings")
        box.prop(self, "document_name")
        box.prop(self, "project_title")
        
        box = layout.box()
        box.label(text="Object Measurements")
        box.prop(self, "measurement_unit")
        
        box = layout.box()
        box.label(text="Template Selection")
        box.prop(self, "auto_select_template")
        
        if not self.auto_select_template:
            box.prop(self, "template_select")
        else:
            # Mostra il template selezionato automaticamente
            box.label(text=f"Selected template: {self.template_select}")
        
        box = layout.box()
        box.label(text="Post-Export Options")
        box.prop(self, "open_file")
        box.prop(self, "open_folder")
        box.prop(self, "create_pdf")
        
        # Mostra avvisi per problemi comuni
        if not bpy.data.filepath:
            box = layout.box()
            box.label(text="Warning: Blend file not saved", icon='ERROR')
            box.label(text="Please save your file first")
        
        # Verifica se il template esiste
        template_paths = self.find_template_paths(self.template_select)
        if not template_paths:
            box = layout.box()
            box.label(text=f"Template '{self.template_select}' not found", icon='ERROR')
            box.label(text="Check the svg_templates folder")
    
    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save your blend file first")
            return {'CANCELLED'}
        
        obj = context.active_object
        output_path = bpy.path.abspath(context.scene.ortho_render_output_path)
        
        # If output directory doesn't exist, create it
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)
        
        # Get paths for each view based on defined positions
        camera_positions = [
            ("FR", "Front", "Front view (Y+)"),
            ("BA", "Back", "Back view (Y-)"),
            ("RI", "Right", "Right view (X+)"),
            ("LE", "Left", "Left view (X-)"),
            ("TO", "Top", "Top view (Z+)"),
            ("BO", "Bottom", "Bottom view (Z-)")
        ]
        
        image_paths = {}
        for i, (code, name, _) in enumerate(camera_positions):
            img_path = os.path.join(output_path, f"{obj.name}_{code}.png")
            if os.path.exists(img_path):
                image_paths[i+1] = img_path
            else:
                self.report({'WARNING'}, f"Missing render for {name} view. File not found: {img_path}")
                image_paths[i+1] = ""
        
        # Get object dimensions
        dimensions = self.get_object_dimensions(obj)
        formatted_dimensions = self.format_dimensions(dimensions, self.measurement_unit)
        
        # Find the SVG template
        template_paths = self.find_template_paths(self.template_select)

        if not template_paths:
            self.report({'ERROR'}, f"Template '{self.template_select}' not found. Operation cancelled.")
            return {'CANCELLED'}

        # Use the first template found
        template_path = template_paths[0]
        
        # Create the output path for the SVG file
        svg_output_path = os.path.join(output_path, f"{self.document_name}.svg")
        
        # Copy the template file directly to destination instead of loading it in memory first
        try:
            import shutil
            shutil.copy(template_path, svg_output_path)
            print(f"Template copied from {template_path} to {svg_output_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Error copying template file: {e}")
            return {'CANCELLED'}
        #return {'FINISHED'}
        # Now read the copied file for replacements
        try:
            with open(svg_output_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
                print(f"Read {len(svg_content)} bytes from copied template")
        except Exception as e:
            self.report({'ERROR'}, f"Error reading copied template: {e}")
            return {'CANCELLED'}
        
        # Handle placeholder for missing images
        placeholder_path = os.path.join(os.path.dirname(svg_output_path), "placeholder.png")
        if not os.path.exists(placeholder_path):
            self.create_placeholder_image(placeholder_path)
        
        # Make all required replacements
        #svg_content = svg_content.replace('_3dscnamedocument.svg', f"{self.document_name}.svg")
        svg_content = svg_content.replace('_3dsctitolo', self.project_title)
        svg_content = svg_content.replace('_3dscnomeblocco', obj.name)
        svg_content = svg_content.replace('_3dscmisure', formatted_dimensions)
        
        # Replace image references
        for i in range(1, 7):
            if i in image_paths and image_paths[i] and os.path.exists(image_paths[i]):
                print(f"Using actual image for view {i}: {image_paths[i]}")
                current_image_relative_path = make_path_relative(image_paths[i], output_path)
                svg_content = svg_content.replace(f'_ref_image{i}', current_image_relative_path)
                #svg_content = svg_content.replace(f'_ref_image{i}', f'file:///{image_paths[i]}')
            else:
                print(f"Using placeholder for view {i}")
                placeholder_relative_path = make_path_relative(placeholder_path, output_path)
                svg_content = svg_content.replace(f'_ref_image{i}', placeholder_relative_path)
                #svg_content = svg_content.replace(f'_ref_image{i}', placeholder_path)
        
        # Handle special images
        #special_images = [
        #    ('_image7', '_ref_image7'),
        #    ('_image_8', '_ref_image_8')
        #]
        #for img_tag, ref_tag in special_images:
        #    svg_content = svg_content.replace(img_tag, placeholder_path)
        #    svg_content = svg_content.replace(ref_tag, placeholder_path)
        
        # Handle logo
        logo_path = os.path.join(os.path.dirname(template_path), "logo.png")
        if os.path.exists(logo_path):
            #svg_content = svg_content.replace('_logo', logo_path)
            svg_content = svg_content.replace('_ref_logo', logo_path)
        else:
            #svg_content = svg_content.replace('_logo', placeholder_path)
            svg_content = svg_content.replace('_ref_logo', placeholder_path)
        
        # Write back the modified content
        try:
            with open(svg_output_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
                print(f"Modified SVG written back with {len(svg_content)} bytes")
        except Exception as e:
            self.report({'ERROR'}, f"Error writing modified SVG: {e}")
            return {'CANCELLED'}
        
        # Create PDF if requested
        pdf_output_path = None
        if self.create_pdf:
            pdf_output_path = os.path.join(output_path, f"{self.document_name}.pdf")
            pdf_created = self.create_pdf_from_svg(svg_output_path, pdf_output_path)
            if not pdf_created:
                self.report({'WARNING'}, "Could not create PDF. Inkscape may not be installed.")

        # Open the file if requested
        if self.open_file:
            try:
                import subprocess
                if os.name == 'nt':  # Windows
                    os.startfile(svg_output_path)
                elif os.name == 'posix':  # Linux or Mac
                    # macOS uses 'open', Linux uses 'xdg-open'
                    import platform
                    if platform.system() == 'Darwin':  # macOS
                        subprocess.Popen(['open', svg_output_path])
                    else:  # Linux
                        subprocess.Popen(['xdg-open', svg_output_path])
            except Exception as e:
                self.report({'WARNING'}, f"Could not open file: {e}")

        # Open folder if requested
        if self.open_folder:
            try:
                import subprocess
                if os.name == 'nt':  # Windows
                    os.startfile(output_path)
                elif os.name == 'posix':  # Linux or Mac
                    import platform
                    if platform.system() == 'Darwin':  # macOS
                        subprocess.Popen(['open', output_path])
                    else:  # Linux
                        subprocess.Popen(['xdg-open', output_path])
            except Exception as e:
                self.report({'WARNING'}, f"Could not open folder: {e}")

        success_msg = f"SVG created successfully at {svg_output_path}"
        if pdf_output_path and os.path.exists(pdf_output_path):
            success_msg += f" and PDF at {pdf_output_path}"

        self.report({'INFO'}, success_msg)
        return {'FINISHED'}
    
    def get_object_dimensions(self, obj):
        """Get the object's bounding box dimensions in world space"""
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
        
        return (depth, width, height)
    
    def format_dimensions(self, dimensions, unit):
        """Format dimensions with the proper unit"""
        if unit == 'm':
            # Convert from meters to meters (no change)
            formatted = f"{dimensions[0]:.2f} x {dimensions[1]:.2f} x {dimensions[2]:.2f} m"
        elif unit == 'cm':
            # Convert from meters to centimeters
            dim_cm = [d * 100 for d in dimensions]
            formatted = f"{dim_cm[0]:.1f} x {dim_cm[1]:.1f} x {dim_cm[2]:.1f} cm"
        elif unit == 'mm':
            # Convert from meters to millimeters
            dim_mm = [d * 1000 for d in dimensions]
            formatted = f"{int(dim_mm[0])} x {int(dim_mm[1])} x {int(dim_mm[2])} mm"
        else:
            formatted = f"{dimensions[0]:.2f} x {dimensions[1]:.2f} x {dimensions[2]:.2f}"
        
        return formatted
    
    def create_pdf_from_svg(self, svg_path, pdf_path):
        """Create a PDF from SVG using available tools"""
        try:
            import subprocess
            import platform

            # Try different conversion methods
            converters = []

            if platform.system() == 'Darwin':  # macOS
                # Try Inkscape (common installation paths on macOS)
                converters.extend([
                    ['/Applications/Inkscape.app/Contents/MacOS/inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['/usr/local/bin/inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['inkscape', svg_path, '--export-filename=' + pdf_path],
                ])
            elif platform.system() == 'Windows':
                converters.extend([
                    ['inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['C:\\Program Files\\Inkscape\\bin\\inkscape.exe', svg_path, '--export-filename=' + pdf_path],
                ])
            else:  # Linux
                converters.extend([
                    ['inkscape', svg_path, '--export-filename=' + pdf_path],
                    ['rsvg-convert', '-f', 'pdf', '-o', pdf_path, svg_path],
                    ['cairosvg', svg_path, '-o', pdf_path],
                ])

            # Try each converter
            for converter in converters:
                try:
                    result = subprocess.run(converter, capture_output=True, timeout=30)
                    if result.returncode == 0 and os.path.exists(pdf_path):
                        print(f"PDF created successfully using {converter[0]}")
                        return True
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

            return False

        except Exception as e:
            print(f"Error creating PDF: {e}")
            return False

    def create_placeholder_image(self, placeholder_path):
        """Create a placeholder image at the specified path"""
        try:
            # Only import PIL if we need to create the placeholder
            from PIL import Image, ImageDraw, ImageFont
            
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(placeholder_path), exist_ok=True)
            
            # Create a simple placeholder image
            width, height = 800, 800
            image = Image.new('RGBA', (width, height), (50, 50, 50, 255))
            draw = ImageDraw.Draw(image)
            
            # Draw a grid pattern
            grid_spacing = 50
            color1 = (60, 60, 60, 255)
            color2 = (40, 40, 40, 255)
            
            for x in range(0, width, grid_spacing):
                for y in range(0, height, grid_spacing):
                    if (x // grid_spacing + y // grid_spacing) % 2 == 0:
                        draw.rectangle([x, y, x + grid_spacing, y + grid_spacing], fill=color1)
                    else:
                        draw.rectangle([x, y, x + grid_spacing, y + grid_spacing], fill=color2)
            
            # Draw diagonal lines
            draw.line((0, 0, width, height), fill=(100, 100, 100), width=5)
            draw.line((0, height, width, 0), fill=(100, 100, 100), width=5)
            
            # Draw a message in the center
            try:
                # Try to use a font if available
                font = ImageFont.truetype("arial.ttf", 40)
            except OSError:
                # Fallback to default
                font = ImageFont.load_default()
                
            text = "View Not Rendered"
            
            # Get text dimensions (compatible with any PIL version)
            text_width, text_height = get_text_dimensions(text, font, draw)
            text_position = ((width - text_width) // 2, (height - text_height) // 2)
            
            # Draw text with shadow
            draw.text((text_position[0]+2, text_position[1]+2), text, font=font, fill=(0, 0, 0, 255))
            draw.text(text_position, text, font=font, fill=(200, 200, 200, 255))
            
            # Save the image
            image.save(placeholder_path)
            print(f"Created placeholder image at {placeholder_path}")
            
        except Exception as e:
            print(f"Error creating placeholder image: {e}")
            # Create a simple fallback if PIL is not available
            try:
                if not os.path.exists(placeholder_path):
                    # Create a simple numpy array and save it with matplotlib
                    import numpy as np
                    import matplotlib.pyplot as plt
                    
                    arr = np.zeros((800, 800, 3))
                    for i in range(800):
                        for j in range(800):
                            if (i//50 + j//50) % 2 == 0:
                                arr[i, j] = [0.2, 0.2, 0.2]
                            else:
                                arr[i, j] = [0.15, 0.15, 0.15]
                    
                    # Add diagonal lines
                    for i in range(800):
                        arr[i, i] = [0.4, 0.4, 0.4]
                        arr[i, 799-i] = [0.4, 0.4, 0.4]
                    
                    plt.imsave(placeholder_path, arr)
                    print(f"Created fallback placeholder image at {placeholder_path}")
            except Exception:
                print("Could not create placeholder image")


def get_addon_path():
    """Return the addon root directory.

    orthogonal_render.py lives at the addon root, so the directory containing
    this file IS the addon root. Using __file__ works regardless of the addon
    folder name or install location (legacy addon dir or bl_ext extension
    namespace) — unlike the old hardcoded "3D-survey-collection" path lookup.
    """
    return os.path.dirname(os.path.realpath(__file__))


# ---------------------------------------------------------------------------
# Template folder resolution
#
# Templates can live in several places. They are searched in priority order;
# the first folder that contains a given template name wins, so user/resource
# folders override the bundled ones. The bundled folder inside the addon is
# always the last-resort fallback and ships with the extension.
#
# The ExtendedMatrix home folder (~/ExtendedMatrix/3D Survey Collection/...) is
# part of the wider EM ecosystem and is NEVER created automatically on install
# — the user creates it manually from the addon preferences. Extra resource
# folders (including cloud/Drive paths) are added by the user to a list in the
# addon preferences.
# ---------------------------------------------------------------------------

def get_em_home_base():
    """~/ExtendedMatrix — shared root for the Extended Matrix tool ecosystem."""
    return os.path.join(os.path.expanduser("~"), "ExtendedMatrix")


def get_3dsc_home():
    """~/ExtendedMatrix/3D Survey Collection — this tool's home subfolder."""
    return os.path.join(get_em_home_base(), "3D Survey Collection")


def get_em_home_templates():
    """The SVG templates folder inside the EM home (manually created)."""
    return os.path.join(get_3dsc_home(), "svg_templates")


def get_addon_prefs():
    """Return this addon's preferences, or None if unavailable."""
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


def get_user_template_folders():
    """Absolute paths of the user-configured resource folders (in order)."""
    folders = []
    prefs = get_addon_prefs()
    if prefs is not None:
        for item in getattr(prefs, "svg_template_folders", []):
            raw = (item.path or "").strip()
            if not raw:
                continue
            folders.append(os.path.normpath(bpy.path.abspath(raw)))
    return folders


def get_template_search_paths():
    """Ordered list of folders to search for SVG templates.

    Priority (first wins on name collision):
      1. User resource folders from preferences (incl. cloud/Drive)
      2. ExtendedMatrix home folder (~/ExtendedMatrix/3D Survey Collection)
      3. Folders next to the saved .blend (project-local)
      4. Bundled folder inside the addon (always present, fallback)
    """
    paths = list(get_user_template_folders())
    paths.append(get_em_home_templates())

    if bpy.data.filepath:
        blend_dir = os.path.dirname(bpy.data.filepath)
        paths.append(os.path.join(blend_dir, "svg_templates"))
        paths.append(os.path.join(blend_dir, "3DSC", "svg_templates"))

    paths.append(os.path.join(get_addon_path(), "svg_templates"))

    # De-duplicate while preserving order
    seen = set()
    ordered = []
    for p in paths:
        norm = os.path.normpath(p)
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


class RENDER_OT_open_templates_folder(Operator):
    """Open the bundled SVG templates folder (read-only reference inside the addon)"""
    bl_idname = "render.open_templates_folder"
    bl_label = "Open Bundled Templates Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Get addon directory
        addon_dir = get_addon_path()
        templates_path = os.path.join(addon_dir, "svg_templates")

        # Create folder if it doesn't exist
        if not os.path.exists(templates_path):
            try:
                os.makedirs(templates_path, exist_ok=True)
                self.report({'INFO'}, f"Created templates folder at {templates_path}")
            except Exception as e:
                self.report({'ERROR'}, f"Could not create templates folder: {e}")
                return {'CANCELLED'}

        # Open the folder
        try:
            import subprocess
            import platform

            if os.name == 'nt':  # Windows
                os.startfile(templates_path)
            elif os.name == 'posix':  # Linux or Mac
                if platform.system() == 'Darwin':  # macOS
                    subprocess.Popen(['open', templates_path])
                else:  # Linux
                    subprocess.Popen(['xdg-open', templates_path])

            self.report({'INFO'}, f"Opened templates folder: {templates_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Could not open folder: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


def _open_in_file_browser(path):
    """Open a folder in the OS file browser. Returns (ok, error)."""
    try:
        import subprocess
        import platform
        if os.name == 'nt':
            os.startfile(path)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return True, None
    except Exception as e:
        return False, str(e)


class RENDER_UL_template_folders(bpy.types.UIList):
    """List of user-configured SVG template resource folders."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        abspath = os.path.normpath(bpy.path.abspath(item.path)) if item.path else ""
        exists = bool(abspath) and os.path.isdir(abspath)
        row = layout.row(align=True)
        row.prop(item, "path", text="", emboss=False,
                 icon='FILE_FOLDER' if exists else 'ERROR')


class RENDER_OT_add_template_folder(Operator):
    """Add a folder to the SVG template resource list (can be a cloud/Drive path)"""
    bl_idname = "render.add_template_folder"
    bl_label = "Add Template Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs is None:
            self.report({'ERROR'}, "Could not access addon preferences")
            return {'CANCELLED'}
        prefs.svg_template_folders.add()
        prefs.svg_template_folders_index = len(prefs.svg_template_folders) - 1
        return {'FINISHED'}


class RENDER_OT_remove_template_folder(Operator):
    """Remove the selected folder from the SVG template resource list"""
    bl_idname = "render.remove_template_folder"
    bl_label = "Remove Template Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs is None:
            self.report({'ERROR'}, "Could not access addon preferences")
            return {'CANCELLED'}
        idx = prefs.svg_template_folders_index
        if 0 <= idx < len(prefs.svg_template_folders):
            prefs.svg_template_folders.remove(idx)
            prefs.svg_template_folders_index = max(0, idx - 1)
        return {'FINISHED'}


class RENDER_OT_create_em_home_folder(Operator):
    """Create the ExtendedMatrix home templates folder and add it to the list

    Creates ~/ExtendedMatrix/3D Survey Collection/svg_templates (part of the
    Extended Matrix ecosystem), registers it as a resource folder, and opens it.
    Nothing is created automatically on install — this is an explicit user action.
    """
    bl_idname = "render.create_em_home_templates_folder"
    bl_label = "Create ExtendedMatrix Home Folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs is None:
            self.report({'ERROR'}, "Could not access addon preferences")
            return {'CANCELLED'}

        path = get_em_home_templates()
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            self.report({'ERROR'}, f"Could not create folder: {e}")
            return {'CANCELLED'}

        # Add to the resource list if not already present
        norm = os.path.normpath(path)
        existing = {os.path.normpath(bpy.path.abspath(i.path))
                    for i in prefs.svg_template_folders if i.path}
        if norm not in existing:
            item = prefs.svg_template_folders.add()
            item.path = path
            prefs.svg_template_folders_index = len(prefs.svg_template_folders) - 1

        ok, err = _open_in_file_browser(path)
        if not ok:
            self.report({'WARNING'}, f"Folder created at {path} but could not open it: {err}")
        else:
            self.report({'INFO'}, f"ExtendedMatrix home templates folder ready: {path}")
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
        
        # Warning if file is not saved
        if not bpy.data.filepath:
            row = box.row()
            row.alert = True
            row.label(text="Save file first!", icon='ERROR')
        
        box.prop(scene, "ortho_render_output_path", text="")

        # Lighting
        box = layout.box()
        box.label(text="Lighting", icon='LIGHT')
        box.prop(scene, "ortho_render_create_lights")

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
        
        # SVG Export section
        box = layout.box()
        box.label(text="SVG Layout Export", icon='FILE_IMAGE')
        box.prop(scene, "ortho_template_family", text="Template")
        
        # Check if SVG template exists
        template_exists = bool(ensure_svg_templates_folder())
        has_saved_blend = bool(bpy.data.filepath)
        has_renders = False
        
        if not template_exists:
            box.label(text="SVG template not found", icon='ERROR')
            box.label(text="Please install the template files")
        elif not has_saved_blend:
            box.label(text="Save file before exporting SVG", icon='ERROR')
        else:
            # Check if we have renders available
            output_path = bpy.path.abspath(context.scene.ortho_render_output_path)
            if os.path.exists(output_path):
                # Check for at least one rendered view
                if context.active_object:
                    front_view = os.path.join(output_path, f"{context.active_object.name}_FR.png")
                    if os.path.exists(front_view):
                        has_renders = True
            
            if not has_renders:
                box.label(text="Render views before creating SVG", icon='INFO')
                box.label(text="At least one view is required")
        
        # Create SVG button
        row = box.row(align=True)
        row.scale_y = 1.2
        row.enabled = bool(template_exists and has_saved_blend and has_renders)
        row.operator("render.create_orthogonal_svg", icon='OUTLINER_OB_FONT')

        # Templates management
        box = layout.box()
        box.label(text="Templates Management", icon='FILEBROWSER')
        row = box.row(align=True)
        row.operator("render.open_templates_folder", icon='FOLDER_REDIRECT', text="Open Templates Folder")


# Function to make sure the SVG template folder exists and create it if not
def ensure_svg_templates_folder():
    """Return True if at least one SVG template is available in any search path.

    The bundled folder inside the addon always exists and ships with templates,
    so this normally returns True. User/EM-home/project folders are checked too,
    with user folders taking priority. Nothing is created automatically here.
    """
    possible_paths = get_template_search_paths()

    # Log paths
    print("Checking template folders in:")
    for path in possible_paths:
        print(f"  - {path}")

    # Find existing paths
    existing_paths = [p for p in possible_paths if os.path.exists(p)]

    # Check if any svg template exists
    has_template = False
    for path in existing_paths:
        template_files = [f for f in os.listdir(path) if f.endswith(".svg")]
        if template_files:
            has_template = True
            print(f"Found template(s) in {path}: {', '.join(template_files)}")
            break
    
    return has_template


def register():
    bpy.utils.register_class(OBJECT_OT_setup_orthogonal_render)
    bpy.utils.register_class(RENDER_OT_orthogonal_views)
    bpy.utils.register_class(RENDER_OT_create_orthogonal_svg)
    bpy.utils.register_class(RENDER_OT_open_templates_folder)
    bpy.utils.register_class(RENDER_UL_template_folders)
    bpy.utils.register_class(RENDER_OT_add_template_folder)
    bpy.utils.register_class(RENDER_OT_remove_template_folder)
    bpy.utils.register_class(RENDER_OT_create_em_home_folder)
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

    bpy.types.Scene.ortho_render_create_lights = BoolProperty(
        name="Create Light Rig",
        description="Create a three-point light rig (Key/Fill/Back) parented to the camera, "
                    "keyframed on every pose for per-view manual fine-tuning",
        default=True
    )

    bpy.types.Scene.ortho_template_family = EnumProperty(
        name="Template Family",
        description="Template family for SVG layout export",
        items=[
            ('FIXED_SHEET', "Fixed Sheet (A3)", "A3 paper, images fill available space"),
            ('FIXED_SCALE', "Fixed Scale", "True metric scale, paper size varies to fit"),
            ('LEGACY', "Legacy", "Original MASTER_*.svg templates"),
        ],
        default='FIXED_SHEET'
    )


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_orthogonal_render)
    bpy.utils.unregister_class(RENDER_OT_create_em_home_folder)
    bpy.utils.unregister_class(RENDER_OT_remove_template_folder)
    bpy.utils.unregister_class(RENDER_OT_add_template_folder)
    bpy.utils.unregister_class(RENDER_UL_template_folders)
    bpy.utils.unregister_class(RENDER_OT_open_templates_folder)
    bpy.utils.unregister_class(RENDER_OT_create_orthogonal_svg)
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
    del bpy.types.Scene.ortho_render_create_lights
    del bpy.types.Scene.ortho_template_family


if __name__ == "__main__":
    register()
