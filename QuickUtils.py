import bpy
import os
import time
import bmesh
from random import randint, choice
from bpy.props import StringProperty, EnumProperty
from .functions import *
from .qualitycheck import *



class OBJECT_OT_invertcoordinates(bpy.types.Operator):
    """Invert x and y coordinates of selected objects"""
    bl_idname = "invert.coordinates"
    bl_label = "Invert x and y coordinates of selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        oggetti_selezionati = bpy.context.selected_objects

        # Ciclo attraverso ciascun oggetto selezionato
        for oggetto in oggetti_selezionati:
            # Accedi alla posizione dell'oggetto
            posizione = oggetto.location

            # Inverti le coordinate X e Y
            posizione.x, posizione.y = posizione.y, posizione.x

            # Aggiorna la posizione dell'oggetto
            oggetto.location = posizione
        return {'FINISHED'}

class OBJECT_OT_diffuseprincipled(bpy.types.Operator):
    """Replace old diffuse shader with a principled shader"""
    bl_idname = "diffuse.principled"
    bl_label = "Replace old diffuse shader with a principled shader"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        turn_on_button = False
        if context.active_object is not None:
            if context.active_object.type == 'MESH':
                turn_on_button = True
        return turn_on_button

    def execute(self, context):
        diffuse2principled()
        return {'FINISHED'}

class OBJECT_OT_setmetalness(bpy.types.Operator):
    """Batch set roughness to principled shaders in selected objects"""
    bl_idname = "set.metalness"
    bl_label = "Batch set metalness to principled shaders in selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        turn_on_button = False
        if context.active_object is not None:
            if context.active_object.type == 'MESH':
                turn_on_button = True
        return turn_on_button

    def execute(self, context):
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                material = matslot.material
                #  store the reference to the node_tree in a variable
                nodetree = material.node_tree
                
                #  loop through nodes in the nodetree
                for node in nodetree.nodes:
                    #  if the node is a Diffuse node....
                    if node.type=="BSDF_PRINCIPLED":
                        node.inputs['Metallic'].default_value = 0.0
        return {'FINISHED'}

class OBJECT_OT_setroughness(bpy.types.Operator):
    """Batch set roughness to principled shaders in selected objects"""
    bl_idname = "set.roughness"
    bl_label = "Batch set roughness to principled shaders in selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        turn_on_button = False
        if context.active_object is not None:
            if context.active_object.type == 'MESH':
                turn_on_button = True
        return turn_on_button

    def execute(self, context):
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                material = matslot.material
                #  store the reference to the node_tree in a variable
                nodetree = material.node_tree
                
                #  loop through nodes in the nodetree
                for node in nodetree.nodes:
                    #  if the node is a Diffuse node....
                    if node.type=="BSDF_PRINCIPLED":
                        node.inputs['Roughness'].default_value = 1.0
                                   
        return {'FINISHED'}




class OBJECT_OT_CorrectMaterial(bpy.types.Operator):
    bl_idname = "correct.material"
    bl_label = "Correct photogr. mats"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selection = context.selected_objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selection:
            obj.select_set(True)
            for i in range(0,len(obj.material_slots)):
                obj.active_material_index = i
                ma = obj.active_material
                ma.diffuse_intensity = 1
                ma.specular_intensity = 0
                ma.specular_color[0] = 1
                ma.specular_color[1] = 1         
                ma.specular_color[2] = 1  
                ma.diffuse_color[0] = 1
                ma.diffuse_color[1] = 1
                ma.diffuse_color[2] = 1
                ma.alpha = 1.0
                ma.use_transparency = False
                ma.transparency_method = 'Z_TRANSPARENCY'
                ma.use_transparent_shadows = True
                ma.ambient = 0.0
                image = ma.texture_slots[0].texture.image
                image.use_alpha = False
        return {'FINISHED'}



