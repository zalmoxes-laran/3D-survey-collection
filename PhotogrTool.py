import bpy
import os
import json
from .functions import *
import xml.etree.ElementTree as ET
from bpy.types import Panel
from bpy_extras.io_utils import ExportHelper, ImportHelper


SUPPORTED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tiff", ".tif")


def _clean_undistorted_path(path):
    if not path:
        return ""
    return bpy.path.abspath(path).strip()


def resolve_undistorted_image_path(scene, camera_name):
    root_path = _clean_undistorted_path(scene.BL_undistorted_path)
    if not root_path:
        return None

    base_name, ext = os.path.splitext(camera_name)
    candidates = []

    # If camera name already has extension, try it first.
    if ext.lower() in SUPPORTED_IMAGE_EXTENSIONS:
        candidates.append(camera_name)
    else:
        chosen_ext = scene.my_image_format.lower()
        candidates.append(f"{camera_name}.{chosen_ext}")

    # Try known extensions as fallback.
    for fallback_ext in SUPPORTED_IMAGE_EXTENSIONS:
        candidates.append(f"{base_name}{fallback_ext}")
        candidates.append(f"{camera_name}{fallback_ext}")

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        full_path = os.path.join(root_path, candidate)
        if os.path.isfile(full_path):
            return full_path
    return None


def _find_project_camera_index(collection, camera_name):
    for idx, item in enumerate(collection):
        if item.object_name == camera_name:
            return idx
    return -1


def _camera_to_dict(item):
    return {
        "object_name": item.object_name,
        "image_name": item.image_name,
        "lens": item.lens,
        "sensor_width": item.sensor_width,
        "sensor_height": item.sensor_height,
        "clip_start": item.clip_start,
        "clip_end": item.clip_end,
        "location": list(item.location),
        "rotation_mode": item.rotation_mode,
        "rotation_euler": list(item.rotation_euler),
        "scale": list(item.scale),
    }


def _camera_payload_to_scene_item(payload, item):
    item.object_name = payload.get("object_name", "Camera")
    item.image_name = payload.get("image_name", "")
    item.lens = float(payload.get("lens", 35.0))
    item.sensor_width = float(payload.get("sensor_width", 36.0))
    item.sensor_height = float(payload.get("sensor_height", 24.0))
    item.clip_start = float(payload.get("clip_start", 0.1))
    item.clip_end = float(payload.get("clip_end", 1000.0))
    item.rotation_mode = payload.get("rotation_mode", "XYZ")

    location = payload.get("location", [0.0, 0.0, 0.0])
    rotation_euler = payload.get("rotation_euler", [0.0, 0.0, 0.0])
    scale = payload.get("scale", [1.0, 1.0, 1.0])
    if len(location) != 3:
        location = [0.0, 0.0, 0.0]
    if len(rotation_euler) != 3:
        rotation_euler = [0.0, 0.0, 0.0]
    if len(scale) != 3:
        scale = [1.0, 1.0, 1.0]
    item.location = location
    item.rotation_euler = rotation_euler
    item.scale = scale


def _store_camera_in_item(camera_object, item):
    item.object_name = camera_object.name
    item.image_name = camera_object.name
    item.lens = float(camera_object.data.lens)
    item.sensor_width = float(camera_object.data.sensor_width)
    item.sensor_height = float(camera_object.data.sensor_height)
    item.clip_start = float(camera_object.data.clip_start)
    item.clip_end = float(camera_object.data.clip_end)
    item.location = camera_object.location
    item.rotation_mode = camera_object.rotation_mode
    item.rotation_euler = camera_object.rotation_euler
    item.scale = camera_object.scale


def _apply_item_to_camera_object(item, camera_object):
    camera_object.data.lens = item.lens
    camera_object.data.sensor_width = item.sensor_width
    camera_object.data.sensor_height = item.sensor_height
    camera_object.data.clip_start = item.clip_start
    camera_object.data.clip_end = item.clip_end
    camera_object.location = item.location
    camera_object.rotation_mode = item.rotation_mode
    camera_object.rotation_euler = item.rotation_euler
    camera_object.scale = item.scale


def _camera_matches_add_filter(scene, camera_object):
    if not scene.photogr_add_only_with_image:
        return True
    return resolve_undistorted_image_path(scene, camera_object.name) is not None

class OGGETTO_OT_pick(bpy.types.Operator):
    """Select a canvas object"""
    bl_idname = "canvas.pick"
    bl_label = "Select a canvas object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.view_layer.objects.active and context.view_layer.objects.active.type == 'MESH':
            is_mesh = True
        else:
            is_mesh = False 
        return is_mesh

    # Questa funzione viene chiamata quando l'operatore è eseguito, ovvero quando l'utente seleziona l'oggetto.
    def execute(self, context):
        # Imposta l'oggetto attivo come oggetto selezionato per la tua proprietà
        context.scene.canvas_obj = context.active_object
        return {'FINISHED'}
