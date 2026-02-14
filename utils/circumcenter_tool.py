import bpy
import bmesh
import math
import traceback
import mathutils
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, FloatProperty, EnumProperty, FloatVectorProperty

class MESH_OT_improved_circumcenter(Operator):
    """Create a circle from three selected vertices, using their circumcenter as the center"""
    bl_idname = "mesh.improved_circumcenter"
    bl_label = "Circle from 3 Points"
    bl_options = {'REGISTER', 'UNDO'}
    
    circle_segments: bpy.props.IntProperty(
        name="Segments",
        description="Number of segments in the circle",
        default=32,
        min=3,
        max=128
    )
    
    circle_color: FloatVectorProperty(
        name="Circle Color",
        description="Color for the circle",
        subtype='COLOR',
        default=(0.0, 0.8, 1.0, 1.0),
        min=0.0,
        max=1.0,
        size=4
    )
    
    create_object: BoolProperty(
        name="Create New Object",
        description="Create a new object (otherwise adds to selected object)",
        default=True
    )
    
    use_selected_vertices: BoolProperty(
        name="Use Selected Vertices",
        description="Use the currently selected vertices instead of picking new ones",
        default=False
    )
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
    
    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Select a mesh object")
                return {'CANCELLED'}
            
            # If we're not in edit mode, enter it
            if obj.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # Get the bmesh from the edit mesh
            bm = bmesh.from_edit_mesh(obj.data)
            
            # Get selected vertices
            selected_verts = [v for v in bm.verts if v.select]
            
            if len(selected_verts) != 3:
                self.report({'ERROR'}, "Select exactly three vertices")
                return {'CANCELLED'}
            
            # Get the coordinates in world space
            co_final_1 = obj.matrix_world @ selected_verts[0].co
            ax = co_final_1[0]
            ay = co_final_1[1]
            
            co_final_2 = obj.matrix_world @ selected_verts[1].co
            bx = co_final_2[0]
            by = co_final_2[1]
            
            co_final_3 = obj.matrix_world @ selected_verts[2].co
            cx = co_final_3[0]
            cy = co_final_3[1]
            
            # Calculate Z as the average of the three vertices
            abcz = (co_final_1[2] + co_final_2[2] + co_final_3[2]) / 3
            
            # Debug info
            self.report({'INFO'}, f"Points: ({ax:.2f}, {ay:.2f}), ({bx:.2f}, {by:.2f}), ({cx:.2f}, {cy:.2f})")
            
            try:
                # Calculate the circumcenter
                ux, uy = self.calculate_circumcenter(ax, ay, bx, by, cx, cy)
                
                # Calculate the radius of the circle
                radius_circle = self.calculate_distance(ux, uy, ax, ay)
                self.report({'INFO'}, f"Circumcenter: ({ux:.2f}, {uy:.2f}), Radius: {radius_circle:.2f}")
                
                # Switch to Object Mode to create the circle
                bpy.ops.object.mode_set(mode='OBJECT')
                
                if self.create_object:
                    # Create a new mesh object with a circle
                    bpy.ops.object.select_all(action='DESELECT')
                    
                    # Generate an appropriate name based on the source object
                    base_name = f"{obj.name}_circumference"
                    
                    # Check if objects with this name already exist and add a suffix if needed
                    existing_names = [o.name for o in bpy.data.objects if o.name.startswith(base_name)]
                    if existing_names:
                        # Find the next available number
                        suffix = 1
                        while f"{base_name}_{suffix:02d}" in existing_names:
                            suffix += 1
                        circle_name = f"{base_name}_{suffix:02d}"
                    else:
                        circle_name = f"{base_name}_01"
                    
                    # Create a new mesh for the circle
                    mesh = bpy.data.meshes.new(f"{circle_name}_mesh")
                    circle_obj = bpy.data.objects.new(circle_name, mesh)
                    
                    # Add it to the current collection
                    context.collection.objects.link(circle_obj)
                    
                    # Create the circle geometry
                    verts = []
                    edges = []
                    
                    # Calculate vertices for the circle
                    for i in range(self.circle_segments):
                        angle = i * 2 * math.pi / self.circle_segments
                        x = ux + radius_circle * math.cos(angle)
                        y = uy + radius_circle * math.sin(angle)
                        verts.append((x, y, abcz))
                        edges.append((i, (i + 1) % self.circle_segments))
                    
                    # Create the mesh from the vertices and edges
                    mesh.from_pydata(verts, edges, [])
                    mesh.update()
                    
                    # Create a material for the circle
                    circle_material = bpy.data.materials.new(name="CircleMaterial")
                    circle_material.use_nodes = True
                    circle_material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = self.circle_color
                    
                    # Assign the material to the circle
                    if len(circle_obj.data.materials) == 0:
                        circle_obj.data.materials.append(circle_material)
                    else:
                        circle_obj.data.materials[0] = circle_material
                    
                    # Set the object display color and make it visible in viewport
                    if hasattr(circle_obj, "color"):
                        circle_obj.color = self.circle_color
                    
                    # Make sure that object color is used for display
                    circle_obj.display_type = 'SOLID'
                    circle_obj.show_wire = True
                    
                    # Set color display options safely checking API availability
                    try:
                        # For newer Blender versions
                        if hasattr(circle_obj.display, "show_object_color"):
                            circle_obj.display.show_object_color = True
                    except:
                        # Older versions might use different API
                        pass
                    
                    # Select the new circle
                    circle_obj.select_set(True)
                    context.view_layer.objects.active = circle_obj
                else:
                    # Add the circle to the current object
                    # Make sure we're back in edit mode
                    bpy.ops.object.mode_set(mode='EDIT')
                    bm = bmesh.from_edit_mesh(obj.data)
                    
                    # Deselect all
                    for v in bm.verts:
                        v.select = False
                    for e in bm.edges:
                        e.select = False
                    for f in bm.faces:
                        f.select = False
                    
                    # Calculate vertices for the circle
                    new_verts = []
                    for i in range(self.circle_segments):
                        angle = i * 2 * math.pi / self.circle_segments
                        x = ux + radius_circle * math.cos(angle)
                        y = uy + radius_circle * math.sin(angle)
                        
                        # Convert from world space to local space
                        world_co = mathutils.Vector((x, y, abcz))
                        local_co = obj.matrix_world.inverted() @ world_co
                        
                        # Create a new vertex and add it to the mesh
                        new_vert = bm.verts.new(local_co)
                        new_vert.select = True
                        new_verts.append(new_vert)
                    
                    # Create edges between the vertices
                    for i in range(self.circle_segments):
                        edge = bm.edges.new([new_verts[i], new_verts[(i + 1) % self.circle_segments]])
                        edge.select = True
                    
                    # Update the bmesh
                    bmesh.update_edit_mesh(obj.data)
            
            except ValueError as e:
                self.report({'ERROR'}, str(e))
                if context.object and context.object.mode == 'OBJECT':
                    bpy.ops.object.mode_set(mode='EDIT')
                return {'CANCELLED'}
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            traceback.print_exc()
            if context.object and context.object.mode == 'OBJECT':
                bpy.ops.object.mode_set(mode='EDIT')
            return {'CANCELLED'}
    
    def calculate_circumcenter(self, ax, ay, bx, by, cx, cy):
        """Calculate the circumcenter of three points"""
        d = 2 * ((ax * (by - cy)) + (bx * (cy - ay)) + (cx * (ay - by)))
        if abs(d) < 1e-6:
            raise ValueError("The points are collinear and don't form a valid triangle.")
        
        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
        
        return (ux, uy)
    
    def calculate_distance(self, x1, y1, x2, y2):
        """Calculate the distance between two points"""
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