class OBJECT_OT_renameGEobject(bpy.types.Operator):
    """Rename data tree of selected objects using the object name"""
    bl_idname = "rename.ge"
    bl_label = "Rename data tree of selected objects using the object name (usefull for GE export)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context = bpy.context
        for ob in context.selected_objects:
            rename_ge(ob)
        return {'FINISHED'}
    
class OBJECT_OT_objectnamefromfilename(bpy.types.Operator):
    """Set active object name from file name"""
    bl_idname = "obname.ffn"
    bl_label = "Set active object name from file name"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objname = bpy.path.basename(bpy.context.blend_data.filepath)
        sel = bpy.context.active_object
        sel.name = objname.split(".")[0]
        return {'FINISHED'}


class OBJECT_OT_qualitycheck(bpy.types.Operator):
    """Quality check"""
    bl_idname = "quality.check"
    bl_label = "Report on quality of 3d models (install the UVtools addon)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        get_texel_density(self, context)
        return {'FINISHED'}


class OBJECT_OT_tiff2pngrelink(bpy.types.Operator):
    """Convert texture files and relink them on selected objects' materials"""
    bl_idname = "tiff2png.relink"
    bl_label = "Convert and relink texture format"
    bl_options = {'REGISTER', 'UNDO'}

    source_format: EnumProperty(
        name="Source format",
        description="Image format to search in selected materials",
        items=(
            ('TIFF', "TIFF (.tif/.tiff)", "Find .tif and .tiff textures"),
            ('PNG', "PNG (.png)", "Find .png textures"),
            ('JPEG', "JPEG (.jpg/.jpeg)", "Find .jpg and .jpeg textures"),
            ('TARGA', "TARGA (.tga)", "Find .tga textures"),
            ('BMP', "BMP (.bmp)", "Find .bmp textures"),
            ('OPEN_EXR', "OpenEXR (.exr)", "Find .exr textures"),
        ),
        default='TIFF'
    )  # type: ignore

    target_format: EnumProperty(
        name="Target format",
        description="New image format to write and relink",
        items=(
            ('PNG', "PNG (.png)", "Convert to .png"),
            ('JPEG', "JPEG (.jpg)", "Convert to .jpg"),
            ('TIFF', "TIFF (.tif)", "Convert to .tif"),
            ('TARGA', "TARGA (.tga)", "Convert to .tga"),
            ('BMP', "BMP (.bmp)", "Convert to .bmp"),
            ('OPEN_EXR', "OpenEXR (.exr)", "Convert to .exr"),
        ),
        default='PNG'
    )  # type: ignore

    modernize_materials: bpy.props.BoolProperty(
        name="Modernize to Principled",
        description="Rebuild selected materials to a clean Principled setup after relink",
        default=True
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "source_format")
        layout.prop(self, "target_format")
        layout.prop(self, "modernize_materials")
        layout.label(text="Output folder: <blend_dir>/tex_<target_ext>", icon='FILE_FOLDER')

    @staticmethod
    def _format_exts(fmt):
        return {
            'TIFF': {'.tif', '.tiff'},
            'PNG': {'.png'},
            'JPEG': {'.jpg', '.jpeg'},
            'TARGA': {'.tga'},
            'BMP': {'.bmp'},
            'OPEN_EXR': {'.exr'},
        }.get(fmt, set())

    @staticmethod
    def _target_ext(fmt):
        return {
            'PNG': 'png',
            'JPEG': 'jpg',
            'TIFF': 'tif',
            'TARGA': 'tga',
            'BMP': 'bmp',
            'OPEN_EXR': 'exr',
        }.get(fmt, 'png')

    @staticmethod
    def _collect_image_nodes_from_selection(context):
        material_keys = set()
        tex_nodes = []
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes or not mat.node_tree:
                    continue
                mat_key = mat.as_pointer()
                if mat_key in material_keys:
                    continue
                material_keys.add(mat_key)
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        tex_nodes.append(node)
        return tex_nodes

    @staticmethod
    def _collect_materials_from_selection(context):
        material_keys = set()
        materials = []
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes or not mat.node_tree:
                    continue
                mat_key = mat.as_pointer()
                if mat_key in material_keys:
                    continue
                material_keys.add(mat_key)
                materials.append(mat)
        return materials

    @staticmethod
    def _find_best_image_node(mat):
        image_nodes = [node for node in mat.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image]
        if not image_nodes:
            return None

        def _score(node):
            score = 0
            color_socket = node.outputs.get("Color")
            alpha_socket = node.outputs.get("Alpha")
            if color_socket:
                score += len(color_socket.links) * 10
            if alpha_socket:
                score += len(alpha_socket.links) * 5
            if node.image and getattr(node.image, "has_data", False):
                score += 2
            return score

        return max(image_nodes, key=_score)

    @staticmethod
    def _get_or_create_output_node(nodes):
        outputs = [node for node in nodes if node.type == 'OUTPUT_MATERIAL']
        if outputs:
            for node in outputs:
                if getattr(node, "is_active_output", False):
                    return node
            return outputs[0]
        return nodes.new('ShaderNodeOutputMaterial')

    @staticmethod
    def _collect_upstream_nodes(start_node):
        keep = {start_node}
        stack = [start_node]
        while stack:
            node = stack.pop()
            for in_socket in node.inputs:
                for link in in_socket.links:
                    source_node = link.from_node
                    if source_node not in keep:
                        keep.add(source_node)
                        stack.append(source_node)
        return keep

    @staticmethod
    def _modernize_material_to_principled(mat):
        if mat is None or not mat.use_nodes or mat.node_tree is None:
            return (False, "nodes_disabled")

        node_tree = mat.node_tree
        nodes = node_tree.nodes
        links = node_tree.links
        image_node = OBJECT_OT_tiff2pngrelink._find_best_image_node(mat)
        if image_node is None:
            return (False, "no_image_node")

        output_node = OBJECT_OT_tiff2pngrelink._get_or_create_output_node(nodes)
        principled = nodes.new('ShaderNodeBsdfPrincipled')

        principled.location = (image_node.location.x + 350, image_node.location.y)
        if output_node.location.x < principled.location.x:
            output_node.location = (principled.location.x + 350, principled.location.y)

        for link in list(links):
            if link.to_node == output_node and link.to_socket == output_node.inputs.get("Surface"):
                links.remove(link)

        for link in list(links):
            if link.to_node == principled and link.to_socket in {principled.inputs.get("Base Color"), principled.inputs.get("Alpha")}:
                links.remove(link)

        color_socket = image_node.outputs.get("Color")
        if color_socket:
            links.new(color_socket, principled.inputs["Base Color"])

        alpha_socket = image_node.outputs.get("Alpha")
        use_alpha = False
        if alpha_socket:
            if len(alpha_socket.links) > 0:
                use_alpha = True
            if getattr(image_node.image, "channels", 0) >= 4:
                use_alpha = True
        if use_alpha and alpha_socket:
            links.new(alpha_socket, principled.inputs["Alpha"])
            if hasattr(mat, "blend_method") and mat.blend_method == 'OPAQUE':
                mat.blend_method = 'CLIP'
            if hasattr(mat, "shadow_method"):
                mat.shadow_method = 'CLIP'

        links.new(principled.outputs["BSDF"], output_node.inputs["Surface"])
        principled.inputs["Metallic"].default_value = 0.0

        keep_nodes = {principled, output_node}
        keep_nodes.update(OBJECT_OT_tiff2pngrelink._collect_upstream_nodes(image_node))
        keep_nodes.add(image_node)

        for node in list(nodes):
            if node not in keep_nodes:
                nodes.remove(node)

        return (True, "")

    @staticmethod
    def _resolve_image_source_path(image):
        if image.filepath:
            return bpy.path.abspath(image.filepath, library=image.library)
        if getattr(image, "filepath_raw", ""):
            return bpy.path.abspath(image.filepath_raw, library=image.library)
        return ""

    @staticmethod
    def _image_matches_source_format(image, source_format, source_exts):
        path_ext = ""
        src_path = OBJECT_OT_tiff2pngrelink._resolve_image_source_path(image)
        if src_path:
            path_ext = os.path.splitext(src_path)[1].lower()

        name_ext = os.path.splitext(image.name)[1].lower()
        file_format = getattr(image, "file_format", "").upper()

        if source_format == 'OPEN_EXR':
            format_match = file_format in {'OPEN_EXR', 'OPEN_EXR_MULTILAYER'}
        else:
            format_match = (file_format == source_format)

        return (path_ext in source_exts) or (name_ext in source_exts) or format_match

    @staticmethod
    def _save_image_as_format(src_image, dst_path, target_format, scene):
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)

        prev_format = scene.render.image_settings.file_format
        try:
            scene.render.image_settings.file_format = target_format
            src_image.save_render(dst_path, scene=scene)
            return
        except Exception:
            pass
        finally:
            scene.render.image_settings.file_format = prev_format

        temp_image = src_image.copy()
        try:
            if not temp_image.has_data:
                try:
                    temp_image.reload()
                except Exception:
                    pass
            temp_image.filepath_raw = dst_path
            temp_image.file_format = target_format
            temp_image.save()
        finally:
            bpy.data.images.remove(temp_image)

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first (needed to create tex_<format> folder)")
            return {'CANCELLED'}

        if self.source_format == self.target_format:
            self.report({'ERROR'}, "Source and target formats must be different")
            return {'CANCELLED'}

        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}

        source_exts = self._format_exts(self.source_format)
        target_ext = self._target_ext(self.target_format)
        blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
        output_dir = os.path.join(blend_dir, f"tex_{target_ext}")
        os.makedirs(output_dir, exist_ok=True)

        tex_nodes = self._collect_image_nodes_from_selection(context)
        if not tex_nodes:
            self.report({'WARNING'}, "No image texture nodes found on selected objects")
            return {'CANCELLED'}

        converted_by_source = {}
        output_owner = {}
        converted_count = 0
        relinked_count = 0
        modernized_count = 0
        skipped_format = 0
        skipped_no_path = 0
        skipped_missing_source = 0
        skipped_modernize = 0
        failed_count = 0
        fail_messages = []

        for node in tex_nodes:
            src_image = node.image
            if not src_image:
                continue

            src_path = self._resolve_image_source_path(src_image)
            if not self._image_matches_source_format(src_image, self.source_format, source_exts):
                skipped_format += 1
                continue

            src_exists = bool(src_path) and os.path.exists(src_path)
            has_buffer = bool(src_image.has_data) or bool(getattr(src_image, "packed_file", None))
            if not src_path and not has_buffer:
                skipped_no_path += 1
                continue
            if not src_exists and not has_buffer:
                skipped_missing_source += 1
                continue

            cache_key = src_path if src_exists else f"packed::{src_image.as_pointer()}"
            dst_path = converted_by_source.get(cache_key)
            if dst_path is None:
                base_name = os.path.splitext(os.path.basename(src_path))[0] if src_path else os.path.splitext(src_image.name)[0]
                if not base_name:
                    base_name = f"image_{src_image.as_pointer()}"
                candidate = os.path.join(output_dir, f"{base_name}.{target_ext}")
                if candidate in output_owner and output_owner[candidate] != cache_key:
                    idx = 1
                    while True:
                        candidate = os.path.join(output_dir, f"{base_name}_{idx}.{target_ext}")
                        if candidate not in output_owner:
                            break
                        idx += 1
                dst_path = candidate
                try:
                    self._save_image_as_format(src_image, dst_path, self.target_format, context.scene)
                    converted_by_source[cache_key] = dst_path
                    output_owner[dst_path] = cache_key
                    converted_count += 1
                except Exception as exc:
                    failed_count += 1
                    if len(fail_messages) < 5:
                        fail_messages.append(f"{src_image.name}: {exc}")
                    continue

            try:
                new_image = bpy.data.images.load(dst_path, check_existing=True)
                try:
                    new_image.filepath = bpy.path.relpath(dst_path)
                except Exception:
                    new_image.filepath = dst_path
                node.image = new_image
                relinked_count += 1
            except Exception as exc:
                failed_count += 1
                if len(fail_messages) < 5:
                    fail_messages.append(f"{src_image.name}: {exc}")

        if self.modernize_materials:
            materials = self._collect_materials_from_selection(context)
            for mat in materials:
                try:
                    ok, reason = self._modernize_material_to_principled(mat)
                    if ok:
                        modernized_count += 1
                    else:
                        skipped_modernize += 1
                        if len(fail_messages) < 5:
                            fail_messages.append(f"{mat.name}: {reason}")
                except Exception as exc:
                    failed_count += 1
                    if len(fail_messages) < 5:
                        fail_messages.append(f"{mat.name}: {exc}")

        if relinked_count == 0 and modernized_count == 0:
            warn_msg = (
                f"No textures converted/relinked. Skipped format: {skipped_format}, "
                f"no path: {skipped_no_path}, missing source: {skipped_missing_source}, "
                f"modernize skipped: {skipped_modernize}, failed: {failed_count}"
            )
            if fail_messages:
                warn_msg += f" | e.g. {'; '.join(fail_messages)}"
            self.report({'WARNING'}, warn_msg)
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Converted {converted_count} file(s), relinked {relinked_count} node(s), "
            f"modernized {modernized_count} material(s), output: tex_{target_ext}"
        )

        if skipped_format or skipped_no_path or skipped_missing_source or skipped_modernize or failed_count:
            warn_msg = (
                f"Skipped format: {skipped_format}, no path: {skipped_no_path}, "
                f"missing file: {skipped_missing_source}, modernize skipped: {skipped_modernize}, "
                f"failed: {failed_count}"
            )
            if fail_messages:
                warn_msg += f" | e.g. {'; '.join(fail_messages)}"
            self.report({'WARNING'}, warn_msg)

        return {'FINISHED'}


