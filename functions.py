import bpy
import os
import time
import bmesh
import platform
from random import randint, choice
import re
import xml.etree.ElementTree as ET

#per panorami
import math
from math import pi
from mathutils import Vector
import bpy.props as prop
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty,
                       IntProperty
                       )


class OBJECT_OT_savepaintcam(bpy.types.Operator):
    bl_idname = "savepaint.cam"
    bl_label = "Save paint"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        #bpy.ops.image.save_dirty()
        bpy.ops.image.save_all_modified()

        return {'FINISHED'}

class OBJECT_OT_createcyclesmat(bpy.types.Operator):
    """Create cycles materials for selected objects"""
    bl_idname = "bi2cycles.material"
    bl_label = "Create cycles materials for selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.context.scene.render.engine = 'CYCLES'
        bi2cycles()
        return {'FINISHED'}

##########################################################################################

def rename_ge(ob):
    if ob.name.startswith('OB_'):
        #print(ob.name)
        ob_name = ob.name[3:]
        #print(ob_name)
    else:
        ob_name = ob.name
        #print(ob_name)
        ob.name = "OB_"+ob.name
    
    ob.data.name = "ME_"+ob_name
    if ob.material_slots:
        mslot_index = 0
        tslot_index = 0
        for m_slot in ob.material_slots:
            if m_slot.material:
                mslot_index += 1
                if m_slot.material.users == 1:
                    m_slot.material.name = "M_"+str(mslot_index)+"_"+ob_name
                else:
                    m_slot.material.name = "M_"+str(mslot_index)+"_"+ob_name
                
                # if m_slot.material.texture_slots:
                #     if(len(m_slot.material.texture_slots) > 0):
                #         tslot_index += 1
                #         m_tex = m_slot.material.texture_slots[0]
                #         m_tex.texture.name = "T_"+str(tslot_index)+"_"+ob.name
                #         m_tex.texture.image.name = "img_"+str(mslot_index)+"_"+ob.name

def circumcenter(ax,ay,bx,by,cx,cy):
    # ax = float(input('What is x of point 1?'))
    # ay = float(input('What is y of point 1?'))
    # bx = float(input('What is x of point 2?'))
    # by = float(input('What is y of point 2?'))
    # cx = float(input('What is x of point 3?'))
    # cy = float(input('What is y of point 3?'))
    d = 2 * ((ax * (by - cy)) + (bx * (cy - ay)) + (cx * (ay - by)))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy)

def calculateDistance(x1,y1,x2,y2):
     dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
     return dist

def grad(rad):
    grad = rad*57.2957795
    return grad

def rad(grad):
    rad = (grad*1.570796327153556)/90.0
    return rad

def get_nodegroupname_from_obj(obj):
    if obj.material_slots[0].material.node_tree.nodes.find('cc_node') == -1 :
        nodegroupname = None
    else:
        nodegroupname = obj.material_slots[0].material.node_tree.nodes['cc_node'].node_tree.name
        #nodegroupname = obj.material_slots[0].material.node_tree.nodes['cc_node'].node_tree
    return nodegroupname

def get_cc_node_pano(obj, current_pano):
    nodes = obj.material_slots[0].material.node_tree.nodes
    cc_node = ""
    for node in nodes:
        if node.name.startswith('cc_'+current_pano):
            cc_node = node
    return cc_node

#if 'Material Output' in [node.name for node in bpy.data.materials['your_material_name'].node_tree.nodes]:
#    print('Yes!')

def get_cc_node_in_obj_mat(nodegroupname,type):
    if type == 'RGB':
        type_name = 'RGB Curves'
    if type == 'BC':
        type_name = 'Bright/Contrast'
    if type == 'HS':
        type_name = 'Hue Saturation Value'
    node = bpy.data.node_groups[nodegroupname].nodes[type_name]
    return node

def get_cc_node_in_mat(mat,type):
    if type == 'RGB':
        type_name = 'RGB Curves'
    if type == 'BC':
        type_name = 'Bright/Contrast'
    if type == 'HS':
        type_name = 'Hue Saturation Value'
    node = mat.nodes
    return node

def parse_cam_xml(name_cam):
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
        return s_width, s_height, x, y


def set_up_lens(obj,sens_width,sens_lenght,lens):
    #obj.select_set(True)
    obj.data.lens = lens
    obj.data.sensor_fit = 'HORIZONTAL'
    obj.data.sensor_width = sens_width
    obj.data.sensor_height = sens_lenght

def set_up_scene(x,y,ao):
    bpy.context.scene.render.resolution_x = x
    bpy.context.scene.render.resolution_y = y
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.world.light_settings.use_ambient_occlusion = ao
    bpy.context.scene.tool_settings.image_paint.screen_grab_size[0] = x
    bpy.context.scene.tool_settings.image_paint.screen_grab_size[1] = y

def assignmatslots(ob, matlist):
    #given an object and a list of material names
    #removes all material slots form the object
    #adds new ones for each material in matlist
    #adds the materials to the slots as well.

    scn = bpy.context.scene
    ob_active = bpy.context.active_object
    scn.objects.active = ob

    for s in ob.material_slots:
        bpy.ops.object.material_slot_remove()

    # re-add them and assign material
    i = 0
    for m in matlist:
        mat = bpy.data.materials[m]
        ob.data.materials.append(mat)
        bpy.context.object.active_material.use_transparency = True
        bpy.context.object.active_material.alpha = 0.5
        i += 1

    # restore active object:
    scn.objects.active = ob_active


