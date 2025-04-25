"""
Utility functions for METS metadata exporter.
Contains helper functions for calculating metadata, checksums, etc.
"""

import bpy
import os
import hashlib
import datetime
import math
import bmesh
from mathutils import Vector

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------

def calculate_checksum(file_path, algorithm='MD5'):
    """Calculate checksum for a file."""
    if not os.path.exists(file_path):
        return None
    
    hash_obj = hashlib.md5()  # Default to MD5
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()

def get_file_size(file_path):
    """Get file size in bytes."""
    if os.path.exists(file_path):
        return os.path.getsize(file_path)
    return 0

def create_folder_if_not_exists(folder_path):
    """Create folder if it doesn't exist."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path

def format_datetime(dt=None):
    """Format datetime in ISO 8601 format."""
    if dt is None:
        dt = datetime.datetime.now()
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def calculate_uv_efficiency(obj):
    """Calculate UV mapping efficiency for the given object."""
    if not obj or obj.type != 'MESH' or not obj.data.uv_layers:
        return 0.0
    
    # Get the active UV layer
    uv_layer = obj.data.uv_layers.active.data
    
    # Calculate used UV space
    min_u, min_v = 1.0, 1.0
    max_u, max_v = 0.0, 0.0
    
    for poly in obj.data.polygons:
        for loop_idx in poly.loop_indices:
            u, v = uv_layer[loop_idx].uv
            min_u = min(min_u, u)
            min_v = min(min_v, v)
            max_u = max(max_u, u)
            max_v = max(max_v, v)
    
    # Calculate UV area (assuming UV space is 0-1)
    used_uv_area = (max_u - min_u) * (max_v - min_v)
    total_uv_area = 1.0
    
    # Calculate efficiency
    if total_uv_area > 0:
        return min(used_uv_area / total_uv_area, 1.0)
    return 0.0

def calculate_texel_density(obj, image_width=2048, image_height=2048):
    """Calculate approximate texel density for the object."""
    if not obj or obj.type != 'MESH' or not obj.data.uv_layers:
        return 0.0
    
    # Get mesh surface area in 3D space
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    mesh_area = sum(f.calc_area() for f in bm.faces)
    bm.free()
    
    if mesh_area <= 0:
        return 0.0
    
    # Calculate UV efficiency
    uv_efficiency = calculate_uv_efficiency(obj)
    
    # Calculate texels per square meter
    uv_area_used = uv_efficiency
    texel_count = image_width * image_height * uv_area_used
    texel_density = texel_count / mesh_area
    
    return texel_density

def get_material_and_texture_info(obj):
    """Extract material and texture information from object."""
    result = {
        'material_count': 0,
        'texture_count': 0,
        'materials': []
    }
    
    # Process materials
    for slot in obj.material_slots:
        if not slot.material:
            continue
        
        mat = slot.material
        result['material_count'] += 1
        
        # Create material entry
        mat_entry = {
            'id': f"mat_{result['material_count']:02d}",
            'name': mat.name,
            'textures': []
        }
        
        # Process material textures
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    tex_type = "diffuse"  # Default texture type
                    
                    # Try to determine texture type from node connections
                    for output in node.outputs:
                        for link in output.links:
                            if link.to_socket.name in ['Base Color', 'Color']:
                                tex_type = "diffuse"
                            elif link.to_socket.name in ['Normal', 'Normal Map']:
                                tex_type = "normal"
                            elif link.to_socket.name in ['Roughness']:
                                tex_type = "roughness"
                            elif link.to_socket.name in ['Metallic']:
                                tex_type = "metallic"
                            elif link.to_socket.name in ['Displacement']:
                                tex_type = "displacement"
                    
                    mat_entry['textures'].append({
                        'type': tex_type,
                        'name': node.image.name,
                        'filepath': bpy.path.abspath(node.image.filepath)
                    })
                    result['texture_count'] += 1
        
        result['materials'].append(mat_entry)
    
    return result

def get_acquisition_method_from_name(obj_name):
    """Try to determine acquisition method from object name (simple heuristic)."""
    name_lower = obj_name.lower()
    
    if any(method in name_lower for method in ['photo', 'photogram', 'sfm', 'mvs']):
        return 'Fotogrammetria'
    elif any(method in name_lower for method in ['laser', 'scan', 'lidar']):
        return 'Scansione Laser'
    elif any(method in name_lower for method in ['struct', 'light']):
        return 'Structured Light'
    elif any(method in name_lower for method in ['ct', 'tac']):
        return 'CT Scan'
    elif any(method in name_lower for method in ['manual', 'model']):
        return 'Modellazione Manuale'
    
    # Default
    return 'Fotogrammetria'

def get_obj_dimensions(obj):
    """Get object dimensions in local space, accounting for scale."""
    if not obj:
        return (0, 0, 0)
    
    # Get dimensions accounting for scale
    dimensions = obj.dimensions
    
    # Convert to cm (Blender uses meters)
    dimensions_cm = [dim * 100 for dim in dimensions]
    
    # Return width, height, depth (reordered from Blender's x, y, z)
    return (dimensions_cm[0], dimensions_cm[2], dimensions_cm[1])

def get_obj_bounds(obj):
    """Get object bounding box min/max coordinates in world space."""
    if not obj:
        return None
    
    # Get the world space bounding box coordinates
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    
    # Initialize min/max values
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    # Find min/max for each axis
    for corner in bbox_corners:
        min_x = min(min_x, corner.x)
        min_y = min(min_y, corner.y)
        min_z = min(min_z, corner.z)
        max_x = max(max_x, corner.x)
        max_y = max(max_y, corner.y)
        max_z = max(max_z, corner.z)
    
    # Return bounds dictionary
    return {
        'min_x': min_x,
        'max_x': max_x,
        'min_y': min_y,
        'max_y': max_y,
        'min_z': min_z,
        'max_z': max_z
    }

def get_mesh_statistics(obj):
    """Get mesh statistics for an object."""
    if not obj or obj.type != 'MESH':
        return None
    
    mesh = obj.data
    
    # Basic counts
    vertex_count = len(mesh.vertices)
    face_count = len(mesh.polygons)
    
    # Calculate triangle count (accounting for n-gons)
    triangle_count = 0
    for poly in mesh.polygons:
        if len(poly.vertices) >= 3:
            triangle_count += len(poly.vertices) - 2
    
    # Calculate surface area
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.transform(obj.matrix_world)
    area = sum(f.calc_area() for f in bm.faces)
    bm.free()
    
    # Calculate triangle density
    if area > 0:
        triangles_per_sqm = triangle_count / area
    else:
        triangles_per_sqm = 0
    
    # Calculate UV data
    uv_count = 0
    uv_efficiency = 0
    if mesh.uv_layers:
        uv_count = len(mesh.uv_layers.active.data)
        uv_efficiency = calculate_uv_efficiency(obj)
    
    # Calculate normal count
    normal_count = vertex_count  # In Blender, normals are typically per-vertex
    
    return {
        'vertex_count': vertex_count,
        'face_count': face_count,
        'triangle_count': triangle_count,
        'normal_count': normal_count,
        'uv_count': uv_count,
        'uv_efficiency': uv_efficiency, 
        'surface_area': area,
        'triangles_per_sqm': triangles_per_sqm
    }

def estimate_mesh_accuracy(obj_name):
    """Estimate mesh accuracy based on acquisition method in name."""
    # This is a heuristic estimation - in real scenarios, you would use more precise methods
    name_lower = obj_name.lower()
    
    if any(method in name_lower for method in ['laser', 'lidar']):
        return 0.1  # 0.1mm for laser scanning
    elif any(method in name_lower for method in ['photo', 'sfm', 'mvs']):
        return 0.5  # 0.5mm for photogrammetry
    elif any(method in name_lower for method in ['struct', 'light']):
        return 0.1  # 0.1mm for structured light
    elif any(method in name_lower for method in ['ct']):
        return 0.05  # 0.05mm for CT
    else:
        return 1.0  # 1mm default

def get_mesh_point_density(obj):
    """Calculate point density (vertices per sq cm)."""
    stats = get_mesh_statistics(obj)
    if stats is None or stats['surface_area'] <= 0:
        return 0.0
    
    # Convert area to sq cm and calculate density
    area_in_sqcm = stats['surface_area'] * 10000  # m² to cm²
    return stats['vertex_count'] / area_in_sqcm

def guess_format_from_name(obj_name):
    """Try to guess format from object name."""
    name_lower = obj_name.lower()
    
    if '.obj' in name_lower:
        return 'model/obj'
    elif '.fbx' in name_lower:
        return 'model/fbx'
    elif '.ply' in name_lower:
        return 'model/ply'
    elif '.stl' in name_lower:
        return 'model/stl'
    elif '.gltf' in name_lower:
        return 'model/gltf+json'
    elif '.glb' in name_lower:
        return 'model/gltf-binary'
    elif '.3ds' in name_lower:
        return 'model/3ds'
    else:
        return 'model/obj'  # Default

def get_format_category(format_name):
    """Determine format category based on format name."""
    interoperable_formats = [
        'model/obj', 'model/ply', 'model/stl', 'model/gltf+json', 
        'model/gltf-binary', 'model/x3d+xml'
    ]
    
    if format_name in interoperable_formats:
        return 'interoperable'
    else:
        return 'proprietary'

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

def register():
    pass  # No registration needed for utility functions

def unregister():
    pass

if __name__ == "__main__":
    register()