class OBJECT_OT_lightoff(bpy.types.Operator):
    """Turn off light sensibility"""
    bl_idname = "light.off"
    bl_label = "Turn off light sensibility"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.context.scene.game_settings.material_mode = 'GLSL'
        bpy.context.scene.game_settings.use_glsl_lights = False
        return {'FINISHED'}

class OBJECT_OT_LOD0polyreducer(bpy.types.Operator):
    """Reduce the polygon number to a correct LOD0 set up"""
    bl_idname = "lod0poly.reducer"
    bl_label = "Reduce the polygon number to a correct LOD0 set up"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context = bpy.context

        selected_objs = context.selected_objects

        for obj in selected_objs:
            me = obj.data
            tot_poly = len(me.polygons)
            tot_area = areamesh(obj)
            final_poly = tot_area*1000
            if final_poly < tot_poly:
                ratio = final_poly/tot_poly
                print("ratio is "+ str(ratio))
                decimate_mesh(context,obj,ratio,'LOD0')

        return {'FINISHED'}

class OBJECT_OT_cycles2bi(bpy.types.Operator):
    """Convert cycles to bi"""
    bl_idname = "cycles2bi.material"
    bl_label = "Convert cycles to bi"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.context.scene.render.engine = 'BLENDER_RENDER'
        cycles2bi()

        return {'FINISHED'}