def check_texture(img, mat):
    #finds a texture from an image
    #makes a texture if needed
    #adds it to the material if it isn't there already

    tex = bpy.data.textures.get(img.name)

    if tex is None:
        tex = bpy.data.textures.new(name=img.name, type='IMAGE')

    tex.image = img

    #see if the material already uses this tex
    #add it if needed
    found = False
    for m in mat.texture_slots:
        if m and m.texture == tex:
            found = True
            break
    if not found and mat:
        mtex = mat.texture_slots.add()
        mtex.texture = tex
        mtex.texture_coords = 'UV'
        mtex.use_map_color_diffuse = True

def tex_to_mat():
    # editmode check here!
    editmode = False
    ob = bpy.context.object
    if ob.mode == 'EDIT':
        editmode = True
        bpy.ops.object.mode_set()

    for ob in bpy.context.selected_editable_objects:

        faceindex = []
        unique_images = []

        # get the texface images and store indices
        if (ob.data.uv_layers):
            for f in ob.data.uv_layers.active.data:
                if f.image:
                    img = f.image
                    #build list of unique images
                    if img not in unique_images:
                        unique_images.append(img)
                    faceindex.append(unique_images.index(img))

                else:
                    img = None
                    faceindex.append(None)

        # check materials for images exist; create if needed
        matlist = []
        for i in unique_images:
            if i:
                try:
                    m = bpy.data.materials[i.name]
                except:
                    m = bpy.data.materials.new(name=i.name)
                    continue

                finally:
                    matlist.append(m.name)
                    # add textures if needed
                    check_texture(i, m)

        # set up the object material slots
        assignmatslots(ob, matlist)

        #set texface indices to material slot indices..
        me = ob.data
#class CAMERA_PH_presets(Menu):
#    bl_label = "cameras presets"
#    preset_subdir = "ph_camera"
#    preset_operator = "script.execute_preset"
#    COMPAT_ENGINES = {'BLENDER_RENDER', 'BLENDER_GAME'}
#    draw = Menu.draw_preset

        i = 0
        for f in faceindex:
            if f is not None:
                me.polygons[i].material_index = f
            i += 1
    if editmode:
        bpy.ops.object.mode_set(mode='EDIT')

#        self.layout.operator("cam.visibility", icon="RENDER_REGION", text='Cam visibility')


#Recursivly transverse layer_collection for a particular name
def recurLayerCollection(layerColl, collName):
    found = None
    if (layerColl.name == collName):
        return layerColl
    for layer in layerColl.children:
        found = recurLayerCollection(layer, collName)
        if found:
            return found

def check_children_plane(cam_ob):
    check = False
    for obj in cam_ob.children:
        if obj.name.startswith("objplane_"):
            check = True
            pass
        else:
            check = False
    return check

def correctcameraname(cameraname):
#        extensions = ['.jpg','.JPG']
#        for extension in extensions:
    if cameraname.endswith('.JPG'):
        return cameraname
        pass
    else:
        cameranamecor = cameraname + ".JPG"
#                print(cameranamecor)
        return cameranamecor

def decimate_mesh(context,obj,ratio,lod):
    selected_obs = context.selected_objects
    bpy.ops.object.select_all(action='DESELECT')
    D = bpy.data
    obj.select_set(True)
    #context.scene.objects.active = obj
    context.view_layer.objects.active = obj
    bpy.ops.object.editmode_toggle()
    print('Decimating the original mesh to obtain the '+lod+' mesh...')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type="VERT")
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.object.vertex_group_add()
    bpy.ops.object.vertex_group_assign()
    bpy.ops.object.editmode_toggle()
#    bpy.data.objects[lod1name].modifiers.new("Decimate", type='DECIMATE')
    D.objects[obj.name].modifiers.new("Decimate", type='DECIMATE')
    D.objects[obj.name].modifiers["Decimate"].ratio = ratio
    D.objects[obj.name].modifiers["Decimate"].vertex_group = "Group"
    D.objects[obj.name].modifiers["Decimate"].invert_vertex_group = True
    bpy.ops.object.modifier_apply(modifier="Decimate")
#    bpy.ops.object.modifier_apply(apply_as='DATA', modifier="Decimate")
#    print("applied modifier")

def setupclonepaint():
    bpy.ops.object.mode_set(mode = 'TEXTURE_PAINT')
    bpy.ops.paint.brush_select(image_tool='CLONE')
    bpy.context.scene.tool_settings.image_paint.mode = 'MATERIAL'
    bpy.context.scene.tool_settings.image_paint.use_clone_layer = True
#    bpy.context.scene.tool_settings.image_paint.seam_bleed = 16
    obj = bpy.context.active_object

    for matslot in obj.material_slots:
        mat = matslot.material
        original_image = node_retriever(mat, "original")
        clone_image = node_retriever(mat, "source_paint_node")
        for idx, img in enumerate(mat.texture_paint_images):
            if img.name == original_image.image.name:
                mat.paint_active_slot = idx
                print ("I have just set the " + img.name + " image, as a paint image, that corresponds to the index: "+ str(idx))
            if img.name == clone_image.image.name:
                mat.paint_clone_slot = idx
                print ("I have just set the " + img.name + " image, as a paint image, that corresponds to the index: "+ str(idx))

def is_windows():
    if platform.system == 'Windows':
        is_win =True
    else:
        is_win =False
    return is_win

def cycles2bi():
    for ob in bpy.context.selected_objects:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select = True
        bpy.context.scene.objects.active = ob
        for matslot in ob.material_slots:
            mat = matslot.material
            node_original = node_retriever(mat,"original")
#            print(node_original.image.name)
#            print(mat.texture_slots[0].texture.image.name)
            mat.texture_slots[0].texture.image = node_original.image

def select_a_mesh(layout):
    row = layout.row()
    row.label(text="Select a mesh to start")

