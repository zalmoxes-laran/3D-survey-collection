import bpy
from mathutils import Matrix
import os
import xml.etree.ElementTree as ET

def createcamera(name, transform_matrix):
    scene = bpy.context.scene
    cam = bpy.data.cameras.new(name)
    cam_ob = bpy.data.objects.new(name, cam)
    cam_ob.matrix_world = transform_matrix
    collection_name = os.path.splitext(filename)[0]
    setup_collection(collection_name)
    scene.collection.children[collection_name].objects.link(cam_ob)

def setup_collection(collection_name):
    if bpy.data.collections.get(collection_name) is None:
        newcol = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(newcol)


def load_create_cameras(filename):
    filepath = bpy.data.filepath
    directory = os.path.dirname(filepath)
    #print(directory)
    file = directory +'/'+filename
    tree = ET.parse(file)
    root = tree.getroot()

    for cam in root.iter('camera'):
        image_name = cam.get('label')
        cam_name = os.path.splitext(image_name)[0]
        sensor = cam.get('sensor_id')
        for transform in cam.findall('transform'):
            transform_coord = transform.text
            list_coord = transform_coord.split(' ')
            formatted_list_coord = [ (float(list_coord[0]), float(list_coord[1]), float(list_coord[2]), float(list_coord[3])), (float(list_coord[4]), float(list_coord[5]), float(list_coord[6]), float(list_coord[7])), (float(list_coord[8]), float(list_coord[9]), float(list_coord[10]), float(list_coord[11])), (float(list_coord[12]), float(list_coord[13]), float(list_coord[14]), float(list_coord[15])) ]
            #print(formatted_list_coord)
            matrix = Matrix(formatted_list_coord)

        print(image_name+' '+ cam_name)
        print(matrix)
        createcamera(cam_name, matrix)

filename = 'camera-Agisoft.xml'

load_create_cameras(filename)