#________________________________________________________

class OBJECT_OT_deactivatematerial(bpy.types.Operator):
    """De-activate node  materials for selected object"""
    bl_idname = "deactivatenode.material"
    bl_label = "De-activate cycles node materials for selected object and switch to BI"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.context.scene.render.engine = 'BLENDER_RENDER'
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                mat.use_nodes = False

        return {'FINISHED'}
    
#-------------------------------------------------------------

class OBJECT_OT_activatematerial(bpy.types.Operator):
    """Activate node materials for selected object"""
    bl_idname = "activatenode.material"
    bl_label = "Activate cycles node materials for selected object and switch to cycles"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.context.scene.render.engine = 'CYCLES'
        for obj in bpy.context.selected_objects:
            for matslot in obj.material_slots:
                mat = matslot.material
                mat.use_nodes = True

        return {'FINISHED'}


# class OBJECT_OT_CenterMass(bpy.types.Operator):
#     bl_idname = "center.mass"
#     bl_label = "Center Mass"
#     bl_options = {"REGISTER", "UNDO"}

#     def execute(self, context):

#         selection = bpy.context.selected_objects
# #        bpy.ops.object.select_all(action='DESELECT')

#         # translate objects in SCS coordinate
#         for obj in selection:
#             obj.select_set(True)
#             bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
#         return {'FINISHED'}