def select_a_node(mat, type):
    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.name == type:
            node.select = True
            nodes.active = node
            is_node = True
            pass
        else:
            is_node = False
    return is_node

# potenzialmente una migliore scrittura del codice:
# nodes = material_slot.material.node_tree.nodes
# texture_node = nodes.get('Image Texture')
# if texture_node is None:

def create_double_UV(obj):
    mesh = obj.data
    mesh.uv_layers.active_index = 0
    multitex_uvmap = mesh.uv_layers.active
    multitex_uvmap_name = multitex_uvmap.name
    multitex_uvmap.name = 'MultiTex'
    atlas_uvmap = mesh.uv_layers.new()
    atlas_uvmap.name = 'Atlas'
    mesh.uv_layers.active_index = 1
    bpy.ops.object.editmode_toggle()
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles()
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(margin=0.001)
    bpy.ops.object.editmode_toggle()
    mesh.uv_layers.active_index = 0
    return

def bake_tex_set(type):
    context = bpy.context
    scene = context.scene
    selected_objs = context.selected_objects
    scene.render.engine = 'CYCLES'
    tot_time = 0
    ob_counter = 1
    scene.cycles.samples = 1
    scene.cycles.max_bounces = 1
    scene.cycles.bake_type = 'DIFFUSE'
    scene.render.bake.use_pass_color = True
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.use_cage = True
    scene.render.bake.cage_extrusion = 0.1
    scene.render.bake.use_clear = True
    start_time = time.time()
    if type == "source":
        if len(selected_objs) > 1:
            ob = context.active_object
            print('checking presence of a destination texture set..')
            for matslot in ob.material_slots:
                mat = matslot.material
                select_a_node(mat,"source_paint_node")
            print('start baking..')
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=True, use_clear=True, save_mode='INTERNAL')
        else:
            raise Exception("Select two meshes in order to transfer a clone layer")
            return
        tot_time += (time.time() - start_time)
    if type == "cc":
        tot_selected_ob = len(selected_objs)
        for ob in selected_objs:
            print('start baking "'+ob.name+'" (object '+str(ob_counter)+'/'+str(tot_selected_ob)+')')
            bpy.ops.object.select_all(action='DESELECT')
            ob.select_set(True)
            context.view_layer.objects.active = ob
            for matslot in ob.material_slots:
                mat = matslot.material
                select_a_node(mat,"cc_image")
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=False, use_clear=True, save_mode='INTERNAL')
            tot_time += (time.time() - start_time)
            print("--- %s seconds ---" % (time.time() - start_time))
            ob_counter += 1
    for ob in selected_objs:
        ob.select_set(True)
    print("--- JOB complete in %s seconds ---" % tot_time)


def remove_cc_setup(mat):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    diffusenode = node_retriever(mat, "diffuse")
    ccnode = node_retriever(mat, "cc_node")
    newimagenode = node_retriever(mat, "cc_image")
    orimagenode = node_retriever(mat, "original")

    nodes.remove(newimagenode)
    nodes.remove(ccnode)

    links.new(orimagenode.outputs[0], diffusenode.inputs[0])

def set_texset(mat, type):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    imagenode = node_retriever(mat, type)
    diffusenode = node_retriever(mat, "diffuse")
    links.new(imagenode.outputs[0], diffusenode.inputs[0])

def substring_after(s, delim):
    return s.partition(delim)[2]

def create_new_tex_set(mat, type):
    #retrieve image specs and position from material
    o_image_node = node_retriever(mat, "original")
    o_image = o_image_node.image
    x_image = o_image.size[0]
    y_image = o_image.size[1]
    o_imagepath = o_image.filepath
    o_imagepath_abs = bpy.path.abspath(o_imagepath)
    o_imagedir, o_filename = os.path.split(o_imagepath_abs)
    o_filename_no_ext = os.path.splitext(o_filename)[0]
    node_tree = mat.node_tree
    nodes = node_tree.nodes
    if type == "cc_image":
        if o_filename_no_ext.startswith("cc_"):
            print(substring_after(o_filename, "cc_"))
            t_image_name = "cc_2_"+o_filename_no_ext
        else:
            t_image_name = "cc_"+o_filename_no_ext
            print(substring_after(o_filename, "cc_"))

    if type == "source_paint_node":
        t_image_name = "sp_"+o_filename_no_ext

    t_image = bpy.data.images.new(name=t_image_name, width=x_image, height=y_image, alpha=False)

    # set path to new image
    fn = os.path.join(o_imagedir, t_image_name)
    t_image.filepath_raw = fn+".png"
    t_image.file_format = 'PNG'

    tteximg = nodes.new('ShaderNodeTexImage')
    tteximg.location = (-1100, -450)
    tteximg.image = t_image
    tteximg.name = type

    for currnode in nodes:
        currnode.select = False

    # node_tree.nodes.select_all(action='DESELECT')
    tteximg.select = True
    node_tree.nodes.active = tteximg
 #   mat.texture_slots[0].texture.image = t_image

# provide to thsi function a material and a node type and it will send you back the name of the node. With the option "all" you will get a dictionary of the nodes
def node_retriever(mat, type):
    mat_nodes = mat.node_tree.nodes
    list_all_node_type = {}
    cc_node = "cc_node"
    cc_image = "cc_image"
    original = "original"
    source_paint_node = "source_paint_node"
    diffuse = "diffuse"
    list_all_node_type[cc_node] = None
    list_all_node_type[cc_image] = None
    list_all_node_type[original] = None
    list_all_node_type[source_paint_node] = None
    list_all_node_type[diffuse] = None
    node = None

    if type == "all":
        for node_type in list_all_node_type:
            for node in mat_nodes:
                if node.name == node_type:
                    list_all_node_type[node_type] = node
        #print(list_all_node_type)
        return dict2list(list_all_node_type)
    else:
        for node in mat_nodes:
            if node.name == type:
                #print('Il nodo tipo trovato è :'+ node.name)
                list_all_node_type[type] = node
                return node
                pass
        print("non ho trovato nulla")
        node = False
        return node

