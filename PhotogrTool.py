import bpy
import os
from .functions import *
import xml.etree.ElementTree as ET
from bpy.types import Panel


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
        selected_camera_id = bpy.context.scene.camera_enum
        lens = context.scene.camera_lens
        for ob in selected_objects:
            #selected_camera_id = ob.name
            if ob.type in ['CAMERA']:
                set_up_lens(ob, float(scene.camera_details[selected_camera_id].s_width), float(scene.camera_details[selected_camera_id].s_height), lens)
        set_up_scene(int(scene.camera_details[selected_camera_id].x),int(scene.camera_details[selected_camera_id].y),True)
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

#______________________________________________________________

class OBJECT_OT_CreateCameraImagePlane(bpy.types.Operator):
    """Associate an undistorted photo to this camera"""
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
            undistortedpath = bpy.context.scene.BL_undistorted_path
            image_cam = bpy.data.images.load(undistortedpath+cameraname)
            self.mat_from_image(image_cam,imageplane,True)

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
            return check_children_plane(scene.camera) and context.preferences.filepaths.image_editor


    def execute(self, context):

        scene = context.scene
        undistortedpath = scene.BL_undistorted_path
        cam_ob = scene.camera

        if not undistortedpath:

            raise Exception("Set the Undistort path before to activate this command")
        else:
            for obj in cam_ob.children:
                if obj.name.startswith("objplane_"):
                    obj.hide_viewport = True
            bpy.ops.view3d.view_camera()
            bpy.ops.object.select_all(action='DESELECT')
            scene.canvas_obj.select_set(True)
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
        row.prop(context.scene, 'BL_undistorted_path', toggle = True, text="")
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
                row = layout.row()

                row.operator("object.createcameraimageplane", icon="PLUS", text='Load undistorted photo')
                row.operator("object.toggle_obj_visibility", icon='HIDE_OFF', text="")

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

                self.layout.operator("paint.cam", icon="PLUS", text='Paint active from cam')

                self.layout.operator("applypaint.cam", icon="PLUS", text='Apply paint')
                self.layout.operator("savepaint.cam", icon="PLUS", text='Save modified texs')
                row = layout.row()
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
    OBJECT_OT_parse_cams,
    OBJECT_OT_applypaintcam,
    OBJECT_OT_BetterCameras,
    OBJECT_OT_NoBetterCameras,
    OBJECT_OT_paintcam,
    OBJECT_OT_CreateCameraImagePlane,
    set_camera_type,
    set_background_cam,
    VIEW3D_PT_PhotogrTool,
    Camera_menu,
    OGGETTO_OT_pick,
    TOGGLE_OBJ_VISIBILITY
    ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.camera_details = bpy.props.CollectionProperty(type=CameraDetails)
    bpy.types.Scene.selected_camera = bpy.props.StringProperty(name="Selected Camera", update=update_camera_details)

    # Aggiungi questa property alla registrazione
    bpy.types.Scene.camera_enum = bpy.props.EnumProperty(items=get_camera_enum_items, update=update_camera_details)
    bpy.types.Scene.canvas_obj = bpy.props.PointerProperty(name="Canvas", type=bpy.types.Object)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.camera_details
    del bpy.types.Scene.selected_camera
