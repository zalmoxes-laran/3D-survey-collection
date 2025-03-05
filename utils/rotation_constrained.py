import bpy
import math
import mathutils
import bmesh
import numpy
import traceback

class MESH_OT_rotation_constrained(bpy.types.Operator):
    """Rotation with constrained vertices"""
    bl_idname = "mesh.rotation_constrained"
    bl_label = "Rotation Constrained"
    bl_options = {'REGISTER', 'UNDO'}

    raxis: bpy.props.EnumProperty(
            items=[("0", "X", "Rotate around X-axis"),
                   ("1", "Y", "Rotate around Y-axis"),
                   ("2", "Z", "Rotate around Z-axis"),
                   ],
            name="Rotation Axis",
            description="Specify the axis of rotation",
            default="1")

    caxis: bpy.props.EnumProperty(
            items=[("0", "X", "Constrain to X-axis"),
                   ("1", "Y", "Constrain to Y-axis"),
                   ("2", "Z", "Constrain to Z-axis"),
                   ],
            name="Constraint Axis",
            description="Specify the vertex constraint axis",
            default="2")

    rpoint: bpy.props.EnumProperty(
            items=[("0", "Mid", "Rotate the end face around its midpoint"),
                   ("1", "Max", "Rotate the end face around its highpoint"),
                   ("2", "Min", "Rotate the end face around its lowpoint"),
                   ],
            name="Rotation point",
            description="Specify the point on the end face to rotate around",
            default="0")

    rmirror: bpy.props.BoolProperty(name="Mirror:", default=False)

    rdeg: bpy.props.FloatProperty(name="Degrees", default=0, min=-120, max=120)

    def invoke(self, context, event):
        try:
            self.bmesh = bmesh.from_edit_mesh(context.active_object.data)
            bmfaces = [face for face in self.bmesh.faces if face.select]
            if not bmfaces:
                self.report({'WARNING'}, "No faces selected")
                return {'CANCELLED'}
                
            self.norm_z = numpy.sum([face.normal for face in bmfaces], axis=0)/len(bmfaces)
            self.norm_y = numpy.sum([face.calc_tangent_edge() for face in bmfaces], axis=0)/len(bmfaces)
            self.norm_x = numpy.sum([-face.normal.cross(-face.calc_tangent_edge()) for face in bmfaces], axis=0)/len(bmfaces)
            bpy.ops.object.editmode_toggle()
            self.mesh = context.active_object.data
            self.omw = context.active_object.matrix_world.copy()
            self.oml = context.active_object.matrix_local.copy()
            self.omwi = self.omw.inverted()
            bpy.ops.object.editmode_toggle()
            return self.execute(context)
        except Exception as e:
            self.report({'ERROR'}, f"Error in invoke: {str(e)}")
            traceback.print_exc()
            return {'CANCELLED'}

    def execute(self, context):
        try:
            # Verifica se stiamo facendo un'invocazione diretta (senza passare da invoke)
            if not hasattr(self, 'mesh') or not self.mesh:
                # Se siamo in modalità edit, otteniamo i dati necessari
                if context.object.mode == 'EDIT':
                    self.bmesh = bmesh.from_edit_mesh(context.active_object.data)
                    bmfaces = [face for face in self.bmesh.faces if face.select]
                    if not bmfaces:
                        self.report({'WARNING'}, "No faces selected")
                        return {'CANCELLED'}
                        
                    self.norm_z = numpy.sum([face.normal for face in bmfaces], axis=0)/len(bmfaces)
                    self.norm_y = numpy.sum([face.calc_tangent_edge() for face in bmfaces], axis=0)/len(bmfaces)
                    self.norm_x = numpy.sum([-face.normal.cross(-face.calc_tangent_edge()) for face in bmfaces], axis=0)/len(bmfaces)
                    bpy.ops.object.editmode_toggle()
                    self.mesh = context.active_object.data
                    self.omw = context.active_object.matrix_world.copy()
                    self.oml = context.active_object.matrix_local.copy()
                    self.omwi = self.omw.inverted()
                    bpy.ops.object.editmode_toggle()
                else:
                    self.report({'WARNING'}, "Must be in edit mode with faces selected")
                    return {'CANCELLED'}
            
            if self.rdeg != 0 and self.caxis != self.raxis:
                bpy.ops.object.editmode_toggle()
                posaxis = mathutils.Vector([(0, 1)[paxis not in (self.raxis, self.caxis)] for paxis in ("0", "1", "2")])
                posindex = list(posaxis).index(1)
                caxis = [(0, 1)[i == int(self.caxis)] for i in range(3)]
                faces = [face for face in self.mesh.polygons if face.select == True]
               
                if not faces:
                    bpy.ops.object.editmode_toggle()
                    self.report({'WARNING'}, "No faces selected")
                    return {'CANCELLED'}
                
                for face in faces:
                    if self.mesh.polygons.active == face.index:
                        faces.insert(0, faces.pop(faces.index(face)))
                        
                vertlists = [[self.mesh.vertices[fv] for fv in face.vertices] for face in faces]

                for vl, vertlist in enumerate(vertlists):                
                    for v in vertlist:
                        if context.scene.transform_orientation_slots[0].type == 'LOCAL':
                            vmax = max([v.co[posindex] for v in vertlist])
                            vmin = min([v.co[posindex] for v in vertlist])
                            refpos = ((vmin+vmax)/2, vmax, vmin)[int(self.rpoint)]
                            v.co += mathutils.Vector((v.co[posindex] - refpos) * mathutils.Vector((caxis)) * math.tan(float((-1, 1)[(vl > 0) * (self.rmirror)] * self.rdeg) * 0.0174533))

                        elif context.scene.transform_orientation_slots[0].type == 'NORMAL':
                            local_caxis = (self.norm_x, self.norm_y, self.norm_z)[int(self.caxis)]
                            local_posaxis = (self.norm_x, self.norm_y, self.norm_z)[posindex]
                            vmax = max([v.co.dot(mathutils.Vector(local_posaxis)) for v in vertlist])
                            vmin = min([v.co.dot(mathutils.Vector(local_posaxis)) for v in vertlist])
                            refpos = ((vmin+vmax)/2, vmax, vmin)[int(self.rpoint)]
                            v.co += mathutils.Vector((v.co.dot(mathutils.Vector(local_posaxis)) - refpos) * mathutils.Vector(local_caxis) * math.tan(float((-1, 1)[(vl > 0) * (self.rmirror)] * self.rdeg)*0.0174533))

                        elif context.scene.transform_orientation_slots[0].type == 'GLOBAL':
                            vmax = max([(self.omw@v.co)[posindex] for v in vertlist])
                            vmin = min([(self.omw@v.co)[posindex] for v in vertlist])
                            refpos = ((vmin+vmax)/2, vmax, vmin)[int(self.rpoint)]
                            v.co += mathutils.Vector(((self.omw@v.co)[posindex] - refpos) * mathutils.Vector((caxis)) * math.tan(float((-1, 1)[(vl > 0) * (self.rmirror)] * self.rdeg)*0.0174533))@self.omwi

                bpy.ops.object.editmode_toggle()
            else:
                if self.caxis == self.raxis:
                    self.report({'WARNING'}, "Rotation and constraint axes must be different")
                if self.rdeg == 0:
                    self.report({'INFO'}, "Degrees set to 0, no rotation applied")

            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error in execute: {str(e)}")
            traceback.print_exc()
            if context.object.mode == 'OBJECT':
                bpy.ops.object.editmode_toggle()
            return {'CANCELLED'}