# for cycles material

def dict2list(dict):
    list=[]
    for i,j in dict.items():
        list.append(j)
#    print (list)
    return list

def create_correction_nodegroup(name):
    # create a group
#    active_object_name = bpy.context.scene.objects.active.name
    cc_nodegroup = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    #cc_nodegroup.name = "cc_node"
#    cc_nodegroup.label = label

    # create group inputs
    group_inputs = cc_nodegroup.nodes.new('NodeGroupInput')
    group_inputs.location = (-750,0)
    cc_nodegroup.inputs.new('NodeSocketColor','tex')

    # create group outputs
    group_outputs = cc_nodegroup.nodes.new('NodeGroupOutput')
    group_outputs.location = (300,0)
    cc_nodegroup.outputs.new('NodeSocketColor','cortex')

    # create three math nodes in a group
    bricon = cc_nodegroup.nodes.new('ShaderNodeBrightContrast')
    bricon.location = (-220, -100)
    bricon.label = 'bricon'

    sathue = cc_nodegroup.nodes.new('ShaderNodeHueSaturation')
    sathue.location = (0, -100)
    sathue.label = 'sathue'

    RGBcurve = cc_nodegroup.nodes.new('ShaderNodeRGBCurve')
    RGBcurve.location = (-500, -100)
    RGBcurve.label = 'RGBcurve'

    # link nodes together
    cc_nodegroup.links.new(sathue.inputs[4], bricon.outputs[0])
    cc_nodegroup.links.new(bricon.inputs[0], RGBcurve.outputs[0])

    # link inputs
    cc_nodegroup.links.new(group_inputs.outputs['tex'], RGBcurve.inputs[1])

    #link output
    cc_nodegroup.links.new(sathue.outputs[0], group_outputs.inputs['cortex'])

    return cc_nodegroup



############ QUESTA PARTE NON DOVREBBE PIU' SERVIRE NEL BLENDER 2.8 ############
def bi2cycles():
    for obj in bpy.context.selected_objects:
        active_object_name = bpy.context.active_object.name
        for matslot in obj.material_slots:
            mat = matslot.material
            image = mat.texture_slots[0].texture.image
            mat.use_nodes = True
            mat.node_tree.nodes.clear()
            links = mat.node_tree.links
            nodes = mat.node_tree.nodes
            output = nodes.new('ShaderNodeOutputMaterial')
            output.location = (0, 0)
            mainNode = nodes.new('ShaderNodeBsdfDiffuse')
            mainNode.location = (-400, -50)
            mainNode.name = "diffuse"
            teximg = nodes.new('ShaderNodeTexImage')
            teximg.location = (-1100, -50)
            teximg.image = image
            teximg.name = "original"
#            colcor = nodes.new(type="ShaderNodeGroup")
#            colcor.node_tree = (bpy.data.node_groups[active_object_name])
#            colcor.location = (-800, -50)
            links.new(teximg.outputs[0], mainNode.inputs[0])
#            links.new(colcor.outputs[0], )
            links.new(mainNode.outputs[0], output.inputs[0])
#            colcor.name = "colcornode"

####################################################################################

def cc_node_to_mat(mat, cc_nodegroup):#(ob,context):
    print("Voglio attaccare al materiale "+ mat.name + " il nodo gruppo: " + cc_nodegroup.name)
    #cc_image_node, cc_node, original_node, diffuse_node, source_paint_node = node_retriever(mat, "all")
    links = mat.node_tree.links
    nodes = mat.node_tree.nodes
    mainNode = node_retriever(mat, "Principled BSDF")
    mainNode.name = "diffuse"

    teximg = node_retriever(mat, "Image Texture")
    teximg.name = "original"

    print("Ho letto il materiale ed ho trovato una immagine di nome: " + teximg.image.name)
    colcor = nodes.new(type="ShaderNodeGroup")
 #   colcor.node_tree = cc_nodegroup
    print(cc_nodegroup)
    colcor.node_tree = cc_nodegroup
#    x_img = teximg.location[0]
#    x_dif = mainNode.location[0]
    x = (teximg.location[0]+mainNode.location[0])/2
    y = (teximg.location[1]+mainNode.location[1])/2
    colcor.location = (x, y)
    colcor.name = "cc_node"
    links.new(teximg.outputs[0], colcor.inputs[0])
    links.new(colcor.outputs[0], mainNode.inputs[0])

def remove_node(mat, node_to_remove):
    node = node_retriever(mat, node_to_remove)
    if node is not None:
#        links = mat.node_tree.links
#        previous_node = cc_node.inputs[0].links[0].from_node
#        following_node = cc_node.outputs[0].links[0].to_node
#        links.new(previous_node.outputs[0], following_node.inputs[0])
        mat.node_tree.nodes.remove(node)
#    else:
#        print("There is not a color correction node in this material")

# for quick utils____________________________________________
def make_group(ob,context):
    nomeoggetto = str(ob.name)
    if bpy.data.groups.get(nomeoggetto) is not None:
        currentgroup = bpy.data.groups.get(nomeoggetto)
        bpy.ops.group.objects_remove_all()
#        for object in currentgroup.objects:
#            bpy.ops.group.objects_remove(group=currentgroup)
    else:
        bpy.ops.group.create(name=nomeoggetto)
    ob.select = True
    bpy.ops.object.group_link(group=nomeoggetto)