'''
class set_background_cam(bpy.types.Operator):
    bl_idname = "set_background.cam"
    bl_label = "Set background camera"
    bl_options = {"REGISTER", "UNDO"}

    name_cam : StringProperty() # type: ignore

    def execute(self, context):
        cam = bpy.data.cameras[self.name_cam]
        clip_path = "/Users/emanueldemetrescu/Desktop/1917_b.jpg"

        clip = bpy.data.movieclips.load(clip_path)
        cam.show_background_images = True
        back_img = cam.background_images.new()
        back_img.source = 'MOVIE_CLIP'
        back_img.clip = clip
        back_img.clip_user.use_render_undistorted = True
        back_img.display_depth = 'FRONT'

        return {'FINISHED'} 
'''

class CameraDetails(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name") # type: ignore
    s_width: bpy.props.FloatProperty(name="Sensor Width") # type: ignore
    s_height: bpy.props.FloatProperty(name="Sensor Height") # type: ignore
    x: bpy.props.IntProperty(name="Resolution X") # type: ignore
    y: bpy.props.IntProperty(name="Resolution Y") # type: ignore


class ProjectCameraItem(bpy.types.PropertyGroup):
    object_name: bpy.props.StringProperty(name="Camera Name") # type: ignore
    image_name: bpy.props.StringProperty(name="Image Name") # type: ignore
    lens: bpy.props.FloatProperty(name="Lens", default=35.0) # type: ignore
    sensor_width: bpy.props.FloatProperty(name="Sensor Width", default=36.0) # type: ignore
    sensor_height: bpy.props.FloatProperty(name="Sensor Height", default=24.0) # type: ignore
    clip_start: bpy.props.FloatProperty(name="Clip Start", default=0.1) # type: ignore
    clip_end: bpy.props.FloatProperty(name="Clip End", default=1000.0) # type: ignore
    location: bpy.props.FloatVectorProperty(name="Location", size=3, default=(0.0, 0.0, 0.0)) # type: ignore
    rotation_mode: bpy.props.StringProperty(name="Rotation Mode", default="XYZ") # type: ignore
    rotation_euler: bpy.props.FloatVectorProperty(name="Rotation", size=3, default=(0.0, 0.0, 0.0)) # type: ignore
    scale: bpy.props.FloatVectorProperty(name="Scale", size=3, default=(1.0, 1.0, 1.0)) # type: ignore


class OBJECT_UL_project_cameras(bpy.types.UIList):
    bl_idname = "OBJECT_UL_project_cameras"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.label(text=item.object_name, icon='CAMERA_DATA')
        elif self.layout_type == "GRID":
            layout.alignment = 'CENTER'
            layout.label(text="", icon='CAMERA_DATA')


class OBJECT_OT_project_camera_add_selected(bpy.types.Operator):
    bl_idname = "project_camera.add_selected"
    bl_label = "Add Selected Cameras"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(ob.type == 'CAMERA' for ob in context.selected_objects)

    def execute(self, context):
        scene = context.scene
        added = 0
        updated = 0
        skipped = 0
        for camera_object in context.selected_objects:
            if camera_object.type != 'CAMERA':
                continue
            if not _camera_matches_add_filter(scene, camera_object):
                skipped += 1
                continue
            idx = _find_project_camera_index(scene.photogr_project_cameras, camera_object.name)
            if idx == -1:
                item = scene.photogr_project_cameras.add()
                added += 1
            else:
                item = scene.photogr_project_cameras[idx]
                updated += 1
            _store_camera_in_item(camera_object, item)
        if len(scene.photogr_project_cameras) > 0:
            scene.photogr_project_cameras_index = len(scene.photogr_project_cameras) - 1
        self.report({'INFO'}, f"Project cameras updated. Added: {added}, Updated: {updated}, Skipped: {skipped}")
        return {'FINISHED'}


class OBJECT_OT_project_camera_add_all_scene(bpy.types.Operator):
    bl_idname = "project_camera.add_all_scene"
    bl_label = "Add All Scene Cameras"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(ob.type == 'CAMERA' for ob in context.scene.objects)

    def execute(self, context):
        scene = context.scene
        added = 0
        updated = 0
        skipped = 0

        for camera_object in scene.objects:
            if camera_object.type != 'CAMERA':
                continue
            if not _camera_matches_add_filter(scene, camera_object):
                skipped += 1
                continue
            idx = _find_project_camera_index(scene.photogr_project_cameras, camera_object.name)
            if idx == -1:
                item = scene.photogr_project_cameras.add()
                added += 1
            else:
                item = scene.photogr_project_cameras[idx]
                updated += 1
            _store_camera_in_item(camera_object, item)

        if len(scene.photogr_project_cameras) > 0:
            scene.photogr_project_cameras_index = len(scene.photogr_project_cameras) - 1
        self.report({'INFO'}, f"Project cameras updated. Added: {added}, Updated: {updated}, Skipped: {skipped}")
        return {'FINISHED'}


class OBJECT_OT_project_camera_remove(bpy.types.Operator):
    bl_idname = "project_camera.remove"
    bl_label = "Remove Active Camera"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.photogr_project_cameras) > 0

    def execute(self, context):
        scene = context.scene
        idx = scene.photogr_project_cameras_index
        if idx < 0 or idx >= len(scene.photogr_project_cameras):
            return {'CANCELLED'}
        scene.photogr_project_cameras.remove(idx)
        scene.photogr_project_cameras_index = min(idx, len(scene.photogr_project_cameras) - 1)
        return {'FINISHED'}