class PANEL_PT_RotationConstrainedPanel(bpy.types.Panel):
    """Creates a panel for Rotation Constrained in the UI"""
    bl_label = "Rotation Constrained"
    bl_idname = "VIEW3D_PT_rotation_constrained"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_parent_id = "VIEW3D_PT_QuickUtils_ToolBar"  # Collegato direttamente al pannello QuickUtils
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'
    
    def draw(self, context):
        layout = self.layout
        
        # Prima aggiungere una spiegazione del tool
        box = layout.box()
        col = box.column()
        col.label(text="Tool for controlled mesh deformation")
        col.label(text="Allows precise bending of faces")
        
        if context.object.mode != 'EDIT':
            box = layout.box()
            row = box.row()
            row.label(text="1. Enter Edit Mode first", icon='ERROR')
            row = box.row()
            op = row.operator("object.mode_set", text="Enter Edit Mode")
            op.mode = 'EDIT'
            return
            
        # Check if any faces are selected in edit mode
        bm = bmesh.from_edit_mesh(context.edit_object.data)
        has_selection = any(face.select for face in bm.faces)
        
        if not has_selection:
            box = layout.box()
            row = box.row()
            row.label(text="2. Select face(s) to rotate", icon='ERROR')
            row = box.row()
            row.operator("mesh.select_mode", text="Face Select").type = 'FACE'
            return
        
        # Step 3: Configuration
        box = layout.box()
        col = box.column()
        col.label(text="3. Configure rotation settings:")
        
        # Explanation of axes
        box = layout.box()
        col = box.column()
        col.label(text="Axes Settings:")
        col.label(text="• Rotation: pivot axis for rotation")
        col.label(text="• Constraint: limits vertex movement")
        col.label(text="These MUST be different axes")
        
        row = layout.row()
        row.prop(context.scene, "rc_raxis", text="Rotation Axis")
        
        row = layout.row()
        row.prop(context.scene, "rc_caxis", text="Constraint Axis")
        
        if context.scene.rc_raxis == context.scene.rc_caxis:
            row = layout.row()
            row.label(text="Warning: Axes must differ", icon='ERROR')
        
        box = layout.box()
        col = box.column()
        col.label(text="Rotation Settings:")
        row = box.row()
        row.prop(context.scene, "rc_rpoint", text="Rotation Point")
        
        row = box.row()
        row.prop(context.scene, "rc_rmirror", text="Mirror")
        
        row = box.row()
        row.prop(context.scene, "rc_rdeg", text="Degrees")
        
        row = layout.row()
        op = row.operator("mesh.apply_rotation_constrained", text="Apply Rotation", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        
        # Keyboard shortcut info
        box = layout.box()
        col = box.column()
        col.label(text="Keyboard Shortcut: Alt+Shift+R")


class MESH_OT_apply_rotation_constrained(bpy.types.Operator):
    """Apply Rotation Constrained with current settings"""
    bl_idname = "mesh.apply_rotation_constrained"
    bl_label = "Apply Rotation Constrained"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'
    
    def execute(self, context):
        try:
            # Get scene properties
            raxis = context.scene.rc_raxis
            caxis = context.scene.rc_caxis
            rpoint = context.scene.rc_rpoint
            rmirror = context.scene.rc_rmirror
            rdeg = context.scene.rc_rdeg
            
            # Check if axes are different
            if raxis == caxis:
                self.report({'WARNING'}, "Rotation and constraint axes must be different")
                return {'CANCELLED'}
                
            # Check if degrees is not zero
            if rdeg == 0:
                self.report({'INFO'}, "Degrees set to 0, no rotation applied")
                return {'FINISHED'}
            
            # Assicurati che siamo in modalità edit
            if context.object.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
                self.report({'INFO'}, "Switched to Edit mode - please select a face first")
                return {'FINISHED'}
                
            # Verifica se ci sono facce selezionate
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            if not any(face.select for face in bm.faces):
                self.report({'WARNING'}, "Please select at least one face")
                return {'CANCELLED'}
            
            # Apply rotation constrained with settings from the panel
            bpy.ops.mesh.rotation_constrained(
                raxis=raxis,
                caxis=caxis,
                rpoint=rpoint,
                rmirror=rmirror,
                rdeg=rdeg
            )
            
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            traceback.print_exc()
            return {'CANCELLED'}


class OBJECT_OT_rotation_constrained_help(bpy.types.Operator):
    """Show help information for Rotation Constrained tool"""
    bl_idname = "object.rotation_constrained_help"
    bl_label = "Rotation Constrained Help"
    
    def execute(self, context):
        self.report({'INFO'}, "Rotation Constrained: Select faces in Edit mode, then set rotation and constraint axes (must be different)")
        return {'FINISHED'}


# Registration

classes = (
    MESH_OT_rotation_constrained,
    PANEL_PT_RotationConstrainedPanel,
    MESH_OT_apply_rotation_constrained,
    OBJECT_OT_rotation_constrained_help,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    # Store operator properties as scene properties for the panel
    bpy.types.Scene.rc_raxis = bpy.props.EnumProperty(
        items=[("0", "X", "Rotate around X-axis"),
               ("1", "Y", "Rotate around Y-axis"),
               ("2", "Z", "Rotate around Z-axis"),
               ],
        name="Rotation Axis",
        description="Specify the axis of rotation",
        default="1")

    bpy.types.Scene.rc_caxis = bpy.props.EnumProperty(
        items=[("0", "X", "Constrain to X-axis"),
               ("1", "Y", "Constrain to Y-axis"),
               ("2", "Z", "Constrain to Z-axis"),
               ],
        name="Constraint Axis",
        description="Specify the vertex constraint axis",
        default="2")

    bpy.types.Scene.rc_rpoint = bpy.props.EnumProperty(
        items=[("0", "Mid", "Rotate the end face around its midpoint"),
               ("1", "Max", "Rotate the end face around its highpoint"),
               ("2", "Min", "Rotate the end face around its lowpoint"),
               ],
        name="Rotation point",
        description="Specify the point on the end face to rotate around",
        default="0")

    bpy.types.Scene.rc_rmirror = bpy.props.BoolProperty(
        name="Mirror", 
        default=False)

    bpy.types.Scene.rc_rdeg = bpy.props.FloatProperty(
        name="Degrees", 
        default=0, 
        min=-120, 
        max=120)
    
    # Register keymaps
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='Mesh', space_type='EMPTY')
        kmi = km.keymap_items.new("mesh.rotation_constrained", 'R', 'PRESS', alt=True, shift=True)
        kmi.properties.rdeg = 0

def unregister():
    # Unregister keymaps
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        for km in wm.keyconfigs.addon.keymaps:
            if km.name == 'Mesh':
                for kmi in km.keymap_items:
                    if kmi.idname == 'mesh.rotation_constrained':
                        km.keymap_items.remove(kmi)
                        break
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    # Remove scene properties
    del bpy.types.Scene.rc_raxis
    del bpy.types.Scene.rc_caxis
    del bpy.types.Scene.rc_rpoint
    del bpy.types.Scene.rc_rmirror
    del bpy.types.Scene.rc_rdeg