def getnextobjname(name):
#    print("prendo in carico l'oggetto: "+name)
    #lst = ['this','is','just','a','test']
#    if fnmatch.filter(name, '.0*'):
    if name.endswith(".001") or name.endswith(".002") or name.endswith(".003") or name.endswith(".004") or name.endswith(".005"):
        current_nonumber = name[:-3]
#        print("ho ridotto il nome a :"+current_nonumber)
        current_n_integer = int(name[-3:])
#        print("aggiungo un numero")
        current_n_integer +=1
#        print(current_n_integer)
        if current_n_integer > 9:
            nextname = current_nonumber+'0'+str(current_n_integer)
        else:
            nextname = current_nonumber+'00'+str(current_n_integer)
    else:
        nextname = name+'.001'
#    print(nextname)
    return nextname


def newimage2selpoly(ob, nametex):
#    objectname = ob.name
    print("I'm creating texture: T_"+nametex+".png")
    me = ob.data
    tempimage = bpy.data.images.new(name=nametex, width=4096, height=4096, alpha=False)
    tempimage.filepath_raw = "//T_"+nametex+".png"
    tempimage.file_format = 'PNG'
    for uv_face in me.uv_layers.active.data:
        uv_face.image = tempimage
    return

def clean_name(name):
    if name.endswith(".001") or name.endswith(".002") or name.endswith(".003") or name.endswith(".004") or name.endswith(".005")or name.endswith(".006")or name.endswith(".007")or name.endswith(".008")or name.endswith(".009"):
        cname = name[:-4]
    else:
        cname = name
    return cname

def areamesh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    area = sum(f.calc_area() for f in bm.faces)
#    print(area)
    bm.free()
    return area

def desiredmatnumber(ob):
    area = areamesh(ob)
    if area > 21:
        if area <103:
            desmatnumber = 6
            if area < 86:
                desmatnumber = 5
                if area < 68:
                    desmatnumber = 4
                    if area < 52:
                        desmatnumber = 3
                        if area < 37:
                            desmatnumber = 2
        else:
            desmatnumber = 6
            print("Be carefull ! the mesh is "+str(area)+" square meters is too big, consider to reduce it under 100. I will use six 4096 texture to describe it.")
    else:
        desmatnumber = 1
    return desmatnumber


def set_texset_obj(context):
    view_mode = context.window_manager.ccToolViewVar.cc_view
    for obj in context.selected_objects:
        for matslot in obj.material_slots:
            mat = matslot.material
            set_texset(mat, view_mode)