class OBJECT_OT_LocalTexture(bpy.types.Operator):
    bl_idname = "local.texture"
    bl_label = "Local texture mode ON"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.file.autopack_toggle()
        bpy.ops.file.autopack_toggle()
        bpy.ops.file.unpack_all(method='WRITE_LOCAL')
        bpy.ops.file.make_paths_relative()
        return {'FINISHED'}


class OBJECT_OT_createpersonalgroups(bpy.types.Operator):
    bl_idname = "create.personalgroups"
    bl_label = "Create groups per single object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for ob in bpy.context.selected_objects:
            bpy.ops.object.select_all(action='DESELECT')
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            make_group(ob,context)
        return {'FINISHED'}


class OBJECT_OT_removealluvexcept1(bpy.types.Operator):
    bl_idname = "remove.alluvexcept1"
    bl_label = "Remove all the UVs except the first one"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for ob in bpy.context.selected_objects:
            if ob.data.uv_layers[1]:
                uv_layers = ob.data.uv_layers
                uv_layers.remove(uv_layers[1])
        return {'FINISHED'}

class OBJECT_OT_removefromallgroups(bpy.types.Operator):
    bl_idname = "remove.fromallgroups"
    bl_label = "Remove the object(s) from all the Groups"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for ob in bpy.context.selected_objects:
            bpy.ops.group.objects_remove_all()
        return {'FINISHED'}
    
    
    
