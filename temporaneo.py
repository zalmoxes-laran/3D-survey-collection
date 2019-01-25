def create_material_from_image(context,image,oggetto):

    mat = bpy.data.materials.new(name='M_'+ oggetto.name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
    imagepath = image.filepath_raw
    texImage.image = bpy.data.images.load(imagepath)
    mat.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

    # Assign it to object
    if oggetto.data.materials:
        oggetto.data.materials[0] = mat
    else:
        oggetto.data.materials.append(mat)
    return mat