def create_material_from_image(context,image,oggetto,connect):

    mat = bpy.data.materials.new(name='M_'+ oggetto.name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Roughness'].default_value = 1.0
    bsdf.inputs['Specular'].default_value = 0.0
    texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
    texImage.image = image
#    imagepath = image.filepath_raw
#    texImage.image = bpy.data.images.load(imagepath)
    if connect == True:
        mat.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

    # Assign it to object
    if oggetto.data.materials:
        oggetto.data.materials[0] = mat
    else:
        oggetto.data.materials.append(mat)

    mat.node_tree.nodes.active = texImage

    return mat, texImage, bsdf


def mat_from_image(img,ob,alpha):
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
    #output_node = mat.node_tree.nodes()

    if alpha == True:
        alpha_node = mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
        alpha_node.location = (-80,-518)
        mixshader_node = mat.node_tree.nodes.new('ShaderNodeMixShader') 
        mixshader_node.location = (-75,-370)
        mat.node_tree.links.new(bsdf.outputs[0], mixshader_node.inputs[1])
        mat.node_tree.links.new(alpha_node.outputs[0], mixshader_node.inputs[2])
        mat.node_tree.links.new(mixshader_node.outputs['Shader'], material_output.inputs[0])
        mat.blend_method = 'BLEND'

    # Assign it to object
    if ob.data.materials:
        ob.data.materials[0] = mat
    else:
        ob.data.materials.append(mat)

    #mat.node_tree.nodes.active = texImage
    return mat, texImage

#sezione panorami

# AGGIUNTA DI MODULO PER GIRARE LE UV

def GetObjectAndUVMap( objName, uvMapName ):
    try:
        obj = bpy.data.objects[objName]

        if obj.type == 'MESH':
            uvMap = obj.data.uv_layers[uvMapName]
            return obj, uvMap
    except:
        pass

    return None, None

#Scale a 2D vector v, considering a scale s and a pivot point p
def Scale2D( v, s, p ):
    return ( p[0] + s[0]*(v[0] - p[0]), p[1] + s[1]*(v[1] - p[1]) )

#Scale a UV map iterating over its coordinates to a given scale and with a pivot point
def ScaleUV( uvMap, scale, pivot ):
    for uvIndex in range( len(uvMap.data) ):
        uvMap.data[uvIndex].uv = Scale2D( uvMap.data[uvIndex].uv, scale, pivot )


#### fine modulo girare UV

def set_rotation_to_bubble(context,object,pano):
#    bpy.ops.object.select_all(action='DESELECT')
#    object.select = True
#    context.scene.objects.active = object
    bpy.ops.object.constraint_add(type='COPY_ROTATION')
    context.object.constraints["Copy Rotation"].target = pano
    bpy.ops.object.visual_transform_apply()
    bpy.ops.object.constraints_clear()

    bpy.ops.object.constraint_add(type='LIMIT_DISTANCE')
    bpy.context.object.constraints["Limit Distance"].target = pano
    bpy.context.object.constraints["Limit Distance"].distance = 1.6
    bpy.context.object.constraints["Limit Distance"].limit_mode = 'LIMITDIST_ONSURFACE'
    bpy.ops.object.visual_transform_apply()
    bpy.ops.object.constraints_clear()

def lod_list_clear(context):
    scene = context.scene
    scene.lod_list_item.update()
    list_lenght = len(scene.lod_list_item)
    for x in range(list_lenght):
        scene.lod_list_item.remove(0)
    return

def PANO_list_clear(context):
    scene = context.scene
    scene.pano_list.update()
    list_lenght = len(scene.pano_list)
    for x in range(list_lenght):
        scene.pano_list.remove(0)
    return

def e2d(float_value):
    fac = 180/pi
    return (float_value/fac)

def create_tex_from_file(ItemName,path_dir):
    realpath = os.path.join(path_dir,ItemName)
    #realpath = path_dir + ItemName #+ '.' + extension
    try:
        img = bpy.data.images.load(realpath)
    except:
        raise NameError("Cannot load image %s" % realpath)
    # Create image texture from image
    diffTex = bpy.data.textures.new('TEX_'+ItemName, type = 'IMAGE')
    diffTex.image = img
    return diffTex, img

def create_pano_ubermat(regenerate_maps):
    context = bpy.context
    scene = context.scene
    obj_mat = context.view_layer.objects.active
    obj_mat_mat_name = obj_mat.name+"uberpano"
    if obj_mat.name in scene.pano_list:
        raise NameError("The active object %s is a panorama, skip the process, please select an object you want to create a panoramic material for" % obj_mat.name)
        return
    else:
        mat = bpy.data.materials.get(obj_mat_mat_name)

        if mat is None:
            mat = bpy.data.materials.new(name=obj_mat_mat_name)
            mat.use_nodes = True
            print(mat.name)
        else:
            mat = bpy.data.materials[obj_mat_mat_name]
            print("The material %s still exists" % mat.name)
        # Assign it to object
        if obj_mat.data.materials:
            # assign to 1st material slot
            obj_mat.data.materials[0] = mat
        else:
            # no slots
            obj_mat.data.materials.append(mat)
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        for n in nodes:
            #if regenerate_maps is True:
            #    if not n.name.startswith('mk_'):
            #        nodes.remove(n)
            #else:
            nodes.remove(n)
        vector_node_pano = nodes.new('ShaderNodeTexCoord')
        vector_node_pano.name = "vectornode"
        vector_node_pano.location = (-450,0)
        UV_node_pano = nodes.new('ShaderNodeUVMap')
        UV_node_pano.name = "UVnode"
        UV_node_pano.location = (-450,-250)
        UV_node_pano.uv_map = obj_mat.data.uv_layers.active.name

        current_y_location = 0
        iteration_num = 1
        for pano in scene.pano_list:
            current_pano_name = pano.name

            current_x_location = 0
            mapping_node_pano = nodes.new('ShaderNodeMapping')
            mapping_node_pano.name = "mn_"+current_pano_name
            mapping_node_pano.location = (current_x_location,current_y_location)
            mapping_node_pano.vector_type = 'TEXTURE'
            current_pano_ob = select_obj_from_panoitem(current_pano_name)

            bpy.ops.object.select_all(action='DESELECT')
            current_pano_ob.select_set(True)
            context.view_layer.objects.active = current_pano_ob

            bpy.ops.transform.rotate(value=rad(90.0), orient_axis='Z', orient_type='LOCAL')

            i = 0
            while i < 3:
                mapping_node_pano.translation[i] = current_pano_ob.location[i]
                mapping_node_pano.rotation[i] = current_pano_ob.rotation_euler[i]
                print(str(current_pano_ob.name))
                i += 1

            bpy.ops.transform.rotate(value=-(rad(90.0)), orient_axis='Z', orient_type='LOCAL')

            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = obj_mat
            obj_mat.select_set(True)

            links.new(vector_node_pano.outputs[3], mapping_node_pano.inputs[0])

            current_x_location += 500
            pano_tex_node = nodes.new('ShaderNodeTexEnvironment')
            pano_tex_node.location = (current_x_location, current_y_location)
            pano_tex_node.name = "tn_"+current_pano_name
            links.new(mapping_node_pano.outputs[0], pano_tex_node.inputs[0])

            current_file_pano_name = current_pano_name+"-"+str(scene.RES_pano)+"k.jpg"

            found = False
            for im in bpy.data.images:
                if im.name == current_file_pano_name:
                    found = True
                    print("got a previous image")
                else:
                    pass

            if found is False:
                current_dir_pano_name = str(scene.RES_pano)+"k"
                path = os.path.join(scene.PANO_dir,current_dir_pano_name,current_file_pano_name)
                pano_tex_node.image = image_from_path(path)
            else:
                pano_tex_node.image = bpy.data.images[current_file_pano_name]

            current_x_location +=400
            if regenerate_maps is True:
                pano_mask_node = nodes.new('ShaderNodeTexImage')
                pano_mask_node.name = "mk_"+current_pano_name
            else:
                pano_mask_node = nodes.nodes.get("mk_"+current_pano_name)
            pano_mask_node.location = (current_x_location, current_y_location)

            current_dir_blend = os.path.dirname(bpy.data.filepath)
            if not current_dir_blend:
                raise Exception("Blend file is not saved")
            current_pano_subfolder_4maps = ("mp_"+obj_mat.name)
            new_map_img_filename = ("mp_"+obj_mat.name+"_"+current_pano_name+".png")
            new_map_dir_path = create_folder_in_path(current_pano_subfolder_4maps,current_dir_blend)
            new_map_img_path = os.path.join(new_map_dir_path,new_map_img_filename)

            tempimage = bpy.data.images.new(name=new_map_img_filename, width=2048, height=2048, alpha=True)
            tempimage.alpha_mode = 'CHANNEL_PACKED'
            tempimage.filepath_raw = new_map_img_path
            tempimage.file_format = 'PNG'
            tempimage.save()

            pano_mask_node.image = tempimage
            links.new(UV_node_pano.outputs[0], pano_mask_node.inputs[0])

            current_x_location +=400
            pano_rgb_node = nodes.new('ShaderNodeRGBCurve')
            pano_rgb_node.location = (current_x_location, current_y_location)
            pano_rgb_node.name = "cc_"+current_pano_name
            links.new(pano_mask_node.outputs[1], pano_rgb_node.inputs[0])
            links.new(pano_tex_node.outputs[0], pano_rgb_node.inputs[1])

            current_x_location +=400
            pano_mix_node = nodes.new('ShaderNodeMixRGB')
            pano_mix_node.location = (current_x_location, current_y_location)
            pano_mix_node.name = "mx_"+current_pano_name
            links.new(pano_rgb_node.outputs[0], pano_mix_node.inputs[2])
            links.new(pano_mask_node.outputs[0], pano_mix_node.inputs[0])
            if iteration_num == 1:
                links.new(pano_rgb_node.outputs[0], pano_mix_node.inputs[1])
            else:
                links.new(last_pano_mix_node.outputs[0], pano_mix_node.inputs[1])

            last_pano_mix_node = pano_mix_node
            iteration_num +=1
            current_y_location -= 350

        current_x_location +=400
        current_y_location = 0
        pano_emission_node = nodes.new('ShaderNodeEmission')
        pano_emission_node.location = (current_x_location, current_y_location)
        pano_emission_node.name = "emission_node"
        links.new(last_pano_mix_node.outputs[0], pano_emission_node.inputs[0])
        current_x_location +=400
        pano_output_node = nodes.new('ShaderNodeOutputMaterial')
        pano_output_node.location = (current_x_location, current_y_location)
        links.new(pano_emission_node.outputs[0], pano_output_node.inputs[0])

def create_folder_in_path(foldername,path):
    folderpath = os.path.join(path, foldername)
    if not os.path.exists(folderpath):
        os.mkdir(folderpath)
        print("There is no "+ foldername +" folder. Creating one...")
    else:
        print('Found previously created '+ foldername +' folder. I will use it')
    return folderpath

def image_from_path(path):
    #path = "path_to_the_image"
    try:
        img = bpy.data.images.load(path)
    except:
        raise NameError("Cannot load image %s" % path)
    return img

def select_obj_from_panoitem(panoname):
    for ob in bpy.data.objects:
        if panoname == ob.name:
            found_ob = ob
    return found_ob

def setup_mat_panorama_3DSC(matname, img):
    scene = bpy.context.scene
    mat = bpy.data.materials[matname]

    mat.use_backface_culling = True
    mat.use_nodes = True
    mat.node_tree.nodes.clear()

    mat.blend_method = "BLEND"
    links = mat.node_tree.links
    nodes = mat.node_tree.nodes
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (0, 0)
    mainNode = nodes.new('ShaderNodeEmission')
    mainNode.location = (-600, 50)
    mainNode.name = "diffuse"

    teximgNode = nodes.new('ShaderNodeTexImage')
    teximgNode.image = img
    teximgNode.location = (-1200, 50)

    mixNode = nodes.new('ShaderNodeMixShader')
    mixNode.inputs[0].default_value = 0.5
    mixNode.location = (-300, 0)

    alphaNode = nodes.new('ShaderNodeBsdfTransparent')
    #alphaNode.inputs[0].default_value = 0.5
    alphaNode.location = (-600, -100)

    links.new(mixNode.outputs[0], output.inputs[0])
    links.new(mainNode.outputs[0], mixNode.inputs[1])
    links.new(teximgNode.outputs[0], mainNode.inputs[0])
    links.new(alphaNode.outputs[0], mixNode.inputs[2])    

def create_mat(ob):
    context = bpy.context
    scene = context.scene
    ob = context.active_object
    mat = bpy.data.materials.new(name="MAT_"+ob.name) #set new material to variable
    ob.data.materials.append(mat)
    #mat.use_transparency = True
    #mat.alpha = 0.75 #add the material to the object
    return mat

def readfile(filename):
    f=open(filename,'r') # open file for reading
    arr=f.readlines()[2:]  # store the entire file in a variable
    f.close()
    return arr

def remove_extension(string):
    return string.replace(".jpg", "")

def flipnormals():
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_all(action='SELECT')
    # Operation in edit mode
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)