class OBJECT_OT_multimateriallayout(bpy.types.Operator):
    """Create multimaterial layout on selected mesh"""
    bl_idname = "multimaterial.layout"
    bl_label = "Create a multimaterial layout for selected meshe(s)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        start_time = time.time()
        totmodels=len(context.selected_objects)
        padding = 0.05
        #ob = bpy.context.object
        print("Found "+str(totmodels)+" models.")
        currentmod = 1
        for ob in context.selected_objects:
            start_time_ob = time.time()
            print("")
            print("***********************")
            print("I'm starting to process: "+ob.name+" model ("+str(currentmod)+"/"+str(totmodels)+")")
            print("***********************")
            print("")
            bpy.ops.object.select_all(action='DESELECT')
            ob.select = True
            bpy.context.scene.objects.active = ob
            currentobjname = ob.name
            objectname = ob.name
            me = ob.data
            tot_poly = len(me.polygons)
            materialnumber = desiredmatnumber(ob) #final number of whished materials
            materialsoriginal=len(ob.material_slots)
            cleaned_obname = clean_name(objectname)
            print("Removing the old "+str(materialsoriginal)+" materials..")

            for i in range(0,materialsoriginal):
                bpy.ops.object.material_slot_remove()
            current_material = 1
            for mat in range(materialnumber-1):
                bpy.ops.object.editmode_toggle()
                print("Selecting polygons for mat: "+str(mat+1)+"/"+str(materialnumber))
                bpy.ops.mesh.select_all(action='DESELECT')
                me.update()
                poly = len(me.polygons)
                bm = bmesh.from_edit_mesh(me)
                for i in range(5):
                    #print(i+1)
                    r = choice([(0,poly)])
                    random_index=(randint(*r))
                    if hasattr(bm.faces, "ensure_lookup_table"):
                        bm.faces.ensure_lookup_table()
                    bm.faces[random_index].select = True
                    bmesh.update_edit_mesh(me, True)
                poly_sel = 5
                while poly_sel <= (tot_poly/materialnumber):
                    bpy.ops.mesh.select_more(use_face_step=True)
                    ob.update_from_editmode()
                    poly_sel = len([p for p in ob.data.polygons if p.select])
                bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.01, user_area_weight=0.0, use_aspect=True)