class MESH_OT_apply_circumcenter(Operator):
    """Apply Circumcenter with current settings"""
    bl_idname = "mesh.apply_circumcenter"
    bl_label = "Create Circle from Selected Vertices"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'
    
    def execute(self, context):
        try:
            # Get scene properties
            circle_segments = context.scene.cc_circle_segments
            circle_color = context.scene.cc_circle_color
            create_object = context.scene.cc_create_object
            
            # Check if we're in edit mode
            if context.object.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
                self.report({'INFO'}, "Switched to Edit mode - please select three vertices")
                return {'FINISHED'}
            
            # Verify we have exactly three vertices selected
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            selected_verts = [v for v in bm.verts if v.select]
            
            if len(selected_verts) != 3:
                self.report({'WARNING'}, "Please select exactly three vertices")
                return {'CANCELLED'}
            
            # Apply the circumcenter operator with settings from the panel
            bpy.ops.mesh.improved_circumcenter(
                circle_segments=circle_segments,
                circle_color=circle_color,
                create_object=create_object,
                use_selected_vertices=True
            )
            
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            traceback.print_exc()
            return {'CANCELLED'}


class PANEL_PT_CircumcenterPanel(Panel):
    """Creates a panel for the Circumcenter tool in the UI"""
    bl_label = "Circle from 3 Points"
    bl_idname = "VIEW3D_PT_circumcenter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 32
    
    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Tool explanation
        box = layout.box()
        col = box.column()
        col.label(text="Create a circle from 3 points")
        col.label(text="Uses geometry's circumcenter")
        
        # Step 1: Enter Edit Mode
        if context.object.mode != 'EDIT':
            box = layout.box()
            row = box.row()
            row.label(text="1. Enter Edit Mode first", icon='ERROR')
            row = box.row()
            op = row.operator("object.mode_set", text="Enter Edit Mode")
            op.mode = 'EDIT'
            return
        
        # Step 2: Select vertices
        bm = bmesh.from_edit_mesh(context.edit_object.data)
        selected_verts = [v for v in bm.verts if v.select]
        
        box = layout.box()
        row = box.row()
        if len(selected_verts) != 3:
            row.label(text=f"2. Select exactly 3 vertices ({len(selected_verts)}/3)", icon='ERROR')
            row = box.row()
            row.operator("mesh.select_mode", text="Vertex Select").type = 'VERT'
            return
        else:
            row.label(text="2. Vertices selected (3/3)", icon='CHECKMARK')
        
        # Step 3: Circle options
        box = layout.box()
        col = box.column()
        col.label(text="3. Circle options:")
        
        row = box.row()
        row.prop(scene, "cc_circle_segments", text="Segments")
        
        row = box.row()
        row.prop(scene, "cc_circle_color", text="")
        
        row = box.row()
        row.prop(scene, "cc_create_object", text="Create as new object")
        
        # Apply button
        row = layout.row()
        op = row.operator("mesh.apply_circumcenter", text="Create Circle", icon='MESH_CIRCLE')
        
        # Information text
        box = layout.box()
        col = box.column()
        col.label(text="The circle will pass through")
        col.label(text="all three selected vertices")


# Registration
classes = (
    MESH_OT_improved_circumcenter,
    MESH_OT_apply_circumcenter,
    PANEL_PT_CircumcenterPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register scene properties
    bpy.types.Scene.cc_circle_segments = bpy.props.IntProperty(
        name="Circle Segments",
        description="Number of segments in the circle",
        default=32,
        min=3,
        max=128
    )
    
    bpy.types.Scene.cc_circle_color = bpy.props.FloatVectorProperty(
        name="Circle Color",
        description="Color for the circle",
        subtype='COLOR',
        default=(0.0, 0.8, 1.0, 1.0),
        min=0.0,
        max=1.0,
        size=4
    )
    
    bpy.types.Scene.cc_create_object = bpy.props.BoolProperty(
        name="Create as New Object",
        description="Create a new object (otherwise adds to selected object)",
        default=True
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove scene properties
    del bpy.types.Scene.cc_circle_segments
    del bpy.types.Scene.cc_circle_color
    del bpy.types.Scene.cc_create_object


if __name__ == "__main__":
    register()