def create_cam(name,pos_x,pos_y,pos_z):
  # create camera data
    context = bpy.context
    cam_data = bpy.data.cameras.new('CAM_'+name)
    cam_data.display_size = 0.15
    cam_data.lens = bpy.context.scene.PANO_cam_lens
    # create object camera data and insert the camera data
    cam_ob = bpy.data.objects.new('CAM_'+name, cam_data)
    # link into scene
    coll = context.view_layer.active_layer_collection.collection
    coll.objects.link(cam_ob)
    #bpy.context.scene.objects.link(cam_ob)
    cam_ob.location.x = pos_x
    cam_ob.location.y = pos_y
    cam_ob.location.z = pos_z
    cam_ob.rotation_euler.x = e2d(90)

def read_pano_dir(context):
    scene = context.scene
    sPath = scene.PANO_dir
    scene.resolution_list.clear()
    minimum_sChildPath = ""
    folder_list = []
    folder_presence = False
    min_len = 100
    idx = 0
    for sChild in os.listdir(sPath):
            sChildPath = os.path.join(sPath,sChild)
            if os.path.isdir(sChildPath):
                folder_presence = True
                folder_list.append(sChild)
                currentnumber = getnumber_in_name(str(sChild))
                scene.resolution_list.add()
                scene.resolution_list[idx].res_num = currentnumber
                idx += 1

                if currentnumber < min_len:
                    #print(str(currentnumber))
                    min_len = currentnumber


    if folder_presence is False:
        pass
    #print(str(minimum_sChildPath))
    scene.RES_pano = min_len
    #scene["RES_pano_folder_list"] = sorted(scene.resolution_list, key = getnumber_in_name)
    scene["RES_pano_folder_list"] = sorted(folder_list, key = getnumber_in_name)
    print(scene["RES_pano_folder_list"])
    return