#                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=padding)
                bpy.ops.uv.pack_islands(margin=padding)
                print("Creating new textures (remember to save them later..)")
                bpy.ops.object.editmode_toggle()
                current_tex_name = (cleaned_obname+'_t'+str(current_material))
                newimage2selpoly(ob, current_tex_name)
                bpy.ops.object.editmode_toggle()
                bpy.ops.mesh.separate(type='SELECTED')
                bpy.ops.object.editmode_toggle()
                current_material += 1

            bpy.ops.object.editmode_toggle()
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(island_margin=padding)
            bpy.ops.uv.pack_islands(margin=padding)
            bpy.ops.object.editmode_toggle()
            current_tex_name = (cleaned_obname+'_t'+str(current_material))
            newimage2selpoly(ob, current_tex_name)
            bpy.ops.object.select_all(action='DESELECT')
            ob.select = True
            bpy.context.scene.objects.active = ob
            currentobjname = ob.name

            for mat in range(materialnumber-1):

                bpy.data.objects[getnextobjname(currentobjname)].select = True
                nextname = getnextobjname(currentobjname)
                currentobjname = nextname

            bpy.ops.object.join()
            bpy.ops.object.editmode_toggle()
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles()
            bpy.ops.object.editmode_toggle()
            #bpy.ops.view3d.texface_to_material()
            print('>>> "'+ob.name+'" ('+str(currentmod)+'/'+ str(totmodels) +') object baked in '+str(time.time() - start_time_ob)+' seconds')
            currentmod += 1
        end_time = time.time() - start_time
        print(' ')
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(totmodels)+' objects processed in '+str(end_time)+' seconds')
        print('>>>>>>>>>>>>>>>>>>>>>>>>>>>')       
        return {'FINISHED'}

def switch_LOD_linked_data():

    # current scene
    scn = bpy.context.scene

    # path to the blend
    filepath = "/path/to/file.blend"

    # name of object(s) to append or link
    obj_name = "Cube"

    # append, set to true to keep the link to the original file
    link = False

    # link all objects starting with 'Cube'
    with bpy.data.libraries.load(filepath, link=link) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects if name.startswith(obj_name)]

    #link object to current scene
    for obj in data_to.objects:
        if obj is not None:
            scn.objects.link(obj)

class OBJECT_OT_remove_suffixnumber(bpy.types.Operator):
    bl_idname = "remove.suffixnumber"
    bl_label = "Remove the suffix from object's name"
    bl_options = {"REGISTER", "UNDO"}

    suffix : StringProperty() # type: ignore

    def execute(self, context):
        for ob in bpy.context.selected_objects:
            clean_suffix(ob,self.suffix)
        return {'FINISHED'}

class OBJECT_OT_setmaterial_blend(bpy.types.Operator):
    bl_idname = "setmaterial.blend"
    bl_label = "Set material blend for materials"
    bl_options = {"REGISTER", "UNDO"}

    blendmode: StringProperty() # type: ignore

    def execute(self, context):
        for ob in bpy.context.selected_objects:
            for mat in ob.material_slots:
                mat.material.blend_method = self.blendmode
        return {'FINISHED'}

        
