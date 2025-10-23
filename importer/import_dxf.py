import bpy
import os
import math
import mathutils
from bpy.props import StringProperty, BoolProperty, FloatVectorProperty, EnumProperty, FloatProperty
from bpy.props import IntProperty

from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator, Panel


def check_ezdxf_installed():
    """Verifica se il modulo ezdxf è installato e accessibile da Blender"""
    try:
        import ezdxf
        # Se importiamo con successo, restituiamo True e la versione
        return True, ezdxf.__version__
    except ImportError as e:
        # Registra dettagli sull'errore di importazione
        print(f"Errore di importazione ezdxf: {str(e)}")
        return False, str(e)
    except Exception as e:
        # Gestisce altri possibili errori
        print(f"Errore con ezdxf: {str(e)}")
        return False, str(e)

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
            ('HATCHES', "Hatches", "Import HATCH entities as polygons"),
            ('TEXT', "Text", "Import TEXT entities"),
        ),
        default={'LINES', 'CIRCLES', 'ARCS', 'POLYLINES', 'HATCHES', 'TEXT'},
    ) # type: ignore
    
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
    
    # Nuove opzioni per la fusione delle linee
    merge_by_layer: BoolProperty(
        name="Merge by Layer",
        description="Merge line segments by layer to reduce object count",
        default=True,
    )
    
    merge_distance_tolerance: FloatProperty(
        name="Merge Distance Tolerance",
        description="Maximum distance between vertices to be considered for merging (in Blender units)",
        default=0.001,
        min=0.0001,
        max=1.0,
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
        
        # Sezione per le opzioni di ottimizzazione
        box = layout.box()
        box.label(text="Optimization Settings")
        box.prop(self, "merge_by_layer")
        if self.merge_by_layer:
            box.prop(self, "merge_distance_tolerance")
    
    def execute(self, context):
        # Check if ezdxf is installed
        try:
            import ezdxf
        except ImportError:
            self.report({'ERROR'}, "The 'ezdxf' module is required. Please install it from the DXF Import panel")
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

            if 'HATCHES' in self.import_entities:
                count = self.import_dxf_hatches(modelspace, collection, shift_values)
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
        
        if self.merge_by_layer:
            # Dictionary to organize lines by layer
            lines_by_layer = {}
            
            for line in lines:
                layer = line.dxf.layer if hasattr(line.dxf, 'layer') else "0"
                
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
                
                if layer not in lines_by_layer:
                    lines_by_layer[layer] = []
                
                lines_by_layer[layer].append((start, end))
            
            # Process each layer
            for layer, line_segments in lines_by_layer.items():
                # Skip empty layers
                if not line_segments:
                    continue
                
                # Merge connected segments into polylines
                polylines = self.merge_segments_into_polylines(line_segments)
                
                # Create curve objects for each polyline
                for i, vertices in enumerate(polylines):
                    if not vertices:
                        continue
                    
                    # Create curve data
                    curve_data = bpy.data.curves.new(name=f"Line_{layer}", type='CURVE')
                    curve_data.dimensions = '3D'
                    curve_data.resolution_u = self.curve_resolution
                    
                    # Create spline in curve
                    spline = curve_data.splines.new('POLY')
                    spline.points.add(len(vertices) - 1)  # -1 because one point already exists
                    
                    # Set points
                    for j, vertex in enumerate(vertices):
                        spline.points[j].co = (vertex[0], vertex[1], vertex[2], 1.0)
                    
                    # Create object
                    count_suffix = f"_{i+1}" if len(polylines) > 1 else ""
                    curve_obj = bpy.data.objects.new(f"Line_{layer}{count_suffix}", curve_data)
                    collection.objects.link(curve_obj)
                    count += 1
        else:
            # Original implementation for individual lines
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
    
    def merge_segments_into_polylines(self, line_segments):
        """
        Merge line segments into continuous polylines.
        
        Args:
            line_segments: List of tuples (start_point, end_point), where each point is a (x, y, z) tuple
        
        Returns:
            List of polylines, where each polyline is a list of points
        """
        # If no segments, return empty list
        if not line_segments:
            return []
        
        # Clone the input to avoid modifying the original
        remaining_segments = line_segments.copy()
        polylines = []
        tolerance = self.merge_distance_tolerance
        
        # Loop until all segments are processed
        while remaining_segments:
            # Start a new polyline with the first available segment
            start, end = remaining_segments.pop(0)
            current_polyline = [start, end]
            
            # Flag to indicate if we found a connecting segment in this iteration
            found_connection = True
            
            # Keep extending the polyline until no more connections can be found
            while found_connection and remaining_segments:
                found_connection = False
                last_point = current_polyline[-1]
                
                # Look for a segment that continues from the last point of our current polyline
                for i, (seg_start, seg_end) in enumerate(remaining_segments):
                    # Check if the start point of the segment is close to the last point of our polyline
                    if self.is_same_point(last_point, seg_start, tolerance):
                        # Add the end point to our polyline
                        current_polyline.append(seg_end)
                        # Remove the segment from remaining segments
                        remaining_segments.pop(i)
                        found_connection = True
                        break
                    
                    # Check if the end point of the segment is close to the last point of our polyline
                    elif self.is_same_point(last_point, seg_end, tolerance):
                        # Add the start point to our polyline
                        current_polyline.append(seg_start)
                        # Remove the segment from remaining segments
                        remaining_segments.pop(i)
                        found_connection = True
                        break
                
                # If we didn't find a continuation, also try to add segments to the start of the polyline
                if not found_connection and len(current_polyline) > 1:
                    first_point = current_polyline[0]
                    
                    for i, (seg_start, seg_end) in enumerate(remaining_segments):
                        # Check if the end point of the segment is close to the first point of our polyline
                        if self.is_same_point(first_point, seg_end, tolerance):
                            # Insert the start point at the beginning of our polyline
                            current_polyline.insert(0, seg_start)
                            # Remove the segment from remaining segments
                            remaining_segments.pop(i)
                            found_connection = True
                            break
                        
                        # Check if the start point of the segment is close to the first point of our polyline
                        elif self.is_same_point(first_point, seg_start, tolerance):
                            # Insert the end point at the beginning of our polyline
                            current_polyline.insert(0, seg_end)
                            # Remove the segment from remaining segments
                            remaining_segments.pop(i)
                            found_connection = True
                            break
            
            # Add the completed polyline to our result list
            polylines.append(current_polyline)
        
        return polylines
    
    def is_same_point(self, p1, p2, tolerance):
        """
        Check if two points are the same (within tolerance).
        
        Args:
            p1: First point as (x, y, z) tuple
            p2: Second point as (x, y, z) tuple
            tolerance: Maximum distance for points to be considered the same
            
        Returns:
            True if points are within tolerance, False otherwise
        """
        return (
            abs(p1[0] - p2[0]) < tolerance and
            abs(p1[1] - p2[1]) < tolerance and
            abs(p1[2] - p2[2]) < tolerance
        )
    
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
        
        polylines = []
        if self.merge_by_layer:
            # Organizziamo le polilinee per layer
            polylines_by_layer = {}
            
            # Aggiungiamo le LWPOLYLINE
            for polyline in modelspace.query('LWPOLYLINE'):
                layer = polyline.dxf.layer if hasattr(polyline.dxf, 'layer') else "0"
                
                # Ottieni i punti dalla polilinea
                points = []
                for point in polyline.get_points():
                    # LWPOLYLINE sono 2D, quindi utilizziamo z=0 o shift[2]
                    points.append((
                        point[0] - shift[0],
                        point[1] - shift[1],
                        -shift[2]
                    ))
                
                if layer not in polylines_by_layer:
                    polylines_by_layer[layer] = []
                
                polylines_by_layer[layer].append({
                    'points': points,
                    'closed': polyline.closed
                })
            
            # Aggiungiamo le POLYLINE
            for polyline in modelspace.query('POLYLINE'):
                layer = polyline.dxf.layer if hasattr(polyline.dxf, 'layer') else "0"
                
                # Ottieni i vertici dalla polilinea
                vertices = list(polyline.vertices)
                points = []
                
                for vertex in vertices:
                    # Ottieni le coordinate 3D
                    x = vertex.dxf.location.x if hasattr(vertex.dxf, 'location') else 0
                    y = vertex.dxf.location.y if hasattr(vertex.dxf, 'location') else 0
                    z = vertex.dxf.location.z if hasattr(vertex.dxf, 'location') else 0
                    
                    points.append((
                        x - shift[0],
                        y - shift[1],
                        z - shift[2]
                    ))
                
                if layer not in polylines_by_layer:
                    polylines_by_layer[layer] = []
                
                polylines_by_layer[layer].append({
                    'points': points,
                    'closed': polyline.is_closed
                })
            
            # Crea oggetti per ogni layer
            count = 0
            for layer, layer_polylines in polylines_by_layer.items():
                if not layer_polylines:
                    continue
                
                # Crea curve per ogni polilinea nel layer
                for i, poly_data in enumerate(layer_polylines):
                    points = poly_data['points']
                    if not points:
                        continue
                    
                    # Crea dati della curva
                    curve_data = bpy.data.curves.new(name=f"Polyline_{layer}", type='CURVE')
                    curve_data.dimensions = '3D'
                    curve_data.resolution_u = self.curve_resolution
                    
                    # Crea spline nella curva
                    spline = curve_data.splines.new('POLY')
                    
                    # Aggiungi punti alla spline
                    spline.points.add(len(points) - 1)  # -1 perché un punto esiste già
                    for j, point in enumerate(points):
                        spline.points[j].co = (point[0], point[1], point[2], 1.0)
                    
                    # Imposta flag di chiusura
                    spline.use_cyclic_u = poly_data['closed']
                    
                    # Crea oggetto
                    name_suffix = f"_{i+1}" if len(layer_polylines) > 1 else ""
                    curve_obj = bpy.data.objects.new(f"Polyline_{layer}{name_suffix}", curve_data)
                    collection.objects.link(curve_obj)
                    count += 1
            
            return count
        
        else:
            # Implementazione originale per polilinee individuali
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
        import ezdxf # type: ignore
        
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

    def import_dxf_hatches(self, modelspace, collection, shift):
        """Import HATCH entities from DXF as polygon meshes"""
        import ezdxf # type: ignore
        import bmesh # type: ignore
        from mathutils import Vector # type: ignore
        
        hatches = modelspace.query('HATCH')
        count = 0
        
        if not hatches:
            return count
        
        for hatch in hatches:
            try:
                # Get layer name
                layer = hatch.dxf.layer if hasattr(hatch.dxf, 'layer') else "0"
                
                # Get all boundary paths
                paths = hatch.paths
                
                if not paths:
                    continue
                
                # Create a new mesh for this hatch
                mesh = bpy.data.meshes.new(name=f"Hatch_{layer}")
                obj = bpy.data.objects.new(f"Hatch_{layer}_{count}", mesh)
                
                # Create bmesh to build the geometry
                bm = bmesh.new()
                
                all_vertices = []
                all_faces = []
                vertex_offset = 0
                
                # Process each boundary path
                for path in paths:
                    vertices = []
                    
                    # Get edges from the path
                    if hasattr(path, 'edges'):
                        for edge in path.edges:
                            # LINE edge
                            if edge.EDGE_TYPE == "LineEdge":
                                start = edge.start
                                vertices.append((
                                    start[0] - shift[0],
                                    start[1] - shift[1],
                                    -shift[2] if len(start) < 3 else start[2] - shift[2]
                                ))
                            
                            # ARC edge
                            elif edge.EDGE_TYPE == "ArcEdge":
                                # Sample points along the arc
                                center = edge.center
                                radius = edge.radius
                                start_angle = math.radians(edge.start_angle)
                                end_angle = math.radians(edge.end_angle)
                                
                                # Determine number of segments based on arc length
                                arc_length = abs(end_angle - start_angle)
                                num_segments = max(3, int(arc_length * radius / 0.5))
                                
                                is_ccw = edge.is_counter_clockwise
                                if not is_ccw and end_angle < start_angle:
                                    end_angle += 2 * math.pi
                                elif is_ccw and start_angle < end_angle:
                                    start_angle += 2 * math.pi
                                
                                for i in range(num_segments):
                                    t = i / num_segments
                                    if is_ccw:
                                        angle = start_angle - t * (start_angle - end_angle)
                                    else:
                                        angle = start_angle + t * (end_angle - start_angle)
                                    
                                    x = center[0] + radius * math.cos(angle)
                                    y = center[1] + radius * math.sin(angle)
                                    z = -shift[2] if len(center) < 3 else center[2] - shift[2]
                                    
                                    vertices.append((
                                        x - shift[0],
                                        y - shift[1],
                                        z
                                    ))
                            
                            # ELLIPSE edge
                            elif edge.EDGE_TYPE == "EllipseEdge":
                                # Sample points along the ellipse
                                center = edge.center
                                major_axis = edge.major_axis
                                ratio = edge.ratio
                                start_angle = math.radians(edge.start_angle)
                                end_angle = math.radians(edge.end_angle)
                                
                                # Calculate minor axis length
                                major_length = math.sqrt(major_axis[0]**2 + major_axis[1]**2)
                                minor_length = major_length * ratio
                                
                                # Rotation angle of the ellipse
                                rotation = math.atan2(major_axis[1], major_axis[0])
                                
                                num_segments = max(8, int(abs(end_angle - start_angle) * 10))
                                
                                for i in range(num_segments):
                                    t = i / num_segments
                                    angle = start_angle + t * (end_angle - start_angle)
                                    
                                    # Parametric ellipse equation
                                    x_local = major_length * math.cos(angle)
                                    y_local = minor_length * math.sin(angle)
                                    
                                    # Rotate and translate
                                    x = center[0] + x_local * math.cos(rotation) - y_local * math.sin(rotation)
                                    y = center[1] + x_local * math.sin(rotation) + y_local * math.cos(rotation)
                                    z = -shift[2] if len(center) < 3 else center[2] - shift[2]
                                    
                                    vertices.append((
                                        x - shift[0],
                                        y - shift[1],
                                        z
                                    ))
                            
                            # SPLINE edge
                            elif edge.EDGE_TYPE == "SplineEdge":
                                # Get control points and approximate with line segments
                                if hasattr(edge, 'control_points'):
                                    for point in edge.control_points:
                                        vertices.append((
                                            point[0] - shift[0],
                                            point[1] - shift[1],
                                            -shift[2] if len(point) < 3 else point[2] - shift[2]
                                        ))
                    
                    # If we have vertices, create face
                    if len(vertices) >= 3:
                        # Remove duplicate consecutive vertices
                        cleaned_vertices = [vertices[0]]
                        for i in range(1, len(vertices)):
                            if not self.points_are_close(vertices[i], cleaned_vertices[-1], 0.0001):
                                cleaned_vertices.append(vertices[i])
                        
                        # Close the loop if needed
                        if len(cleaned_vertices) >= 3 and not self.points_are_close(
                            cleaned_vertices[0], cleaned_vertices[-1], 0.0001
                        ):
                            cleaned_vertices.append(cleaned_vertices[0])
                        
                        if len(cleaned_vertices) >= 3:
                            # Add vertices to bmesh
                            face_verts = []
                            for v in cleaned_vertices[:-1]:  # Exclude last duplicate vertex
                                vert = bm.verts.new(v)
                                face_verts.append(vert)
                            
                            # Create face if we have enough vertices
                            if len(face_verts) >= 3:
                                try:
                                    bm.faces.new(face_verts)
                                except ValueError:
                                    # Face already exists or invalid, skip
                                    pass
                
                # Update bmesh and create mesh
                bm.to_mesh(mesh)
                bm.free()
                
                # Only add object if it has geometry
                if len(mesh.vertices) > 0:
                    collection.objects.link(obj)
                    count += 1
                else:
                    # Clean up empty mesh
                    bpy.data.objects.remove(obj)
                    bpy.data.meshes.remove(mesh)
                    
            except Exception as e:
                print(f"Error importing hatch: {str(e)}")
                continue
        
        return count

class OBJECT_OT_reload_python_modules(Operator):
    """Reload Python modules path to detect installed packages"""
    bl_idname = "import_dxf.reload_modules"
    bl_label = "Reload Python Modules"
    
    def execute(self, context):
        try:
            import site
            import sys
            import importlib
            
            # Ricarica i percorsi dei pacchetti sito
            site.main()
            
            # Ricarica il modulo se è già stato caricato
            if "ezdxf" in sys.modules:
                importlib.reload(sys.modules["ezdxf"])
                
            # Tenta di importare il modulo
            try:
                import ezdxf
                self.report({'INFO'}, f"ezdxf module loaded successfully - version: {ezdxf.__version__}")
            except ImportError as e:
                self.report({'WARNING'}, f"Could not load ezdxf: {str(e)}")
            
            # Stampa i percorsi Python per debug
            print("Python paths:")
            for p in sys.path:
                print(f"  {p}")
                
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error reloading Python paths: {str(e)}")
            return {'CANCELLED'}

class DXF_PT_ImportPanel(Panel):
    """Panel for importing DXF files with coordinate shift support"""
    bl_label = "DXF Import"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3DSC"
    bl_parent_id = "VIEW3D_PT_Import_ToolBar"  # Collegamento al pannello Importers esistente
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return True
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Test più rigoroso per ezdxf
        is_installed, version_info = check_ezdxf_installed()
        
        # Mostra il pulsante per importare DXF se ezdxf è installato
        if is_installed:
            row = layout.row(align=True)
            row.operator("import_dxf.button", icon="IMPORT", text="Import DXF File")
            row = layout.row()
            row.label(text=f"ezdxf version: {version_info}")
            
            # Mostra le impostazioni di shift delle coordinate
            box = layout.box()
            box.label(text="Coordinate Shift (from the SHIFT panel):")
            row = box.row()
            row.label(text=f"X: {scene.BL_x_shift}")
            row = box.row()
            row.label(text=f"Y: {scene.BL_y_shift}")
            row = box.row()
            row.label(text=f"Z: {scene.BL_z_shift}")
        else:
            # Se ezdxf non è installato, mostra un messaggio e un pulsante per installarlo
            box = layout.box()
            box.label(text="Module 'ezdxf' is not detected", icon="ERROR")
            box.label(text=f"Error: {version_info}")
            
            # Aggiungi un pulsante di ricarica per rigenerare i path dopo l'installazione
            row = layout.row(align=True)
            row.operator("import_dxf.reload_modules", icon="FILE_REFRESH", text="Reload Python Paths")
            
            # Bottone per installare
            row = layout.row(align=True)
            op = row.operator("install_3dsc_missing.modules", icon="IMPORT", text="Install ezdxf module")
            op.is_install = True
            op.list_modules_to_install = "ezdxf"
            
            # Suggerimento per riavviare Blender
            box = layout.box()
            box.label(text="Tip: After installation, you may need")
            box.label(text="to restart Blender for changes to take effect")


# Registra e deregistra le classi

def register():
    is_installed, version_info = check_ezdxf_installed()
    if is_installed:
        print(f"Module 'ezdxf' is installed - version: {version_info}")
    else:
        print(f"Module 'ezdxf' is not available: {version_info}")
        print("Please install it via the UI button or restart Blender after installation")
 
    bpy.utils.register_class(OBJECT_OT_IMPORTDXF)
    bpy.utils.register_class(ImportDXF_3DSC)
    bpy.utils.register_class(DXF_PT_ImportPanel)
    bpy.utils.register_class(OBJECT_OT_reload_python_modules)

def unregister():
    bpy.utils.unregister_class(DXF_PT_ImportPanel)
    bpy.utils.unregister_class(ImportDXF_3DSC)
    bpy.utils.unregister_class(OBJECT_OT_IMPORTDXF)
    bpy.utils.unregister_class(OBJECT_OT_reload_python_modules)