def getnumber_in_name(string):
    temp = re.findall(r'\d+', str(string))
    numbers = list(map(int, temp))
    #print(numbers)
    lastnumber = int(numbers[len(numbers)-1])
    return lastnumber


def bmesh_calc_area(bm):
    """Calculate the surface area."""
    return sum(f.calc_area() for f in bm.faces)


def bmesh_copy_from_object(obj, transform=True, triangulate=True, apply_modifiers=False):
    """Returns a transformed, triangulated copy of the mesh"""

    assert obj.type == 'MESH'

    if apply_modifiers and obj.modifiers:
        import bpy
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        me = obj_eval.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(me)
        obj_eval.to_mesh_clear()
    else:
        me = obj.data
        if obj.mode == 'EDIT':
            bm_orig = bmesh.from_edit_mesh(me)
            bm = bm_orig.copy()
        else:
            bm = bmesh.new()
            bm.from_mesh(me)

    # TODO. remove all customdata layers.
    # would save ram

    if transform:
        bm.transform(obj.matrix_world)

    if triangulate:
        bmesh.ops.triangulate(bm, faces=bm.faces)

    return bm


def clean_float(text):
    # strip trailing zeros: 0.000 -> 0.0
    index = text.rfind(".")
    if index != -1:
        index += 2
        head, tail = text[:index], text[index:]
        tail = tail.rstrip("0")
        text = head + tail
    return text

def clean_suffix(ob,suffix):
    if ob.name.endswith(suffix):
        ob.name = ob.name[:-4]
    return

def roundup(x):
    return int(math.ceil(x / 1.0))  # * 1

def create_cutter_series(cutter_name, x_tile_side, y_tile_side):
    x_min = 10000000
    y_min = 10000000
    x_max = -10000000
    y_max = -10000000
    z_max = -10000000
    x_lenght = 0
    y_lenght = 0

    for ob in bpy.context.selected_objects:
        for ver in ob.bound_box:
            if x_min > ver[0]:
                x_min = ver[0]
            if y_min > ver[1]:
                y_min = ver[1]
            if x_max < ver[0]:
                x_max = ver[0]
            if y_max < ver[1]:
                y_max = ver[1]
            if z_max < ver[2]:
                z_max = ver[2]

    x_lenght = x_max-x_min
    y_lenght = y_max-y_min

    x_tile_num = roundup(x_lenght/x_tile_side)
    y_tile_num = roundup(y_lenght/y_tile_side)

    bpy.context.scene.cursor.location = (x_min, y_min, z_max)

    bpy.ops.mesh.primitive_plane_add(size=1, enter_editmode=True, align='WORLD', location=(
        x_min, y_min, z_max+1), scale=(10, 10, 1))
    bpy.ops.transform.translate(value=(0.49, 0.49, 0), orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(
        True, False, False), mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False)
    bpy.ops.object.editmode_toggle()
    cutter = bpy.context.active_object
    cutter.name = cutter_name
    cutter.scale = (x_tile_side, y_tile_side, 1)
    bpy.ops.object.modifier_add(type='ARRAY')
    cutter.modifiers[0].count = x_tile_num
    bpy.ops.object.modifier_add(type='ARRAY')
    cutter.modifiers[1].relative_offset_displace[0] = 0.0
    cutter.modifiers[1].count = y_tile_num
    cutter.modifiers[1].relative_offset_displace[1] = 1.0
    cutter.display_type = 'WIRE'
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    cutter.modifiers[0].name
    bpy.ops.object.modifier_apply(modifier=cutter.modifiers[0].name)
    bpy.ops.object.modifier_apply(modifier=cutter.modifiers[0].name)
    bpy.ops.mesh.separate(type='LOOSE')
    return

def diffuse2principled():
    for obj in bpy.context.selected_objects:
        for matslot in obj.material_slots:
            material = matslot.material
            #  store the reference to the node_tree in a variable
            nodetree = material.node_tree
            
            #  loop through nodes in the nodetree
            for node in nodetree.nodes:
                #  if the node is a Diffuse node....
                if node.type=="BSDF_DIFFUSE":
                    
                    #  store the nodes that are connected to it
                    inputnode = node.inputs['Color'].links[0].from_node
                    outputnode = node.outputs['BSDF'].links[0].to_node
                    
                    origCoordinates = node.location
                    #  remove the diffuse node
                    nodetree.nodes.remove(node)
                    
                    
                    newnode = nodetree.nodes.new('ShaderNodeBsdfPrincipled')
                    newnode.location = origCoordinates
                    newnode.name = "diffuse"
                    newnode.inputs['Roughness'].default_value = 1.0
                    newnode.inputs['Specular'].default_value = 0.0
                    
                    #  relink everything
                    nodetree.links.new(inputnode.outputs[0], newnode.inputs[0])
                    #nodetree.links.new(inputnode.outputs[0], newnode.inputs[1])
                    nodetree.links.new(newnode.outputs[0], outputnode.inputs[0])
    return

#def 