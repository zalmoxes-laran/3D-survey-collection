import bpy
import time
import bmesh
import math
from .functions import *
from bpy.props import BoolProperty


CUTTER_COLLECTION_NAME = "_cutter"


def _is_mesh(obj):
    return obj is not None and obj.type == 'MESH'


def _is_unit_scale(obj, tol=1e-5):
    sx, sy, sz = obj.scale
    return abs(sx - 1.0) <= tol and abs(sy - 1.0) <= tol and abs(sz - 1.0) <= tol


def _ensure_cutter_collection(scene):
    col = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
    if col is None:
        col = bpy.data.collections.new(CUTTER_COLLECTION_NAME)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def _is_cutter(obj):
    return bool(obj.get("e3dsc_is_cutter", False)) or obj.name.lower().startswith("cutter")


def _tag_and_link_cutters(scene, cutter_objects):
    cutter_col = _ensure_cutter_collection(scene)
    for obj in cutter_objects:
        if not _is_mesh(obj):
            continue
        obj["e3dsc_is_cutter"] = True
        if obj.name not in cutter_col.objects:
            cutter_col.objects.link(obj)
        # Keep cutters only in the dedicated root collection.
        for parent_col in list(obj.users_collection):
            if parent_col != cutter_col:
                parent_col.objects.unlink(obj)


def _sync_named_cutters_to_collection(scene):
    named_cutters = [obj for obj in bpy.data.objects if _is_mesh(obj) and obj.name.lower().startswith("cutter")]
    _tag_and_link_cutters(scene, named_cutters)


def _get_available_cutters(scene):
    _sync_named_cutters_to_collection(scene)
    cutter_col = _ensure_cutter_collection(scene)
    return [obj for obj in cutter_col.objects if _is_mesh(obj)]


def _preprocess_mesh_topology(context, obj):
    """Basic topology cleanup before knife projection to reduce split failures."""
    if not _is_mesh(obj):
        return
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    try:
        bpy.ops.mesh.remove_doubles()
    except Exception:
        bpy.ops.mesh.merge_by_distance()
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')


def _should_preclean(scene):
    return bool(getattr(scene, "e3dsc_segmentation_preclean", True))


def _knife_project_cut(context, cutter_obj, target_obj):
    bpy.ops.object.select_all(action='DESELECT')
    target_obj.select_set(True)
    context.view_layer.objects.active = target_obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    # Select cutter while keeping target in edit mode (required by knife_project).
    cutter_obj.select_set(True)
    context.view_layer.objects.active = target_obj
    bpy.ops.mesh.knife_project(cut_through=True)
    try:
        bpy.ops.mesh.separate(type='SELECTED')
    except Exception:
        pass
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')



class OBJECT_OT_setcutter(bpy.types.Operator):
    """Segment (projecting) a series of selected elements using an active mesh"""
    bl_idname = "set.cutter"
    bl_label = "Segment (projecting) a series of selected elements using an active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    apply_scale_before_create: BoolProperty(
        name="Apply Scale Before Creating Cutter Set",
        description="Apply scale to the active object before creating cutter set",
        default=True,
    ) # type: ignore

    needs_scale_fix: BoolProperty(default=False, options={'HIDDEN'}) # type: ignore

    @classmethod
    def poll(cls, context):
        return _is_mesh(context.active_object) and context.mode == 'OBJECT'

    def invoke(self, context, event):
        active = context.active_object
        if not _is_mesh(active):
            self.report({'ERROR'}, "Select an active mesh object first")
            return {'CANCELLED'}

        self.needs_scale_fix = not _is_unit_scale(active)
        if self.needs_scale_fix:
            return context.window_manager.invoke_props_dialog(self, width=460)
        return self.execute(context)

    def draw(self, context):
        if self.needs_scale_fix:
            layout = self.layout
            col = layout.column(align=True)
            col.label(text="Active object scale is not 1,1,1.", icon='ERROR')
            col.label(text="Cutter Set works on mesh geometry and may fail with unapplied scale.")
            col.label(text="Apply scale now before creating the cutter set?")
            col.prop(self, "apply_scale_before_create")

    def execute(self, context):
        active = context.active_object
        if not _is_mesh(active):
            self.report({'ERROR'}, "Select an active mesh object first")
            return {'CANCELLED'}

        if self.needs_scale_fix:
            if not self.apply_scale_before_create:
                self.report({'WARNING'}, "Operation cancelled: apply object scale first")
                return {'CANCELLED'}
            bpy.ops.object.select_all(action='DESELECT')
            active.select_set(True)
            context.view_layer.objects.active = active
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        scene = context.scene
        side = scene.TILE_side_length
        objects_before = set(bpy.data.objects.keys())
        create_cutter_series("cutter", side, side)
        created = [
            obj for obj in bpy.data.objects
            if obj.name not in objects_before and _is_mesh(obj)
        ]
        created_cutters = [obj for obj in created if obj.name.lower().startswith("cutter")]
        _tag_and_link_cutters(scene, created_cutters)
        self.report({'INFO'}, f"Created cutter set with {len(created_cutters)} cutter(s)")
        return {'FINISHED'}