class OBJECT_OT_project_camera_clear(bpy.types.Operator):
    bl_idname = "project_camera.clear"
    bl_label = "Clear Camera List"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.photogr_project_cameras) > 0

    def execute(self, context):
        scene = context.scene
        scene.photogr_project_cameras.clear()
        scene.photogr_project_cameras_index = 0
        self.report({'INFO'}, "Project camera list cleared")
        return {'FINISHED'}


class OBJECT_OT_project_camera_export_active(bpy.types.Operator, ExportHelper):
    bl_idname = "project_camera.export_active"
    bl_label = "Export Active Camera"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'}) # type: ignore

    @classmethod
    def poll(cls, context):
        scene = context.scene
        idx = scene.photogr_project_cameras_index
        return len(scene.photogr_project_cameras) > 0 and 0 <= idx < len(scene.photogr_project_cameras)

    def execute(self, context):
        scene = context.scene
        item = scene.photogr_project_cameras[scene.photogr_project_cameras_index]
        payload = {"version": 1, "cameras": [_camera_to_dict(item)]}
        with open(self.filepath, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        self.report({'INFO'}, f"Camera exported to {self.filepath}")
        return {'FINISHED'}


class OBJECT_OT_project_camera_export_all(bpy.types.Operator, ExportHelper):
    bl_idname = "project_camera.export_all"
    bl_label = "Export All Cameras"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'}) # type: ignore

    @classmethod
    def poll(cls, context):
        return len(context.scene.photogr_project_cameras) > 0

    def execute(self, context):
        scene = context.scene
        payload = {
            "version": 1,
            "cameras": [_camera_to_dict(item) for item in scene.photogr_project_cameras],
        }
        with open(self.filepath, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        self.report({'INFO'}, f"{len(payload['cameras'])} cameras exported to {self.filepath}")
        return {'FINISHED'}


class OBJECT_OT_project_camera_import(bpy.types.Operator, ImportHelper):
    bl_idname = "project_camera.import"
    bl_label = "Import Camera File"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'}) # type: ignore
    create_missing_cameras: bpy.props.BoolProperty( # type: ignore
        name="Create Missing Cameras in Scene",
        default=True,
        description="If enabled, imported cameras that do not exist will be created in the scene",
    )

    def execute(self, context):
        scene = context.scene
        try:
            with open(self.filepath, "r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except Exception as exc:
            self.report({'ERROR'}, f"Cannot read camera file: {exc}")
            return {'CANCELLED'}

        imported = payload.get("cameras")
        if imported is None and "object_name" in payload:
            imported = [payload]
        if not isinstance(imported, list):
            self.report({'ERROR'}, "Invalid camera file format")
            return {'CANCELLED'}

        added = 0
        updated = 0
        created = 0
        for cam_payload in imported:
            camera_name = cam_payload.get("object_name", "Camera")
            idx = _find_project_camera_index(scene.photogr_project_cameras, camera_name)
            if idx == -1:
                item = scene.photogr_project_cameras.add()
                added += 1
            else:
                item = scene.photogr_project_cameras[idx]
                updated += 1
            _camera_payload_to_scene_item(cam_payload, item)

            if self.create_missing_cameras:
                camera_obj = bpy.data.objects.get(item.object_name)
                if camera_obj is None:
                    cam_data = bpy.data.cameras.new(item.object_name)
                    camera_obj = bpy.data.objects.new(item.object_name, cam_data)
                    scene.collection.objects.link(camera_obj)
                    created += 1
                if camera_obj.type == 'CAMERA':
                    _apply_item_to_camera_object(item, camera_obj)

        if len(scene.photogr_project_cameras) > 0:
            scene.photogr_project_cameras_index = len(scene.photogr_project_cameras) - 1
        self.report(
            {'INFO'},
            f"Imported cameras. Added: {added}, Updated: {updated}, Created in scene: {created}",
        )
        return {'FINISHED'}

class set_camera_type(bpy.types.Operator):
    bl_idname = "set_camera.type"
    bl_label = "Set Camera Type"
    bl_options = {"REGISTER", "UNDO"}

    name_cam : StringProperty() # type: ignore

    def execute(self, context):
        scene = context.scene
        context.scene.camera_type = self.name_cam
        selected_objects = context.selected_objects
        selected_camera_id = bpy.context.scene.camera_enum
        selected_profile = scene.camera_details.get(selected_camera_id)
        if not selected_camera_id or selected_profile is None:
            self.report({'ERROR'}, "No camera profile selected")
            return {'CANCELLED'}
        lens = context.scene.camera_lens
        for ob in selected_objects:
            #selected_camera_id = ob.name
            if ob.type in ['CAMERA']:
                set_up_lens(ob, float(selected_profile.s_width), float(selected_profile.s_height), lens)
        set_up_scene(int(selected_profile.x), int(selected_profile.y), True)
        return {'FINISHED'} 

class OBJECT_OT_BetterCameras(bpy.types.Operator):
    bl_idname = "better.cameras"
    bl_label = "Better Cameras"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
            
        if context.view_layer.objects.active and context.view_layer.objects.active.type == 'CAMERA':
            is_cam = True
        else:
            is_cam = False 
        return is_cam

    def execute(self, context):
        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for cam in selection:
            cam.select_set(True)
            cam.data.show_limits = True
            cam.data.clip_start = 0.1
            cam.data.clip_end = 4
            cam.scale[0] = 0.1
            cam.scale[1] = 0.1
            cam.scale[2] = 0.1
        return {'FINISHED'}

class OBJECT_OT_NoBetterCameras(bpy.types.Operator):
    bl_idname = "nobetter.cameras"
    bl_label = "Disable Better Cameras"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
            
        if context.view_layer.objects.active and context.view_layer.objects.active.type == 'CAMERA':
            is_cam = True
        else:
            is_cam = False 
        return is_cam
            
            
            

    def execute(self, context):
        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for cam in selection:
            cam.select_set(True)
            cam.data.show_limits = False
        return {'FINISHED'}

class OBJECT_OT_CreateCameraImagePlane(bpy.types.Operator):
    """Associate an undistorted photo to this camera"""
    bl_idname= "object.createcameraimageplane"
    bl_label="Camera Image Plane"
    bl_options={'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return scene.camera is not None and bool(_clean_undistorted_path(scene.BL_undistorted_path))

    def SetupDriverVariables(self, driver, imageplane):
        camAngle = driver.variables.new()
        camAngle.name = 'camAngle'
        camAngle.type = 'SINGLE_PROP'
        camAngle.targets[0].id = imageplane.parent
        camAngle.targets[0].data_path="data.angle"

        depth = driver.variables.new()
        depth.name = 'depth'
        depth.type = 'TRANSFORMS'
        depth.targets[0].id = imageplane
        depth.targets[0].data_path = 'location'
        depth.targets[0].transform_type = 'LOC_Z'
        depth.targets[0].transform_space = 'LOCAL_SPACE'

    def SetupDriversForImagePlane(self, imageplane):
        driver = imageplane.driver_add('scale',1).driver
        driver.type = 'SCRIPTED'
        self.SetupDriverVariables( driver, imageplane)
        driver.expression ="-depth*tan(camAngle/2)*bpy.context.scene.render.resolution_y * bpy.context.scene.render.pixel_aspect_y/(bpy.context.scene.render.resolution_x * bpy.context.scene.render.pixel_aspect_x)"
        driver = imageplane.driver_add('scale',0).driver
        driver.type= 'SCRIPTED'
        self.SetupDriverVariables( driver, imageplane)
        driver.expression ="-depth*tan(camAngle/2)"
        bpy.context.view_layer.update()


    # get selected camera (might traverse children of selected object until a camera is found?)
    # for now just pick the active object


    def mat_from_image(self, img,ob,alpha):
        mat = bpy.data.materials.new(name='M_'+ ob.name)
        mat.use_nodes = True
        material_output = None
        for node in mat.node_tree.nodes:
            if node.type == "OUTPUT_MATERIAL":
                material_output = node
                break

        bsdf = mat.node_tree.nodes["Principled BSDF"]
        texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texImage.image = img
        texImage.location = (-460,90)
        mat.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])
        mat.node_tree.links.new(bsdf.outputs['BSDF'], material_output.inputs[0])
        bsdf.inputs['Alpha'].default_value = 0.5
        mat.blend_method = 'BLEND'
        #output_node = mat.node_tree.nodes()

        """ if alpha == True:
            alpha_node = mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
            alpha_node.location = (-80,-518)
            mixshader_node = mat.node_tree.nodes.new('ShaderNodeMixShader') 
            mixshader_node.location = (-75,-370)
            mat.node_tree.links.new(bsdf.outputs[0], mixshader_node.inputs[1])
            mat.node_tree.links.new(alpha_node.outputs[0], mixshader_node.inputs[2])
            mat.node_tree.links.new(mixshader_node.outputs['Shader'], material_output.inputs[0])
            mat.blend_method = 'BLEND' 
        """

        # Assign it to object
        if ob.data.materials:
            ob.data.materials[0] = mat
        else:
            ob.data.materials.append(mat)

        #mat.node_tree.nodes.active = texImage
        return mat, texImage

    def createImagePlaneForCamera(self, camera):
        imageplane = None
        scene = bpy.context.scene
        if not _clean_undistorted_path(scene.BL_undistorted_path):
            self.report({'ERROR'}, "Set the undistorted images path first")
            return {'CANCELLED'}
        try:
            depth = 2

            #create imageplane
            bpy.ops.mesh.primitive_plane_add()#radius = 0.5)
            imageplane = bpy.context.active_object
            cameraname = self.correctcameraname(camera.name)
            imageplane.name = ("objplane_"+cameraname)
            bpy.ops.object.editmode_toggle()
            bpy.ops.mesh.select_all(action='TOGGLE')
            bpy.ops.transform.resize( value=(0.5,0.5,0.5))
            bpy.ops.uv.smart_project(angle_limit=66,island_margin=0, area_weight=0)
            bpy.ops.uv.select_all(action='TOGGLE')
            bpy.ops.transform.rotate(value=1.5708, orient_axis='Z')
            
            bpy.ops.object.editmode_toggle()

            imageplane.location = (0,0,-depth)
            imageplane.parent = camera

            #calculate scale
            #REPLACED WITH CREATING EXPRESSIONS
            self.SetupDriversForImagePlane(imageplane)

            #setup material
            activename = bpy.path.clean_name(bpy.context.view_layer.objects.active.name)
            image_path = resolve_undistorted_image_path(scene, camera.name)
            if image_path is None:
                self.report({'ERROR'}, f"Image not found for camera '{camera.name}' in Undistorted path")
                return {'CANCELLED'}
            image_cam = bpy.data.images.load(image_path, check_existing=True)
            self.mat_from_image(image_cam,imageplane,True)

            #bpy.context.object.data.uv_layers.active.data[0].image = 
            #bpy.ops.view3d.tex_to_material()

        except Exception as e:
            if imageplane is not None:
                imageplane.select_set(False)
            camera.select_set(True)
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

    def execute(self, context):
#        camera = bpy.context.active_object #bpy.data.objects['Camera']
        scene = context.scene
        undistortedpath = _clean_undistorted_path(scene.BL_undistorted_path)
        cam_ob = scene.camera

        if not undistortedpath:
            self.report({'ERROR'}, "Set the Undistort path before activating this command")
            return {'CANCELLED'}
        if cam_ob is None:
            self.report({'ERROR'}, "No active scene camera")
            return {'CANCELLED'}
        else:
            obj_exists = False
            for obj in cam_ob.children:
                if obj.name.startswith("objplane_"):
                    obj.hide_viewport = False
                    obj_exists = True
                    bpy.ops.object.select_all(action='DESELECT')
                    context.view_layer.objects.active = obj
                    obj.select_set(True)
                    return {'FINISHED'}
            if obj_exists is False:
                camera = bpy.context.scene.camera
                return self.createImagePlaneForCamera(camera)

class TOGGLE_OBJ_VISIBILITY(bpy.types.Operator):
    """(add a photo to activate this button)"""
    bl_idname = "object.toggle_obj_visibility"
    bl_label = "Show/Hide the camera's photo"

    @classmethod
    def poll(cls, context):
            scene = context.scene
            return check_children_plane(scene.camera)

    def execute(self, context):
        cam_ob = context.scene.camera
        if cam_ob is not None:
            for obj in cam_ob.children:
                if obj.name.startswith("objplane_"):
                    obj.hide_viewport = not obj.hide_viewport
        return {'FINISHED'}

class OBJECT_OT_paintcam(bpy.types.Operator):
    """Add a photo to the current camera to activate this button"""
    bl_idname = "paint.cam"
    bl_label = "Paint selected from current cam"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
            scene = context.scene
            return (
                scene.camera is not None
                and bool(_clean_undistorted_path(scene.BL_undistorted_path))
                and check_children_plane(scene.camera)
                and context.preferences.filepaths.image_editor
            )

    def execute(self, context):

        scene = context.scene
        undistortedpath = _clean_undistorted_path(scene.BL_undistorted_path)
        cam_ob = scene.camera

        if not undistortedpath:
            self.report({'ERROR'}, "Set the Undistort path before activating this command")
            return {'CANCELLED'}
        else:
            for obj in cam_ob.children:
                if obj.name.startswith("objplane_"):
                    obj.hide_viewport = True
            bpy.ops.view3d.view_camera()
            bpy.ops.object.select_all(action='DESELECT')
            scene.canvas_obj.select_set(True)
            bpy.ops.paint.texture_paint_toggle()
            bpy.types.View3DOverlay.show_overlays = False
            bpy.ops.image.project_edit()
            obj_camera = bpy.context.scene.camera
    
            image_path = resolve_undistorted_image_path(scene, obj_camera.name)
            if image_path is None:
                self.report({'ERROR'}, f"Image not found for camera '{obj_camera.name}'")
                return {'CANCELLED'}
            cleanpath = bpy.path.abspath(image_path)
            bpy.ops.image.external_edit(filepath=cleanpath)

            bpy.types.View3DOverlay.show_overlays = True
            bpy.ops.paint.texture_paint_toggle()

        return {'FINISHED'}

    def correctcameraname(self, cameraname):
        extensions = ['.JPG','.PNG','.JPEG','.TIFF']
        for extension in extensions:
            if cameraname.upper().endswith(extension):
                return cameraname
        return cameraname + '.' + bpy.context.scene.my_image_format

class OBJECT_OT_applypaintcam(bpy.types.Operator):
    bl_idname = "applypaint.cam"
    bl_label = "Apply paint"
    bl_options = {"REGISTER"}

    def execute(self, context):
        bpy.ops.paint.texture_paint_toggle()
        bpy.ops.image.project_apply()
        bpy.ops.paint.texture_paint_toggle()
        return {'FINISHED'}

class OBJECT_OT_parse_cams(bpy.types.Operator):
    bl_idname = "parse.cams"
    bl_label = "parse cameras"
    bl_options = {"REGISTER"}

    def execute(self, context):

        path = bpy.utils.script_paths(subdir="Addons/3D-survey-collection/src/", user_pref=True, check_all=False, use_user=True)
        path2xml = os.path.join(path[0], "cams.xml")
        tree = ET.parse(path2xml)
        root = tree.getroot()
        
        scene = context.scene
        scene.camera_details.clear()
        
        for cam in root.findall('cam'):
            name = cam.get('name')
            camera_item = scene.camera_details.add()
            camera_item.name = name
            camera_item.s_width = float(cam.find('s_width').text)
            camera_item.s_height = float(cam.find('s_height').text)
            camera_item.x = int(cam.find('x').text)
            camera_item.y = int(cam.find('y').text)

        return {'FINISHED'}

def get_camera_enum_items(self, context):
    items = [(cam.name, cam.name, "") for cam in bpy.context.scene.camera_details]
    return items

def update_camera_details(self, context):
    selected_cam_name = context.scene.selected_camera
    selected_cam = next((cam for cam in context.scene.camera_details if cam.name == selected_cam_name), None)
    if selected_cam:
        print(f"Dettagli selezionati: {selected_cam.name}, {selected_cam.s_width}, {selected_cam.s_height}, {selected_cam.x}, {selected_cam.y}")
    else:
        print("Nessuna camera selezionata")

class ToolsPanelPhotogrTool:
    bl_label = "Photogrammetry paint"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        cam_ob = None
        cam_ob = scene.camera

        row = layout.row()
        row.label(text="Setup scene:", icon='PACKAGE')


        row = layout.row()
        row.label(text="Folder with undistorted images:")
        row = layout.row()
        split = row.split(factor=0.7)
        col1 = split.column()
        col1.prop(context.scene, 'BL_undistorted_path', toggle = True, text="")

        # Menu a tendina per la selezione del formato
        split2 = split.split(factor=1)
        col2 = split2.column()
        col2.prop(scene, 'my_image_format', text="")


        row = layout.row()

        if cam_ob is None:
            row = layout.row()
            row.label(text="Please, add a Cam to see tools here")

        else:
            #camera_type = context.scene.camera_type
            obj = context.object
            obj_selected = context.view_layer.objects.active
            cam_cam = scene.camera.data
            #row = layout.row()
            #op = row.operator("set_background.cam", icon="FILE_TICK", text='BG Cam')
            #op.name_cam = "Camera"
            row = layout.row()
            row.label(text="Set selected cam(s) as:", icon='CON_CAMERASOLVER')
            row = layout.row()

            # Suddividi la riga con un fattore di 0.5 per la prima colonna
            split = row.split(factor=0.5)
            col1 = split.column()
            col1.prop(scene, "camera_enum", text="")

            # Nello spazio restante (50%), suddividi ulteriormente per dare alla seconda colonna il 70% di questo spazio,
            # che corrisponde al 35% dello spazio totale.
            split2 = split.split(factor=0.7)
            col2 = split2.column()
            col2.prop(scene, 'camera_lens', icon='BLENDER', toggle=True, text='Lens')

            # La terza colonna occupa automaticamente il restante spazio
            col3 = split2.column()
            col3.operator("parse.cams", icon="FILE_TICK", text='')

            row = layout.row()
            row.operator("set_camera.type", icon="FILE_TICK", text='Apply')

            row = layout.row()
            row.operator("object.unify_meshes", icon="PLUS", text='Temporary Merge')
            row.operator("object.separate_meshes", icon="PLUS", text='Respawn meshes')

            row = layout.row()
            row.label(text="Visual mode:", icon='PLUS')
            row = layout.row()
            split = row.split()
            col = split.column()
            col.operator("better.cameras", icon="PLUS", text='Better Cams')
            col = split.column()
            col.operator("nobetter.cameras", icon="PLUS", text='Disable Better Cams')
            row = layout.row()

            if cam_ob is not None:
                row = layout.row()

                row.label(text="Active Cam: " + cam_ob.name, icon="CAMERA_DATA")
                has_undistorted_path = bool(_clean_undistorted_path(scene.BL_undistorted_path))
                row = layout.row(align=True)
                row.enabled = has_undistorted_path
                row.operator("object.createcameraimageplane", icon="PLUS", text='Load undistorted photo')
                row = layout.row(align=True)
                row.operator("object.toggle_obj_visibility", icon='HIDE_OFF', text="Show/Hide loaded photo")
                if not has_undistorted_path:
                    layout.label(text="Set Undistorted Path to enable photo loading", icon='INFO')

                row = layout.row()
                row.prop(cam_cam, "lens")
                row = layout.row()
                row.label(text="Clip from-to")
                row.prop(cam_cam, "clip_start", text="")
                row.prop(cam_cam, "clip_end", text="")
                

                row = layout.row()

                camera = context.scene.camera  # Ottiene la camera attiva della scena
                material = self.trova_objplane_material(camera)
                
                if material is not None and hasattr(material, 'node_tree'):
                    bsdf = material.node_tree.nodes.get('Principled BSDF')
                    if bsdf is not None:
                        row.prop(bsdf.inputs['Alpha'], 'default_value', text="Camera transparency")
                    else:
                        row.label(text="Principled BSDF found")
                else:
                    row.label(text="Camera Texture not present")


                layout.label(text="Canvas object:", icon="NODE_TEXTURE")
                # Prop_search per selezionare un oggetto da una lista
                layout.prop_search(scene, "canvas_obj", scene, "objects", text="")
                # Bottone per attivare l'operatore di selezione
                layout.operator("canvas.pick", text="or selected obj -> Canvas")
                
                row = layout.row()
                is_cam_ob_plane = check_children_plane(cam_ob)


                #row.label(text="Active object: " + obj.name)

                # Accesso alle preferenze di Blender
                prefs = context.preferences
                filepaths = prefs.filepaths
                # Aggiunge un widget per modificare il percorso dell'editor di immagini
                row = layout.row()
                row.label(text="Set an image editor executable:")
                layout.prop(filepaths, "image_editor", text="")
                row = layout.row()
                row.enabled = has_undistorted_path
                row.operator("paint.cam", icon="PLUS", text='Paint active from cam')

                self.layout.operator("applypaint.cam", icon="PLUS", text='Apply paint')
                self.layout.operator("savepaint.cam", icon="PLUS", text='Save modified texs')
                row = layout.row()

                project_box = layout.box()
                project_box.label(text="Project Cameras", icon='OUTLINER_OB_CAMERA')
                project_box.template_list(
                    "OBJECT_UL_project_cameras",
                    "",
                    scene,
                    "photogr_project_cameras",
                    scene,
                    "photogr_project_cameras_index",
                    rows=4,
                )
                row = project_box.row(align=True)
                row.operator("project_camera.add_selected", text="Add Selected", icon='ADD')
                row.operator("project_camera.add_all_scene", text="Add All Scene", icon='OUTLINER_OB_CAMERA')
                row = project_box.row()
                row.prop(scene, "photogr_add_only_with_image", text="Only cameras with undistorted image")
                scene_cameras = [ob for ob in scene.objects if ob.type == 'CAMERA']
                total_scene_cameras = len(scene_cameras)
                if scene.photogr_add_only_with_image:
                    matching_scene_cameras = sum(
                        1 for cam in scene_cameras if resolve_undistorted_image_path(scene, cam.name) is not None
                    )
                    project_box.label(
                        text=f"Scene cameras with image: {matching_scene_cameras}/{total_scene_cameras}",
                        icon='INFO',
                    )
                else:
                    project_box.label(
                        text=f"Scene cameras available: {total_scene_cameras}",
                        icon='INFO',
                    )
                row = project_box.row(align=True)
                row.operator("project_camera.remove", text="", icon='REMOVE')
                row.operator("project_camera.clear", text="", icon='TRASH')

                row = project_box.row(align=True)
                row.operator("project_camera.export_active", text="Export Active", icon='EXPORT')
                row.operator("project_camera.export_all", text="Export All", icon='EXPORT')
                row = project_box.row()
                row.operator("project_camera.import", text="Import Camera File", icon='IMPORT')
            else:
                row.label(text="!!! Import some cams to start !!!")

    def trova_objplane_material(self, camera):
        # Cerca tra i figli della camera per un oggetto che inizia con "objplane_"
        for child in camera.children:
            if child.name.startswith("objplane_"):
                # Assicurati che l'oggetto abbia dei materiali
                if len(child.material_slots) > 0:
                    # Restituisci il primo materiale dell'oggetto
                    return child.material_slots[0].material
        # Restituisci None se nessun oggetto o materiale corrispondente è stato trovato
        return None

class VIEW3D_PT_PhotogrTool(Panel, ToolsPanelPhotogrTool):
    bl_category = "3DSC"
    bl_idname = "VIEW3D_PT_PhotogrTool"
    bl_context = "objectmode"

class Camera_menu(bpy.types.Menu):
    bl_label = "Custom Menu"
    bl_idname = "OBJECT_MT_Camera_menu"

    def draw(self, context):
        camera_type_list = context.scene.camera_list
        idx = 0
        layout = self.layout
        while idx < len(camera_type_list):
            op = layout.operator(
                    "set_camera.type", text=camera_type_list[idx].name_cam, emboss=False, icon="RIGHTARROW")
            op.name_cam = camera_type_list[idx].name_cam
            idx +=1

classes = [
    CameraDetails,
    ProjectCameraItem,
    OBJECT_UL_project_cameras,
    OBJECT_OT_project_camera_add_selected,
    OBJECT_OT_project_camera_add_all_scene,
    OBJECT_OT_project_camera_remove,
    OBJECT_OT_project_camera_clear,
    OBJECT_OT_project_camera_export_active,
    OBJECT_OT_project_camera_export_all,
    OBJECT_OT_project_camera_import,
    OBJECT_OT_parse_cams,
    OBJECT_OT_applypaintcam,
    OBJECT_OT_BetterCameras,
    OBJECT_OT_NoBetterCameras,
    OBJECT_OT_paintcam,
    OBJECT_OT_CreateCameraImagePlane,
    set_camera_type,
    #set_background_cam,
    VIEW3D_PT_PhotogrTool,
    Camera_menu,
    OGGETTO_OT_pick,
    TOGGLE_OBJ_VISIBILITY
    ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.camera_details = bpy.props.CollectionProperty(type=CameraDetails)
    bpy.types.Scene.photogr_project_cameras = bpy.props.CollectionProperty(type=ProjectCameraItem)
    bpy.types.Scene.photogr_project_cameras_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.photogr_add_only_with_image = bpy.props.BoolProperty(
        name="Only cameras with undistorted image",
        default=False,
        description="When enabled, Add Selected/Add All Scene include only cameras with a matching image in Undistorted Path",
    )
    bpy.types.Scene.selected_camera = bpy.props.StringProperty(name="Selected Camera", update=update_camera_details)

    # Aggiungi questa property alla registrazione
    bpy.types.Scene.camera_enum = bpy.props.EnumProperty(items=get_camera_enum_items, update=update_camera_details)
    bpy.types.Scene.canvas_obj = bpy.props.PointerProperty(name="Canvas", type=bpy.types.Object)

    bpy.types.Scene.my_image_format = bpy.props.EnumProperty(
        items=[
            ('JPG', "JPG", "JPG Format"),
            ('JPEG', "JPEG", "JPEG Format"),
            ('PNG', "PNG", "PNG Format"),
            ('TIFF', "TIFF", "TIFF Format"),
            # Aggiungi qui altri formati se necessario
        ],
        name="Image Format",
        description="Select image format"#,
        #update=update_format
    )

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.camera_details
    del bpy.types.Scene.photogr_project_cameras
    del bpy.types.Scene.photogr_project_cameras_index
    del bpy.types.Scene.photogr_add_only_with_image
    del bpy.types.Scene.selected_camera
    del bpy.types.Scene.camera_enum
    del bpy.types.Scene.canvas_obj
    del bpy.types.Scene.my_image_format
