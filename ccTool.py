import bpy
from .functions import *



class OBJECT_OT_removeccsetup(bpy.types.Operator):
    """Remove cc node for selected objects"""
    bl_idname = "removeccnode.material"
    bl_label = "Remove cycles cc node for selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        issues = []
        removed = 0
        for obj_name, mat in cc_collect_selected_materials(context):
            ok = remove_cc_setup(mat)
            if ok:
                removed += 1
            else:
                cc_report_material_issue(obj_name, mat.name, "remove cc setup failed", issues)

        self.report({'INFO'}, f"Removed CC setup from {removed} material(s)")
        if issues:
            self.report({'WARNING'}, "; ".join(issues[:3]))

        return {'FINISHED'}
    
class OBJECT_OT_applyccsetup(bpy.types.Operator):
    """Apply color correction images to materials and discard the originals (they will NOT be erased from the HD"""
    bl_idname = "applyccsetup.material"
    bl_label = "Apply color correction images to materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        issues = []
        applied = 0
        for obj_name, mat in cc_collect_selected_materials(context):
            ok, reason = cc_apply_setup(mat, keep_backup=True)
            if ok:
                applied += 1
            else:
                cc_report_material_issue(obj_name, mat.name, reason, issues)

        save_result = save_dirty_images_best_effort()
        self.report(
            {'INFO'},
            f"Applied CC to {applied} material(s), saved images: {save_result['saved_count']}"
        )
        if issues:
            self.report({'WARNING'}, "; ".join(issues[:3]))
        if save_result["failed_count"] or save_result["unsavable_count"]:
            self.report(
                {'WARNING'},
                f"Image save issues: failed={save_result['failed_count']}, missing path={save_result['unsavable_count']}"
            )

        return {'FINISHED'}

#-------------------------------------------------------------
class OBJECT_OT_createccsetup(bpy.types.Operator):
    """Create a color correction node for selected objects"""
    bl_idname = "create.ccsetup"
    bl_label = "Create cycles materials for selected object"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        bpy.context.scene.render.engine = 'CYCLES'
        selected_materials = cc_collect_selected_materials(context)
        if not selected_materials:
            self.report({'ERROR'}, "No mesh materials selected")
            return {'CANCELLED'}

        cc_nodegroup = None
        for _, mat in selected_materials:
            cc_node = cc_find_node_by_role(mat, "cc_node") or cc_find_legacy_node(mat, "cc_node")
            if cc_node and cc_node.type == 'GROUP' and cc_node.node_tree is not None:
                cc_nodegroup = cc_node.node_tree
                break
        if cc_nodegroup is None:
            active_name = context.active_object.name if context.active_object else "CC"
            cc_nodegroup = create_correction_nodegroup(active_name + "_CC")

        issues = []
        configured = 0
        for obj_name, mat in selected_materials:
            ok, reason = cc_node_to_mat(mat, cc_nodegroup)
            if not ok:
                cc_report_material_issue(obj_name, mat.name, reason, issues)
                continue
            tex_ok, tex_reason = create_new_tex_set(mat, "cc_image")
            if not tex_ok:
                cc_report_material_issue(obj_name, mat.name, tex_reason, issues)
                continue
            configured += 1

        context.window_manager.ccToolViewVar.cc_view = "cc_node"
        self.report({'INFO'}, f"CC setup created on {configured} material(s)")
        if issues:
            self.report({'WARNING'}, "; ".join(issues[:3]))

        return {'FINISHED'}
#-------------------------------------------------------------
class OBJECT_OT_setccview(bpy.types.Operator):
    """Set view mode"""
    bl_idname = "set.cc_view"
    bl_label = "Set view mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        set_texset_obj(context)
 
        return {'FINISHED'}

#-------------------------------------------------------------

class OBJECT_OT_bakecyclesdiffuse(bpy.types.Operator):
    """Color correction to new texture set"""
    bl_idname = "bake.cyclesdiffuse"
    bl_label = "Transfer new color correction to a new texture set"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_materials = cc_collect_selected_materials(context)
        missing_cc_image = []
        for obj_name, mat in selected_materials:
            if cc_find_cc_image_node(mat) is None:
                missing_cc_image.append(f"{obj_name}/{mat.name}")
        if missing_cc_image:
            self.report({'WARNING'}, f"{len(missing_cc_image)} material(s) missing cc_image target")
        context.window_manager.ccToolViewVar.cc_view = "cc_node"
        set_texset_obj(context)
        bake_tex_set("cc")
        context.window_manager.ccToolViewVar.cc_view = "cc_image"
        set_texset_obj(context)

        return {'FINISHED'}

####-----------------------------------------------------------