class OBJECT_OT_clearcutters(bpy.types.Operator):
    """Delete all cutters from the _cutter collection"""
    bl_idname = "set.clear_cutters"
    bl_label = "Delete all cutters"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cutter_col = bpy.data.collections.get(CUTTER_COLLECTION_NAME)
        if cutter_col is None:
            self.report({'INFO'}, "No cutter set collection found")
            return {'FINISHED'}

        cutters = [obj for obj in cutter_col.objects if _is_mesh(obj)]
        for obj in cutters:
            bpy.data.objects.remove(obj, do_unlink=True)

        self.report({'INFO'}, f"Deleted {len(cutters)} cutter(s)")
        return {'FINISHED'}

class OBJECT_OT_projectsegmentation(bpy.types.Operator):
    """Segment (projecting) a series of selected elements using an active mesh"""
    bl_idname = "project.segmentation"
    bl_label = "Segment (projecting) a series of selected elements using an active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        start_time = time.time()
        ob_counter = 1

        ob_cutting = context.active_object
        if not _is_mesh(ob_cutting):
            self.report({'ERROR'}, "Select an active cutter mesh")
            return {'CANCELLED'}

        targets = [
            ob for ob in context.selected_objects
            if _is_mesh(ob) and ob != ob_cutting and not _is_cutter(ob)
        ]
        if not targets:
            self.report({'ERROR'}, "Select one or more target meshes (excluding cutters)")
            return {'CANCELLED'}

        ob_tot = len(targets)
        for ob in targets:
            start_time_ob = time.time()
            print('>>> CUTTING >>>')
            print('>>>>>> the object is going to be cut: ""' +
                  ob.name+'"" ('+str(ob_counter)+'/'+str(ob_tot)+')')

            if _should_preclean(context.scene):
                _preprocess_mesh_topology(context, ob)
            _knife_project_cut(context, ob_cutting, ob)

            print('>>> "'+ob.name+'" ('+str(ob_counter)+'/' + str(ob_tot) +
                  ') object cut in '+str(time.time() - start_time_ob)+' seconds')
            ob_counter += 1

        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}


class OBJECT_OT_projectsegmentationinversed(bpy.types.Operator):
    """Segment (projecting) an active mesh using a series of selected elements"""
    bl_idname = "project.segmentationinv"
    bl_label = "Segment (projecting) an active mesh using a series of selected elements"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        start_time = time.time()
        ob_counter = 1
        ob_to_cut = context.active_object
        if not _is_mesh(ob_to_cut):
            self.report({'ERROR'}, "Select an active target mesh")
            return {'CANCELLED'}
        if _is_cutter(ob_to_cut):
            self.report({'ERROR'}, "Active object cannot be a cutter")
            return {'CANCELLED'}

        selected_cutters = [
            ob for ob in context.selected_objects
            if _is_mesh(ob) and ob != ob_to_cut and _is_cutter(ob)
        ]
        cutters = selected_cutters if selected_cutters else [
            ob for ob in _get_available_cutters(context.scene) if ob != ob_to_cut
        ]
        if not cutters:
            self.report({'ERROR'}, "No cutters available. Create a cutter set first.")
            return {'CANCELLED'}

        if _should_preclean(context.scene):
            try:
                _preprocess_mesh_topology(context, ob_to_cut)
            except RuntimeError as e:
                self.report({'WARNING'}, f"Pre-clean skipped on '{ob_to_cut.name}' (linked mesh, not editable): cutting on original mesh.")

        ob_tot = len(cutters)
        for ob in cutters:
            start_time_ob = time.time()
            print('>>> CUTTING >>>')
            print('>>>>>> the object "' + ob.name + '" ('+str(ob_counter) +
                  '/'+str(ob_tot)+') is cutting the object "' + ob_to_cut.name + '"')

            _knife_project_cut(context, ob, ob_to_cut)

            print('>>> "'+ob.name+'" ('+str(ob_counter)+'/' + str(ob_tot) +
                  ') object used to cut in '+str(time.time() - start_time_ob)+' seconds')
            ob_counter += 1

        end_time = time.time() - start_time
        print('<<<<<<< Process done >>>>>>')
        print('>>>'+str(ob_tot)+' objects processed in '+str(end_time)+' seconds')
        return {'FINISHED'}
