import bpy
import os
from .functions import *
import xml.etree.ElementTree as ET


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

class CameraDetails(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name") # type: ignore
    s_width: bpy.props.FloatProperty(name="Sensor Width") # type: ignore
    s_height: bpy.props.FloatProperty(name="Sensor Height") # type: ignore
    x: bpy.props.IntProperty(name="Resolution X") # type: ignore
    y: bpy.props.IntProperty(name="Resolution Y") # type: ignore

class set_camera_type(bpy.types.Operator):
    bl_idname = "set_camera.type"
    bl_label = "Set Camera Type"
    bl_options = {"REGISTER", "UNDO"}

    name_cam : StringProperty() # type: ignore

    def execute(self, context):
        scene = context.scene
        context.scene.camera_type = self.name_cam
        selected_objects = context.selected_objects
        selected_camera_id = bpy.context.scene.selected_camera
        #s_width, s_height, x, y = parse_cam_xml(self.name_cam)
        lens = context.scene.camera_lens
        for ob in selected_objects:
            if ob.type in ['CAMERA']:
                set_up_lens(ob, float(scene.camera_details[selected_camera_id].s_width), float(scene.camera_details[selected_camera_id].s_height), lens)
        set_up_scene(int(scene.camera_details[selected_camera_id].x),int(scene.camera_details[selected_camera_id].y),True)
        return {'FINISHED'} 

class OBJECT_OT_BetterCameras(bpy.types.Operator):
    bl_idname = "better.cameras"
    bl_label = "Better Cameras"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for cam in selection:
            cam.select_set(True)
            cam.data.show_limits = True
            cam.data.clip_start = 0.5
            cam.data.clip_end = 4
            cam.scale[0] = 0.1
            cam.scale[1] = 0.1
            cam.scale[2] = 0.1
        return {'FINISHED'}

class OBJECT_OT_NoBetterCameras(bpy.types.Operator):
    bl_idname = "nobetter.cameras"
    bl_label = "Disable Better Cameras"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selection = bpy.context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for cam in selection:
            cam.select_set(True)
            cam.data.show_limits = False
        return {'FINISHED'}

#______________________________________________________________

class OBJECT_OT_CreateCameraImagePlane(bpy.types.Operator):
    """Create image plane for camera"""
    bl_idname= "object.createcameraimageplane"
    bl_label="Camera Image Plane"
    bl_options={'REGISTER', 'UNDO'}
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
        #driver.expression ="-depth*math.tan(camAngle/2)*resolution_y*pixel_y/(resolution_x*pixel_x)"
        driver.expression ="-depth*tan(camAngle/2)*bpy.context.scene.render.resolution_y * bpy.context.scene.render.pixel_aspect_y/(bpy.context.scene.render.resolution_x * bpy.context.scene.render.pixel_aspect_x)"
        driver = imageplane.driver_add('scale',0).driver
        driver.type= 'SCRIPTED'
        self.SetupDriverVariables( driver, imageplane)
        driver.expression ="-depth*tan(camAngle/2)"

    # get selected camera (might traverse children of selected object until a camera is found?)
    # for now just pick the active object
        

    def createImagePlaneForCamera(self, camera):
        imageplane = None
        if not bpy.context.scene.BL_undistorted_path:
            raise Exception("Hey Buddy, you have to set the undistorted images path !")
        try:
            depth = 2

            #create imageplane
            bpy.ops.mesh.primitive_plane_add()#radius = 0.5)
            imageplane = bpy.context.active_object
            cameraname = correctcameraname(camera.name)
            imageplane.name = ("objplane_"+cameraname)
            bpy.ops.object.parent_set(type='OBJECT', keep_transform=False)
            bpy.ops.object.editmode_toggle()
            bpy.ops.mesh.select_all(action='TOGGLE')
            bpy.ops.transform.resize( value=(0.5,0.5,0.5))
            bpy.ops.uv.smart_project(angle_limit=66,island_margin=0, user_area_weight=0)
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
            undistortedpath = bpy.context.scene.BL_undistorted_path
            image_cam = bpy.data.images.load(undistortedpath+cameraname)
            mat_from_image(image_cam,imageplane,True)

            #bpy.context.object.data.uv_layers.active.data[0].image = 
            #bpy.ops.view3d.tex_to_material()

        except Exception as e:
            imageplane.select_set(False)
            camera.select_set(True)
            raise e
        return {'FINISHED'}

    def execute(self, context):
#        camera = bpy.context.active_object #bpy.data.objects['Camera']
        scene = context.scene
        undistortedpath = scene.BL_undistorted_path
        cam_ob = scene.camera

        if not undistortedpath:
            raise Exception("Set the Undistort path before to activate this command")
        else:
            obj_exists = False
            for obj in cam_ob.children:
                if obj.name.startswith("objplane_"):
                    obj.hide = False
                    obj_exists = True
                    bpy.ops.object.select_all(action='DESELECT')
                    scene.objects.active = obj
                    obj.select_set(True)
                    return {'FINISHED'}
            if obj_exists is False:
                camera = bpy.context.scene.camera
                return self.createImagePlaneForCamera(camera)

class OBJECT_OT_paintcam(bpy.types.Operator):
    bl_idname = "paint.cam"
    bl_label = "Paint selected from current cam"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        scene = context.scene
        undistortedpath = bpy.context.scene.BL_undistorted_path
        cam_ob = bpy.context.scene.camera

        if not undistortedpath:
            raise Exception("Set the Undistort path before to activate this command")
        else:
            for obj in cam_ob.children:
                if obj.name.startswith("objplane_"):
                    obj.hide_viewport = True
            bpy.ops.paint.texture_paint_toggle()
            #bpy.context.space_data.show_only_render = True
            bpy.types.View3DOverlay.show_overlays = False
            bpy.ops.image.project_edit()
            obj_camera = bpy.context.scene.camera
    
            undistortedphoto = undistortedpath+correctcameraname(obj_camera.name)
            cleanpath = bpy.path.abspath(undistortedphoto)
            bpy.ops.image.external_edit(filepath=cleanpath)

            bpy.types.View3DOverlay.show_overlays = True
            #bpy.context.space_data.show_only_render = False
            bpy.ops.paint.texture_paint_toggle()

        return {'FINISHED'}

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


""" def parse_cam_xml(name_cam):
    # if name_cam is not "just_parse", the function will return the parameters for the cam
    path = bpy.utils.script_paths(subdir="Addons/3D-survey-collection/src/", user_pref=True, check_all=False, use_user=True)
    path2xml = os.path.join(path[0],"cams.xml")
    tree = ET.parse(path2xml)
    root = tree.getroot()
    scene = bpy.context.scene
    
    if name_cam == "just_parse":
        #scene.camera_list = []
        scene.camera_list.clear()
        idx = 0
        for cam in root.findall('cam'):
            #rank = country.find('rank').text
            name = cam.get('name')
            scene.camera_list.add()
            scene.camera_list[idx].name_cam = name
            idx +=1
            print(name)
        return
    else:
        for cam in root.findall('cam'):
            name = cam.get('name')
            if name_cam == name:
                s_width = cam.find('s_width').text
                s_height = cam.find('s_height').text
                x = cam.find('x').text
                y = cam.find('y').text
        return s_width, s_height, x, y """

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

classes = [
    CameraDetails,
    OBJECT_OT_parse_cams]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.camera_details = bpy.props.CollectionProperty(type=CameraDetails)
    bpy.types.Scene.selected_camera = bpy.props.StringProperty(name="Selected Camera", update=update_camera_details)



    # Aggiungi questa property alla registrazione
    bpy.types.Scene.camera_enum = bpy.props.EnumProperty(items=get_camera_enum_items, update=update_camera_details)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.camera_details
    del bpy.types.Scene.selected_camera
