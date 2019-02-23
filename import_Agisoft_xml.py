import bpy
from mathutils import Matrix
import os
import xml.etree.ElementTree as ET
from bpy_extras.io_utils import axis_conversion
from bpy_extras.io_utils import ImportHelper

def createcamera(name, transform_matrix, collection_name):
    scene = bpy.context.scene
    cam = bpy.data.cameras.new(name)
    cam_ob = bpy.data.objects.new(name, cam)
    cam_ob.matrix_local = transform_matrix
    
    scene.collection.children[collection_name].objects.link(cam_ob)

def setup_collection(collection_name):
    if bpy.data.collections.get(collection_name) is None:
        newcol = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(newcol)
    
def load_create_cameras(filepath):

    tree = ET.parse(filepath)
    (dirname, filename) = os.path.split(filepath)
    root = tree.getroot()
    collection_name = os.path.splitext(filename)[0]
    setup_collection(collection_name)
    for cam in root.iter('camera'):
        image_name = cam.get('label')
        cam_name = os.path.splitext(image_name)[0]
        sensor = cam.get('sensor_id')
        for transform in cam.findall('transform'):
            transform_coord = transform.text
            list_coord = transform_coord.split(' ')
            formatted_list_coord = [ (float(list_coord[0]), float(list_coord[1]), float(list_coord[2]), float(list_coord[3])), (float(list_coord[4]), float(list_coord[5]), float(list_coord[6]), float(list_coord[7])), (float(list_coord[8]), float(list_coord[9]), float(list_coord[10]), float(list_coord[11])), (float(list_coord[12]), float(list_coord[13]), float(list_coord[14]), float(list_coord[15])) ]
            matrix = Matrix(formatted_list_coord)
            conversion_matrix = axis_conversion(from_forward='Z', from_up='-Y', to_forward='-Z', to_up='Y').to_4x4()
            matrix = matrix @ conversion_matrix
        #print(image_name+' '+ cam_name)
        #print(matrix)
        createcamera(cam_name, matrix, collection_name)