import bpy
import os
import mathutils
from bpy.props import StringProperty, BoolProperty, FloatVectorProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator

class OBJECT_OT_IMPORTDXF(Operator):
    """Import DXF file with coordinate shifting support"""
    bl_idname = "import_dxf.button"
    bl_label = "Import DXF"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.import_file.dxf_3dsc('INVOKE_DEFAULT')
        return {'FINISHED'}

class ImportDXF_3DSC(Operator, ImportHelper):
    """Import a DXF file with coordinate shifting support using 3DSC shift values"""
    bl_idname = "import_file.dxf_3dsc"
    bl_label = "Import DXF with Shift"
    bl_options = {'PRESET', 'UNDO'}
    
    filename_ext = ".dxf"
    filter_glob: StringProperty(
        default="*.dxf",
        options={'HIDDEN'},
    )
    
    # Use 3DSC shift values
    shift_coordinates: BoolProperty(
        name="Shift Coordinates",
        description="Apply shift using 3DSC shift values",
        default=True,
    )
    
    import_entities: EnumProperty(
        name="Import Entities",
        options={'ENUM_FLAG'},
        items=(
            ('LINES', "Lines", "Import LINE entities"),
            ('CIRCLES', "Circles", "Import CIRCLE entities"),
            ('ARCS', "Arcs", "Import ARC entities"),
            ('POLYLINES', "Polylines", "Import POLYLINE entities"),
            ('TEXT', "Text", "Import TEXT entities"),
        ),
        default={'LINES', 'CIRCLES', 'ARCS', 'POLYLINES'},
    )
    
    create_collection: BoolProperty(
        name="Create Collection",
        description="Create a new collection for imported objects",
        default=True,
    )
    
    curve_resolution: IntProperty(
        name="Curve Resolution",
        description="Resolution for curve objects",
        default=12,
        min=2,
        max=64,
    )
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Coordinate Settings")
        box.prop(self, "shift_coordinates")
        if self.shift_coordinates:
            row = box.row()
            row.label(text=f"X Shift: {context.scene.BL_x_shift}")
            row = box.row()
            row.label(text=f"Y Shift: {context.scene.BL_y_shift}")
            row = box.row()
            row.label(text=f"Z Shift: {context.scene.BL_z_shift}")
        
        box = layout.box()
        box.label(text="Import Settings")
        box.prop(self, "import_entities")
        box.prop(self, "create_collection")
        box.prop(self, "curve_resolution")
    
    def execute(self, context):
        # Check if ezdxf is installed
        try:
            import ezdxf
        except ImportError:
            self.report({'ERROR'}, "The 'ezdxf' module is required. Please install it via pip: pip install ezdxf")
            return {'CANCELLED'}
        
        # Get shift values from 3DSC addon
        if self.shift_coordinates:
            shift_values = (
                context.scene.BL_x_shift,
                context.scene.BL_y_shift,
                context.scene.BL_z_shift
            )
        else:
            shift_values = (0.0, 0.0, 0.0)
        
        # Create a new collection if requested
        if self.create_collection:
            collection_name = os.path.basename(self.filepath).split(".")[0]
            new_collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(new_collection)
            collection = new_collection
        else:
            collection = context.collection
        
        # Parse and import the DXF file
        try:
            dxf = ezdxf.readfile(self.filepath)
            modelspace = dxf.modelspace()
            
            import_count = 0
            
            # Import different entity types based on user selection
            if 'LINES' in self.import_entities:
                count = self.import_dxf_lines(modelspace, collection, shift_values)
                import_count += count
                
            if 'CIRCLES' in self.import_entities:
                count = self.import_dxf_circles(modelspace, collection, shift_values)
                import_count += count
                
            if 'ARCS' in self.import_entities:
                count = self.import_dxf_arcs(modelspace, collection, shift_values)
                import_count += count
                
            if 'POLYLINES' in self.import_entities:
                count = self.import_dxf_polylines(modelspace, collection, shift_values)
                import_count += count
                
            if 'TEXT' in self.import_entities:
                count = self.import_dxf_text(modelspace, collection, shift_values)
                import_count += count
            
            self.report({'INFO'}, f"Imported {import_count} DXF entities with shift {shift_values}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error importing DXF: {str(e)}")
            return {'CANCELLED'}
    
    def import_dxf_lines(self, modelspace, collection, shift):
        """Import LINE entities from DXF"""
        import ezdxf
        
        lines = modelspace.query('LINE')
        count = 0
        
        if not lines:
            return count
            
        for line in lines:
            start = (
                line.dxf.start.x - shift[0],
                line.dxf.start.y - shift[1],
                line.dxf.start.z - shift[2] if hasattr(line.dxf.start, 'z') else -shift[2]
            )
            
            end = (
                line.dxf.end.x - shift[0],
                line.dxf.end.y - shift[1],
                line.dxf.end.z - shift[2] if hasattr(line.dxf.end, 'z') else -shift[2]
            )
            
            # Create curve
            curve_data = bpy.data.curves.new(name="Line", type='CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = self.curve_resolution
            
            # Create spline
            polyline = curve_data.splines.new('POLY')
            polyline.points.add(1)  # Add one point to the two default ones
            polyline.points[0].co = (start[0], start[1], start[2], 1.0)
            polyline.points[1].co = (end[0], end[1], end[2], 1.0)
            
            # Create object with layer name if available
            layer = line.dxf.layer if hasattr(line.dxf, 'layer') else "0"
            curve_obj = bpy.data.objects.new(f"Line_{layer}", curve_data)
            collection.objects.link(curve_obj)
            count += 1
            
        return count
    
    def import_dxf_circles(self, modelspace, collection, shift):
        """Import CIRCLE entities from DXF"""
        import ezdxf
        import math
        
        circles = modelspace.query('CIRCLE')
        count = 0
        
        if not circles:
            return count
            
        for circle in circles:
            center = (
                circle.dxf.center.x - shift[0],
                circle.dxf.center.y - shift[1],
                circle.dxf.center.z - shift[2] if hasattr(circle.dxf.center, 'z') else -shift[2]
            )
            
            radius = circle.dxf.radius
            
            # Create circle curve
            curve_data = bpy.data.curves.new(name="Circle", type='CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = self.curve_resolution
            
            # Create circle spline
            spline = curve_data.splines.new('BEZIER')
            num_points = 8  # Number of control points for the circle
            spline.bezier_points.add(num_points - 1)  # One point already exists
            
            # Set circle points
            for i in range(num_points):
                angle = (i / num_points) * 2 * math.pi
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)
                point = spline.bezier_points[i]
                point.co = (x, y, center[2])
                point.handle_left_type = 'AUTO'
                point.handle_right_type = 'AUTO'
            
            # Set curve properties
            spline.use_cyclic_u = True
            
            # Create object with layer name if available
            layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
            curve_obj = bpy.data.objects.new(f"Circle_{layer}", curve_data)
            collection.objects.link(curve_obj)
            count += 1
            
        return count
    
    def import_dxf_arcs(self, modelspace, collection, shift):
        """Import ARC entities from DXF"""
        import ezdxf
        import math
        
        arcs = modelspace.query('ARC')
        count = 0
        
        if not arcs:
            return count
            
        for arc in arcs:
            center = (
                arc.dxf.center.x - shift[0],
                arc.dxf.center.y - shift[1],
                arc.dxf.center.z - shift[2] if hasattr(arc.dxf.center, 'z') else -shift[2]
            )
            
            radius = arc.dxf.radius
            start_angle = math.radians(arc.dxf.start_angle)
            end_angle = math.radians(arc.dxf.end_angle)
            
            # Handle cases where end_angle < start_angle (crosses 0)
            if end_angle < start_angle:
                end_angle += 2 * math.pi
                
            # Create arc curve
            curve_data = bpy.data.curves.new(name="Arc", type='CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = self.curve_resolution
            
            # Create arc spline
            spline = curve_data.splines.new('BEZIER')
            
            # Calculate how many points to add based on the arc angle
            arc_angle = end_angle - start_angle
            num_points = max(3, int(arc_angle / (math.pi/4)) + 1)
            spline.bezier_points.add(num_points - 1)  # -1 because one point already exists
            
            # Set arc points
            for i in range(num_points):
                angle = start_angle + (i / (num_points - 1)) * arc_angle
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)
                point = spline.bezier_points[i]
                point.co = (x, y, center[2])
                point.handle_left_type = 'AUTO'
                point.handle_right_type = 'AUTO'
            
            # Create object with layer name if available
            layer = arc.dxf.layer if hasattr(arc.dxf, 'layer') else "0"
            curve_obj = bpy.data.objects.new(f"Arc_{layer}", curve_data)
            collection.objects.link(curve_obj)
            count += 1
            
        return count
    
    def import_dxf_polylines(self, modelspace, collection, shift):
        """Import POLYLINE and LWPOLYLINE entities from DXF"""
        import ezdxf
        
        polylines = list(modelspace.query('LWPOLYLINE')) + list(modelspace.query('POLYLINE'))
        count = 0
        
        if not polylines:
            return count
            
        for polyline in polylines:
            # Get the layer name if available
            layer = polyline.dxf.layer if hasattr(polyline.dxf, 'layer') else "0"
            
            # Create polyline curve
            curve_data = bpy.data.curves.new(name=f"Polyline_{layer}", type='CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = self.curve_resolution
            
            # Create spline in curve
            spline = curve_data.splines.new('POLY')
            
            # Get vertices from the polyline
            if polyline.dxftype() == 'LWPOLYLINE':
                # LWPOLYLINE is flattened to 2D
                points = list(polyline.get_points())
                
                # Add points to spline
                spline.points.add(len(points) - 1)  # -1 because one point already exists
                
                for j, point in enumerate(points):
                    # LWPOLYLINEs are 2D, so we use z=0 or shift[2]
                    spline.points[j].co = (
                        point[0] - shift[0],
                        point[1] - shift[1],
                        -shift[2],
                        1.0
                    )
                    
                # Set closed flag if polyline is closed
                spline.use_cyclic_u = polyline.closed
                
            elif polyline.dxftype() == 'POLYLINE':
                # POLYLINE with vertices
                vertices = list(polyline.vertices)
                
                # Add points to spline
                spline.points.add(len(vertices) - 1)  # -1 because one point already exists
                
                for j, vertex in enumerate(vertices):
                    # Get 3D coordinates
                    x = vertex.dxf.location.x if hasattr(vertex.dxf, 'location') else 0
                    y = vertex.dxf.location.y if hasattr(vertex.dxf, 'location') else 0
                    z = vertex.dxf.location.z if hasattr(vertex.dxf, 'location') else 0
                    
                    spline.points[j].co = (
                        x - shift[0],
                        y - shift[1],
                        z - shift[2],
                        1.0
                    )
                    
                # Set closed flag if polyline is closed
                spline.use_cyclic_u = polyline.is_closed
            
            # Create object
            curve_obj = bpy.data.objects.new(f"Polyline_{layer}", curve_data)
            collection.objects.link(curve_obj)
            count += 1
            
        return count
    
    def import_dxf_text(self, modelspace, collection, shift):
        """Import TEXT entities from DXF"""
        import ezdxf
        
        texts = list(modelspace.query('TEXT')) + list(modelspace.query('MTEXT'))
        count = 0
        
        if not texts:
            return count
            
        for text in texts:
            # Get text content
            if text.dxftype() == 'TEXT':
                content = text.dxf.text
                position = (
                    text.dxf.insert.x - shift[0],
                    text.dxf.insert.y - shift[1],
                    text.dxf.insert.z - shift[2] if hasattr(text.dxf.insert, 'z') else -shift[2]
                )
                height = text.dxf.height
                rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
            else:  # MTEXT
                content = text.text
                position = (
                    text.dxf.insert.x - shift[0],
                    text.dxf.insert.y - shift[1],
                    text.dxf.insert.z - shift[2] if hasattr(text.dxf.insert, 'z') else -shift[2]
                )
                height = text.dxf.char_height
                rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
            
            # Get the layer name if available
            layer = text.dxf.layer if hasattr(text.dxf, 'layer') else "0"
            
            # Create text object
            text_curve = bpy.data.curves.new(name=f"Text_{layer}", type='FONT')
            text_curve.body = content
            text_curve.size = height
            text_curve.align_x = 'LEFT'
            text_curve.align_y = 'BOTTOM'
            
            # Create object
            text_obj = bpy.data.objects.new(f"Text_{layer}", text_curve)
            text_obj.location = position
            text_obj.rotation_euler.z = math.radians(rotation)
            
            collection.objects.link(text_obj)
            count += 1
            
        return count

def register():
    try:
        import ezdxf
    except ImportError:
        print("Warning: 'ezdxf' module not found. DXF import may not work correctly.")
        print("Please install it via pip: pip install ezdxf")
    
    bpy.utils.register_class(OBJECT_OT_IMPORTDXF)
    bpy.utils.register_class(ImportDXF_3DSC)

def unregister():
    bpy.utils.unregister_class(ImportDXF_3DSC)
    bpy.utils.unregister_class(OBJECT_OT_IMPORTDXF)