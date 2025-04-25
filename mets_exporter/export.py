"""
METS XML export functionality.
Handles the generation of METS XML files from object metadata.
"""

import bpy
from bpy.types import Operator
import os
import uuid
import xml.dom.minidom
import xml.etree.ElementTree as ET

from . import utils

# -----------------------------------------------------------------------------
# METS XML Export Operator
# -----------------------------------------------------------------------------

class METS_OT_ExportMETS(Operator):
    """Export METS XML file with 3D model metadata."""
    bl_idname = "mets.export_mets"
    bl_label = "Export METS XML"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        scene = context.scene
        export_settings = scene.mets_export_settings
        
        # Get objects to export
        objects = []
        if export_settings.use_selection:
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        elif export_settings.object_name:
            obj = bpy.data.objects.get(export_settings.object_name)
            if obj and obj.type == 'MESH':
                objects = [obj]
        elif context.active_object and context.active_object.type == 'MESH':
            objects = [context.active_object]
        
        if not objects:
            self.report({'ERROR'}, "No valid objects selected for export")
            return {'CANCELLED'}
        
        # Ensure the export path exists
        export_path = bpy.path.abspath(export_settings.export_path)
        os.makedirs(export_path, exist_ok=True)
        
        # Full path to output file
        output_file = os.path.join(export_path, export_settings.file_name)
        
        # Generate the METS XML
        try:
            self.generate_mets_xml(context, objects, output_file)
            self.report({'INFO'}, f"METS XML exported to {output_file}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error exporting METS XML: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
        
    def generate_mets_xml(self, context, objects, output_file):
        """Generate METS XML file for the given objects."""
        scene = context.scene
        export_settings = scene.mets_export_settings
        
        # Creiamo il documento XML con i namespace definiti correttamente
        ET.register_namespace('', "http://www.loc.gov/METS/")
        ET.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")
        ET.register_namespace('dc', "http://purl.org/dc/elements/1.1/")
        ET.register_namespace('dct', "http://purl.org/dc/terms/")
        ET.register_namespace('mix', "http://www.loc.gov/mix/v20")
        ET.register_namespace('mods', "http://www.loc.gov/mods/v3")
        ET.register_namespace('metsrights', "http://cosimo.stanford.edu/sdr/metsrights/")
        ET.register_namespace('xlink', "http://www.w3.org/1999/xlink")
        ET.register_namespace('ext3d', "http://example.org/ext3d/")
        ET.register_namespace('premis', "http://www.loc.gov/premis/v3")
        
        # Crea l'elemento root con l'attributo dello schema corretto
        mets = ET.Element("{http://www.loc.gov/METS/}mets")
        mets.set("PROFILE", export_settings.mets_profile)
        mets.set("OBJID", export_settings.mets_objid)
        mets.set("xsi:schemaLocation", "http://www.loc.gov/METS/ http://www.loc.gov/standards/mets/mets.xsd "
                "http://www.loc.gov/mix/v20 https://www.loc.gov/standards/mix/mix20/mix20.xsd "
                "http://www.loc.gov/mods/v3 http://www.loc.gov/mods/v3/mods-3-8.xsd "
                "http://cosimo.stanford.edu/sdr/metsrights/ https://www.loc.gov/standards/rights/METSRights.xsd")

        # Add metsHdr
        self.add_mets_header(mets, context)
        
        # Add dmdSec for each object
        dmd_id_counter = 1
        dmd_id_map = {}  # Map objects to their dmdSec IDs
        
        for obj in objects:
            dmd_id = f"DMD_{dmd_id_counter:02d}"
            dmd_id_map[obj] = dmd_id
            self.add_descriptive_metadata(mets, context, obj, dmd_id)
            dmd_id_counter += 1
        
        # Add amdSec with techMD, rightsMD, sourceMD, and digiprovMD
        amd_sec = ET.SubElement(mets, "{http://www.loc.gov/METS/}amdSec")
        tech_id_map = {}  # Map objects to their techMD IDs
        
        # Add techMD for each object
        tech_id_counter = 1
        for obj in objects:
            tech_id = f"TMD_3D_{tech_id_counter:02d}"
            tech_id_map[obj] = tech_id
            self.add_technical_metadata(amd_sec, context, obj, tech_id)
            tech_id_counter += 1
        
        # Add rights metadata
        self.add_rights_metadata(amd_sec, context)
        
        # Add source metadata
        self.add_source_metadata(amd_sec, context)
        
        # Add digital provenance metadata
        self.add_digiprov_metadata(amd_sec, context, objects)
        
        # Add fileSec
        file_sec = ET.SubElement(mets, "{http://www.loc.gov/METS/}fileSec")
        self.add_file_section(file_sec, context, objects, tech_id_map)
        
        # Add structMap (physical)
        struct_map_phys = ET.SubElement(mets, "{http://www.loc.gov/METS/}structMap")
        struct_map_phys.set("TYPE", "PHYSICAL")
        self.add_physical_struct_map(struct_map_phys, context, objects)
        
        # Add structMap (logical)
        struct_map_log = ET.SubElement(mets, "{http://www.loc.gov/METS/}structMap")
        struct_map_log.set("TYPE", "LOGICAL")
        self.add_logical_struct_map(struct_map_log, context, objects)
        
        # Add structLink
        struct_link = ET.SubElement(mets, "{http://www.loc.gov/METS/}structLink")
        self.add_struct_links(struct_link, context)
        
        # Add behaviorSec
        behavior_sec = ET.SubElement(mets, "{http://www.loc.gov/METS/}behaviorSec")
        behavior_sec.set("ID", "BHVR_3D")
        self.add_behaviors(behavior_sec, context)
        
        # Format the XML with pretty indentation
        rough_string = ET.tostring(mets, 'utf-8')

        try:
            reparsed = xml.dom.minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
        except Exception as e:
            # In caso di errore, scrivi l'XML grezzo
            print(f"Error formatting XML: {str(e)}")
            pretty_xml = rough_string.decode('utf-8')
        
        # Write the formatted XML to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
    
    def add_mets_header(self, mets, context):
        """Add metsHdr element to the METS document."""
        mets_hdr = ET.SubElement(mets, "{http://www.loc.gov/METS/}metsHdr")
        mets_hdr.set("CREATEDATE", utils.format_datetime())
        mets_hdr.set("LASTMODDATE", utils.format_datetime())
        
        # Creator agent (organization)
        agent = ET.SubElement(mets_hdr, "{http://www.loc.gov/METS/}agent")
        agent.set("ROLE", "CREATOR")
        agent.set("TYPE", "ORGANIZATION")
        name = ET.SubElement(agent, "{http://www.loc.gov/METS/}name")
        name.text = "3D Survey Collection"
        
        # Editor agent (individual)
        agent = ET.SubElement(mets_hdr, "{http://www.loc.gov/METS/}agent")
        agent.set("ROLE", "EDITOR")
        agent.set("TYPE", "INDIVIDUAL")
        name = ET.SubElement(agent, "{http://www.loc.gov/METS/}name")
        name.text = context.scene.mets_technical.operator or "3DSC User"
        
        # Digitizer agent (organization)
        agent = ET.SubElement(mets_hdr, "{http://www.loc.gov/METS/}agent")
        agent.set("ROLE", "DIGITIZER")
        agent.set("TYPE", "ORGANIZATION")
        name = ET.SubElement(agent, "{http://www.loc.gov/METS/}name")
        name.text = "3D Survey Collection User"
        
        # Document ID
        doc_id = ET.SubElement(mets_hdr, "{http://www.loc.gov/METS/}metsDocumentID")
        doc_id.text = f"METS-3DSC-{context.scene.mets_export_settings.mets_objid}-{utils.format_datetime()[:10]}"
    
    def add_descriptive_metadata(self, mets, context, obj, dmd_id):
        """Add descriptive metadata section for an object."""
        dmd_sec = ET.SubElement(mets, "{http://www.loc.gov/METS/}dmdSec")
        dmd_sec.set("ID", dmd_id)
        
        # DC metadata
        md_wrap = ET.SubElement(dmd_sec, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap.set("MDTYPE", "DC")
        xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
        
        # Get metadata from object custom properties if available, otherwise use scene settings
        ident_props = context.scene.mets_identification
        
        # Title
        dc_title = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}title")
        dc_title.text = obj.get('title', ident_props.title) or obj.name
        
        # Creator
        dc_creator = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}creator")
        dc_creator.text = obj.get('creator', ident_props.creator) or "Unknown"
        
        # Date
        dc_date = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}date")
        dc_date.text = obj.get('date', ident_props.date) or utils.format_datetime()[:10]
        
        # Description
        dc_description = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}description")
        dc_description.text = obj.get('description', ident_props.description) or f"3D model of {obj.name}"
        
        # Subject
        dc_subject = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}subject")
        dc_subject.text = obj.get('subject', ident_props.subject) or "3D model"
        
        # Type
        dc_type = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}type")
        dc_type.text = obj.get('type', ident_props.type) or "Digital 3D Model"
        
        # Format
        dc_format = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}format")
        dc_format.text = obj.get('format', ident_props.format) or "3D Model"
        
        # Identifier
        dc_identifier = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}identifier")
        dc_identifier.text = obj.get('identifier', ident_props.identifier) or f"3DSC-{obj.name}"
        
        # Relation
        dc_relation = ET.SubElement(xml_data, "{http://purl.org/dc/elements/1.1/}relation")
        dc_relation.text = obj.get('relation', ident_props.relation) or "3D Survey Collection"
        
        # Add ext3d:modelMetadata section
        self.add_ext3d_model_metadata(dmd_sec, context, obj)
    
    def add_ext3d_model_metadata(self, dmd_sec, context, obj):
        """Add ext3d:modelMetadata section."""
        md_wrap = ET.SubElement(dmd_sec, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap.set("MDTYPE", "OTHER")
        md_wrap.set("OTHERMDTYPE", "3D_MODEL_METADATA")
        xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
        
        model_metadata = ET.SubElement(xml_data, "{http://example.org/ext3d/}modelMetadata")
        
        # Dimensions
        dimensions = ET.SubElement(model_metadata, "{http://example.org/ext3d/}dimensions")
        
        # Get dimensions in cm
        width, height, depth = utils.get_obj_dimensions(obj)
        
        width_elem = ET.SubElement(dimensions, "{http://example.org/ext3d/}width")
        width_elem.set("unit", "cm")
        width_elem.text = f"{width:.1f}"
        
        height_elem = ET.SubElement(dimensions, "{http://example.org/ext3d/}height")
        height_elem.set("unit", "cm")
        height_elem.text = f"{height:.1f}"
        
        depth_elem = ET.SubElement(dimensions, "{http://example.org/ext3d/}depth")
        depth_elem.set("unit", "cm")
        depth_elem.text = f"{depth:.1f}"
        
        # Resolution (vertex and polygon count)
        resolution = ET.SubElement(model_metadata, "{http://example.org/ext3d/}resolution")
        
        stats = utils.get_mesh_statistics(obj)
        
        vertices = ET.SubElement(resolution, "{http://example.org/ext3d/}vertices")
        vertices.text = str(stats['vertex_count'])
        
        polygons = ET.SubElement(resolution, "{http://example.org/ext3d/}polygons")
        polygons.text = str(stats['face_count'])
        
        # Scale
        scale = ET.SubElement(model_metadata, "{http://example.org/ext3d/}scale")
        scale.set("unit", "cm")
        scale.text = "1:1"
        
        # Modeling method
        method = ET.SubElement(model_metadata, "{http://example.org/ext3d/}modellingMethod")
        method.text = obj.get('acquisition_method', context.scene.mets_technical.acquisition_method) or "Fotogrammetria"
    
    def add_technical_metadata(self, amd_sec, context, obj, tech_id):
        """Add technical metadata for a 3D model."""
        tech_md = ET.SubElement(amd_sec, "{http://www.loc.gov/METS/}techMD")
        tech_md.set("ID", tech_id)
        
        md_wrap = ET.SubElement(tech_md, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap.set("MDTYPE", "OTHER")
        md_wrap.set("OTHERMDTYPE", "3D_TECHNICAL")
        xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
        
        technical_3d = ET.SubElement(xml_data, "{http://example.org/ext3d/}technical3D")
        
        # Object Information
        obj_info = ET.SubElement(technical_3d, "{http://example.org/ext3d/}objectInformation")
        
        # Format name
        format_name = ET.SubElement(obj_info, "{http://example.org/ext3d/}formatName")
        format_name.text = utils.guess_format_from_name(obj.name)
        
        # Format category
        format_category = ET.SubElement(obj_info, "{http://example.org/ext3d/}formatCategory")
        format_category.text = utils.get_format_category(format_name.text)
        
        # Format version
        format_version = ET.SubElement(obj_info, "{http://example.org/ext3d/}formatVersion")
        format_version.text = "4.0" if format_name.text == "model/obj" else "1.0"
        
        # Software
        software = ET.SubElement(obj_info, "{http://example.org/ext3d/}software")
        software.text = obj.get('software', context.scene.mets_technical.software) or "Blender"
        
        # Software version
        software_version = ET.SubElement(obj_info, "{http://example.org/ext3d/}softwareVersion")
        software_version.text = obj.get('software_version', context.scene.mets_technical.software_version) or bpy.app.version_string
        
        # Date created
        date_created = ET.SubElement(obj_info, "{http://example.org/ext3d/}dateCreated")
        date_created.text = utils.format_datetime()
        
        # Geometry Information
        geom_info = ET.SubElement(technical_3d, "{http://example.org/ext3d/}geometryInformation")
        
        stats = utils.get_mesh_statistics(obj)
        
        # Vertex count
        vertex_count = ET.SubElement(geom_info, "{http://example.org/ext3d/}vertexCount")
        vertex_count.text = str(stats['vertex_count'])
        
        # Face count
        face_count = ET.SubElement(geom_info, "{http://example.org/ext3d/}faceCount")
        face_count.text = str(stats['face_count'])
        
        # Normal count
        normal_count = ET.SubElement(geom_info, "{http://example.org/ext3d/}normalCount")
        normal_count.text = str(stats['normal_count'])
        
        # UV count
        uv_count = ET.SubElement(geom_info, "{http://example.org/ext3d/}uvCount")
        uv_count.text = str(stats['uv_count'])
        
        # Point density
        point_density = ET.SubElement(geom_info, "{http://example.org/ext3d/}pointDensity")
        point_density.set("unit", "points/cm2")
        point_density.text = f"{utils.get_mesh_point_density(obj):.2f}"
        
        # Accuracy
        accuracy = ET.SubElement(geom_info, "{http://example.org/ext3d/}accuracy")
        accuracy.set("unit", "mm")
        accuracy.text = f"{utils.estimate_mesh_accuracy(obj.name):.2f}"
        
        # Bounding box
        bounds = utils.get_obj_bounds(obj)
        if bounds:
            bbox = ET.SubElement(geom_info, "{http://example.org/ext3d/}boundingBox")
            
            min_x = ET.SubElement(bbox, "{http://example.org/ext3d/}minX")
            min_x.text = f"{bounds['min_x']:.2f}"
            
            max_x = ET.SubElement(bbox, "{http://example.org/ext3d/}maxX")
            max_x.text = f"{bounds['max_x']:.2f}"
            
            min_y = ET.SubElement(bbox, "{http://example.org/ext3d/}minY")
            min_y.text = f"{bounds['min_y']:.2f}"
            
            max_y = ET.SubElement(bbox, "{http://example.org/ext3d/}maxY")
            max_y.text = f"{bounds['max_y']:.2f}"
            
            min_z = ET.SubElement(bbox, "{http://example.org/ext3d/}minZ")
            min_z.text = f"{bounds['min_z']:.2f}"
            
            max_z = ET.SubElement(bbox, "{http://example.org/ext3d/}maxZ")
            max_z.text = f"{bounds['max_z']:.2f}"
        
        # Scale
        scale = ET.SubElement(geom_info, "{http://example.org/ext3d/}scale")
        scale.set("unit", "cm")
        scale.text = "1:1"
        
        # Material Information
        mat_info = utils.get_material_and_texture_info(obj)
        if mat_info['material_count'] > 0:
            material_info = ET.SubElement(technical_3d, "{http://example.org/ext3d/}materialInformation")
            
            material_count = ET.SubElement(material_info, "{http://example.org/ext3d/}materialCount")
            material_count.text = str(mat_info['material_count'])
            
            texture_count = ET.SubElement(material_info, "{http://example.org/ext3d/}textureCount")
            texture_count.text = str(mat_info['texture_count'])
            
            # Add materials
            for mat in mat_info['materials']:
                material = ET.SubElement(material_info, "{http://example.org/ext3d/}material")
                material.set("id", mat['id'])
                
                name = ET.SubElement(material, "{http://example.org/ext3d/}name")
                name.text = mat['name']
                
                # Add textures
                for tex in mat['textures']:
                    texture = ET.SubElement(material, "{http://example.org/ext3d/}texture")
                    texture.set("type", tex['type'])
                    texture.text = tex['name']
        
        # Acquisition Information
        tech_props = context.scene.mets_technical
        acquisition_method = obj.get('acquisition_method', tech_props.acquisition_method)
        
        if acquisition_method and acquisition_method != 'Modellazione Manuale':
            acq_info = ET.SubElement(technical_3d, "{http://example.org/ext3d/}acquisitionInformation")
            
            # Acquisition method
            acq_method = ET.SubElement(acq_info, "{http://example.org/ext3d/}acquisitionMethod")
            acq_method.text = acquisition_method
            
            # Device manufacturer
            device_manuf = ET.SubElement(acq_info, "{http://example.org/ext3d/}deviceManufacturer")
            device_manuf.text = obj.get('device_manufacturer', tech_props.device_manufacturer) or "Unknown"
            
            # Device model
            device_model = ET.SubElement(acq_info, "{http://example.org/ext3d/}deviceModel")
            device_model.text = obj.get('device_model', tech_props.device_model) or "Unknown"
            
            # Capture settings
            capture_settings = ET.SubElement(acq_info, "{http://example.org/ext3d/}captureSettings")
            
            if acquisition_method == 'Fotogrammetria':
                image_count = ET.SubElement(capture_settings, "{http://example.org/ext3d/}imageCount")
                image_count.text = str(obj.get('image_count', tech_props.image_count) or 0)
                
                focal_length = ET.SubElement(capture_settings, "{http://example.org/ext3d/}focalLength")
                focal_length.text = obj.get('focal_length', tech_props.focal_length) or "50mm"
                
                aperture = ET.SubElement(capture_settings, "{http://example.org/ext3d/}aperture")
                aperture.text = obj.get('aperture', tech_props.aperture) or "f/8"
                
                iso = ET.SubElement(capture_settings, "{http://example.org/ext3d/}iso")
                iso.text = obj.get('iso', tech_props.iso) or "100"
            
            elif acquisition_method in ['Scansione Laser', 'Structured Light']:
                scan_count = ET.SubElement(capture_settings, "{http://example.org/ext3d/}scanCount")
                scan_count.text = str(obj.get('scan_count', tech_props.scan_count) or 0)
                
                resolution = ET.SubElement(capture_settings, "{http://example.org/ext3d/}resolution")
                resolution.text = "0.5mm"
            
            # Lighting (for all acquisition methods)
            lighting = ET.SubElement(capture_settings, "{http://example.org/ext3d/}lighting")
            lighting.text = obj.get('lighting', tech_props.lighting) or "Studio lighting"
            
            # Processing software
            proc_software = ET.SubElement(acq_info, "{http://example.org/ext3d/}processingSoftware")
            proc_software.text = obj.get('software', tech_props.software) or "Blender"
            
            # Processing software version
            proc_software_ver = ET.SubElement(acq_info, "{http://example.org/ext3d/}processingSoftwareVersion")
            proc_software_ver.text = obj.get('software_version', tech_props.software_version) or bpy.app.version_string
        
        # Processing Information
        proc_info = ET.SubElement(technical_3d, "{http://example.org/ext3d/}processingInformation")
        
        # Description
        description = ET.SubElement(proc_info, "{http://example.org/ext3d/}description")
        description.text = f"Processing of 3D model {obj.name} with 3D Survey Collection"
        
        # Software
        software_elem = ET.SubElement(proc_info, "{http://example.org/ext3d/}software")
        software_elem.text = "Blender"
        
        # Software version
        software_ver_elem = ET.SubElement(proc_info, "{http://example.org/ext3d/}softwareVersion")
        software_ver_elem.text = bpy.app.version_string
        
        # Operator
        operator_elem = ET.SubElement(proc_info, "{http://example.org/ext3d/}operator")
        operator_elem.text = tech_props.operator or "3DSC User"
        
        # Date
        date_elem = ET.SubElement(proc_info, "{http://example.org/ext3d/}date")
        date_elem.text = utils.format_datetime()[:10]
    
    def add_rights_metadata(self, amd_sec, context):
        """Add rights metadata section."""
        rights_props = context.scene.mets_rights
        
        # METSRIGHTS metadata
        rights_md = ET.SubElement(amd_sec, "{http://www.loc.gov/METS/}rightsMD")
        rights_md.set("ID", "BCS")
        
        md_wrap = ET.SubElement(rights_md, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap.set("LABEL", "Rights Metadata")
        md_wrap.set("MDTYPE", "METSRIGHTS")
        md_wrap.set("MIMETYPE", "text/xml")
        
        xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
        
        rights_decl = ET.SubElement(xml_data, "{http://cosimo.stanford.edu/sdr/metsrights/}RightsDeclarationMD")
        
        rights_holder = ET.SubElement(rights_decl, "{http://cosimo.stanford.edu/sdr/metsrights/}RightsHolder")
        rights_holder.set("RIGHTSHOLDERID", "3DSC_USER_001")
        
        rights_holder_name = ET.SubElement(rights_holder, "{http://cosimo.stanford.edu/sdr/metsrights/}RightsHolderName")
        rights_holder_name.text = rights_props.rights_holder or "3D Survey Collection User"
        
        rights_holder_contact = ET.SubElement(rights_holder, "{http://cosimo.stanford.edu/sdr/metsrights/}RightsHolderContact")
        
        rights_holder_email = ET.SubElement(rights_holder_contact, "{http://cosimo.stanford.edu/sdr/metsrights/}RightsHolderContactEmail")
        rights_holder_email.text = rights_props.rights_holder_contact or "user@example.com"
        
        context_elem = ET.SubElement(rights_decl, "{http://cosimo.stanford.edu/sdr/metsrights/}Context")
        context_elem.set("CONTEXTCLASS", "OTHER")
        context_elem.set("OTHERCONTEXTTYPE", "Standard-IPAC")
        context_elem.set("CONTEXTID", "IPAC-PDP-001")
        
        user_name = ET.SubElement(context_elem, "{http://cosimo.stanford.edu/sdr/metsrights/}UserName")
        user_name.text = "Standard-IPAC"
        
        # DCT rights metadata
        rights_md_dct = ET.SubElement(amd_sec, "{http://www.loc.gov/METS/}rightsMD")
        rights_md_dct.set("ID", "DCTrights")
        
        md_wrap_dct = ET.SubElement(rights_md_dct, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap_dct.set("MDTYPE", "DC")
        md_wrap_dct.set("MIMETYPE", "text/xml")
        md_wrap_dct.set("LABEL", "DCT Rights Metadata")
        
        xml_data_dct = ET.SubElement(md_wrap_dct, "{http://www.loc.gov/METS/}xmlData")
        
        license = ET.SubElement(xml_data_dct, "{http://purl.org/dc/terms/}license")
        license.text = rights_props.license_url
        
        rights = ET.SubElement(xml_data_dct, "{http://purl.org/dc/terms/}rights")
        rights.text = rights_props.rights_statement
    
    def add_source_metadata(self, amd_sec, context):
        """Add source metadata section."""
        source_props = context.scene.mets_source
        
        source_md = ET.SubElement(amd_sec, "{http://www.loc.gov/METS/}sourceMD")
        source_md.set("ID", "SMD_01")
        
        md_wrap = ET.SubElement(source_md, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap.set("MDTYPE", "OTHER")
        md_wrap.set("OTHERMDTYPE", "PHYSICAL_SOURCE")
        
        xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
        
        source = ET.SubElement(xml_data, "source")
        
        current_location = ET.SubElement(source, "currentLocation")
        current_location.text = source_props.current_location or "Unknown"
        
        institutional_id = ET.SubElement(source, "institutionalID")
        institutional_id.text = source_props.institutional_id or "Unknown"
        
        conservation_state = ET.SubElement(source, "conservationState")
        conservation_state.text = source_props.conservation_state or "Unknown"
        
        materials = ET.SubElement(source, "materials")
        materials.text = source_props.materials or "Unknown"
    
    def add_digiprov_metadata(self, amd_sec, context, objects):
        """Add digital provenance metadata section."""
        tech_props = context.scene.mets_technical
        
        # Add a digitization event for each acquisition method used
        acquisition_methods = set()
        for obj in objects:
            method = obj.get('acquisition_method', tech_props.acquisition_method)
            if method and method != 'Modellazione Manuale':
                acquisition_methods.add(method)
        
        event_id = 1
        for method in acquisition_methods:
            digiprov_md = ET.SubElement(amd_sec, "{http://www.loc.gov/METS/}digiprovMD")
            digiprov_md.set("ID", f"DPMD_{event_id:02d}")
            
            md_wrap = ET.SubElement(digiprov_md, "{http://www.loc.gov/METS/}mdWrap")
            md_wrap.set("MDTYPE", "PREMIS:EVENT")
            
            xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
            
            event = ET.SubElement(xml_data, "{http://www.loc.gov/premis/v3}event")
            
            event_identifier = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventIdentifier")
            
            event_id_type = ET.SubElement(event_identifier, "{http://www.loc.gov/premis/v3}eventIdentifierType")
            event_id_type.text = "UUID"
            
            event_id_value = ET.SubElement(event_identifier, "{http://www.loc.gov/premis/v3}eventIdentifierValue")
            event_id_value.text = str(uuid.uuid4())
            
            event_type = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventType")
            event_type.text = "digitalizzazione"
            
            event_date = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventDateTime")
            event_date.text = utils.format_datetime()
            
            event_detail = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventDetail")
            if method == 'Fotogrammetria':
                event_detail.text = "Acquisizione fotogrammetrica"
            elif method == 'Scansione Laser':
                event_detail.text = "Acquisizione tramite scansione laser"
            elif method == 'Structured Light':
                event_detail.text = "Acquisizione tramite luce strutturata"
            else:
                event_detail.text = f"Acquisizione tramite {method}"
            
            event_outcome_info = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventOutcomeInformation")
            
            event_outcome = ET.SubElement(event_outcome_info, "{http://www.loc.gov/premis/v3}eventOutcome")
            event_outcome.text = "successo"
            
            event_outcome_detail = ET.SubElement(event_outcome_info, "{http://www.loc.gov/premis/v3}eventOutcomeDetail")
            
            event_outcome_detail_note = ET.SubElement(event_outcome_detail, "{http://www.loc.gov/premis/v3}eventOutcomeDetailNote")
            if method == 'Fotogrammetria':
                event_outcome_detail_note.text = f"Acquisite {tech_props.image_count} immagini ad alta risoluzione"
            elif method == 'Scansione Laser' or method == 'Structured Light':
                event_outcome_detail_note.text = f"Completate {tech_props.scan_count} scansioni"
            else:
                event_outcome_detail_note.text = f"Acquisizione completata con successo"
            
            linking_agent = ET.SubElement(event, "{http://www.loc.gov/premis/v3}linkingAgentIdentifier")
            
            linking_agent_type = ET.SubElement(linking_agent, "{http://www.loc.gov/premis/v3}linkingAgentIdentifierType")
            linking_agent_type.text = "URI"
            
            linking_agent_value = ET.SubElement(linking_agent, "{http://www.loc.gov/premis/v3}linkingAgentIdentifierValue")
            linking_agent_value.text = f"https://example.org/staff/{tech_props.operator or 'user'}"
            
            event_id += 1
        
        # Add processing event
        digiprov_md = ET.SubElement(amd_sec, "{http://www.loc.gov/METS/}digiprovMD")
        digiprov_md.set("ID", f"DPMD_{event_id:02d}")
        
        md_wrap = ET.SubElement(digiprov_md, "{http://www.loc.gov/METS/}mdWrap")
        md_wrap.set("MDTYPE", "PREMIS:EVENT")
        
        xml_data = ET.SubElement(md_wrap, "{http://www.loc.gov/METS/}xmlData")
        
        event = ET.SubElement(xml_data, "{http://www.loc.gov/premis/v3}event")
        
        event_identifier = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventIdentifier")
        
        event_id_type = ET.SubElement(event_identifier, "{http://www.loc.gov/premis/v3}eventIdentifierType")
        event_id_type.text = "UUID"
        
        event_id_value = ET.SubElement(event_identifier, "{http://www.loc.gov/premis/v3}eventIdentifierValue")
        event_id_value.text = str(uuid.uuid4())
        
        event_type = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventType")
        event_type.text = "elaborazione"
        
        event_date = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventDateTime")
        event_date.text = utils.format_datetime()
        
        event_detail = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventDetail")
        event_detail.text = "Elaborazione dei modelli 3D con 3D Survey Collection"
        
        event_outcome_info = ET.SubElement(event, "{http://www.loc.gov/premis/v3}eventOutcomeInformation")
        
        event_outcome = ET.SubElement(event_outcome_info, "{http://www.loc.gov/premis/v3}eventOutcome")
        event_outcome.text = "successo"
        
        event_outcome_detail = ET.SubElement(event_outcome_info, "{http://www.loc.gov/premis/v3}eventOutcomeDetail")
        
        event_outcome_detail_note = ET.SubElement(event_outcome_detail, "{http://www.loc.gov/premis/v3}eventOutcomeDetailNote")
        if len(objects) == 1:
            stats = utils.get_mesh_statistics(objects[0])
            event_outcome_detail_note.text = f"Elaborato modello 3D con {stats['vertex_count']} vertici e {stats['face_count']} facce"
        else:
            event_outcome_detail_note.text = f"Elaborati {len(objects)} modelli 3D"
        
        linking_agent = ET.SubElement(event, "{http://www.loc.gov/premis/v3}linkingAgentIdentifier")
        
        linking_agent_type = ET.SubElement(linking_agent, "{http://www.loc.gov/premis/v3}linkingAgentIdentifierType")
        linking_agent_type.text = "URI"
        
        linking_agent_value = ET.SubElement(linking_agent, "{http://www.loc.gov/premis/v3}linkingAgentIdentifierValue")
        linking_agent_value.text = f"https://example.org/staff/{tech_props.operator or 'user'}"
    
    def add_file_section(self, file_sec, context, objects, tech_id_map):
        """Add file section with file groups."""
        # Main file group
        file_grp = ET.SubElement(file_sec, "{http://www.loc.gov/METS/}fileGrp")
        file_grp.set("ID", "FG_INTERNAL")
        file_grp.set("USE", "INTERNAL")
        
        # Archive file group (master models)
        archive_grp = ET.SubElement(file_grp, "{http://www.loc.gov/METS/}fileGrp")
        archive_grp.set("ID", "FG_ARCHIVE")
        archive_grp.set("USE", "ARCHIVE")
        
        # Add master model files
        file_id_counter = 1
        for obj in objects:
            # Find .blend file path
            blend_path = bpy.data.filepath
            if not blend_path:
                # Skip if .blend not saved
                continue
            
            # Get tech ID for this object
            tech_id = tech_id_map.get(obj, "")
            
            # Add file entry for blend file (as OBJ for now since we don't actually export)
            file_elem = ET.SubElement(archive_grp, "{http://www.loc.gov/METS/}file")
            file_elem.set("ID", f"MASTER_{file_id_counter:02d}")
            file_elem.set("MIMETYPE", "model/obj")  # Using OBJ as placeholder
            file_elem.set("SIZE", str(utils.get_file_size(blend_path)))
            file_elem.set("CREATED", utils.format_datetime())
            
            if context.scene.mets_export_settings.include_checksum:
                file_elem.set("CHECKSUMTYPE", "MD5")
                checksum = utils.calculate_checksum(blend_path)
                if checksum:
                    file_elem.set("CHECKSUM", checksum)
            
            if tech_id:
                file_elem.set("ADMID", tech_id)
            
            # Add file location (using placeholder path since we're not exporting)
            f_locat = ET.SubElement(file_elem, "{http://www.loc.gov/METS/}FLocat")
            f_locat.set("LOCTYPE", "URL")
            f_locat.set("{http://www.w3.org/1999/xlink}href", f"file:///models/{obj.name}.obj")
            
            file_id_counter += 1
            
            # Add material textures if available
            material_info = utils.get_material_and_texture_info(obj)
            for mat in material_info['materials']:
                for tex in mat['textures']:
                    # Check if texture has a valid filepath
                    if not tex['filepath'] or not os.path.exists(tex['filepath']):
                        continue
                    
                    # Add file entry for texture
                    tex_file_elem = ET.SubElement(archive_grp, "{http://www.loc.gov/METS/}file")
                    tex_file_elem.set("ID", f"TEXTURE_{file_id_counter:02d}")
                    tex_file_elem.set("MIMETYPE", "image/png")  # Assuming PNG textures
                    tex_file_elem.set("SIZE", str(utils.get_file_size(tex['filepath'])))
                    tex_file_elem.set("CREATED", utils.format_datetime())
                    
                    if context.scene.mets_export_settings.include_checksum:
                        tex_file_elem.set("CHECKSUMTYPE", "MD5")
                        checksum = utils.calculate_checksum(tex['filepath'])
                        if checksum:
                            tex_file_elem.set("CHECKSUM", checksum)
                    
                    # Add file location
                    tex_f_locat = ET.SubElement(tex_file_elem, "{http://www.loc.gov/METS/}FLocat")
                    tex_f_locat.set("LOCTYPE", "URL")
                    tex_f_locat.set("{http://www.w3.org/1999/xlink}href", f"file:///textures/{os.path.basename(tex['filepath'])}")
                    
                    file_id_counter += 1
    
    def add_physical_struct_map(self, struct_map, context, objects):
        """Add physical structure map."""
        # Main div
        main_div = ET.SubElement(struct_map, "{http://www.loc.gov/METS/}div")
        main_div.set("LABEL", "3D Models - Physical Structure")
        main_div.set("TYPE", "FOLDER")
        
        # Add a div for each object
        for i, obj in enumerate(objects):
            obj_div = ET.SubElement(main_div, "{http://www.loc.gov/METS/}div")
            obj_div.set("ID", f"DO_3DMODEL_{i+1:03d}")
            obj_div.set("LABEL", obj.name)
            obj_div.set("ORDER", str(i+1))
            obj_div.set("TYPE", "FILE")
            
            # Add file pointer to master file (if we were actually exporting)
            fptr = ET.SubElement(obj_div, "{http://www.loc.gov/METS/}fptr")
            fptr.set("FILEID", f"MASTER_{i+1:02d}")
            
            # Add texture info if available
            material_info = utils.get_material_and_texture_info(obj)
            tex_counter = 0
            for mat in material_info['materials']:
                for tex in mat['textures']:
                    tex_counter += 1
                    
                    # Only add if texture has a valid filepath
                    if not tex['filepath'] or not os.path.exists(tex['filepath']):
                        continue
                    
                    tex_div = ET.SubElement(main_div, "{http://www.loc.gov/METS/}div")
                    tex_div.set("ID", f"DO_TEXTURE_{i+1:03d}_{tex_counter:02d}")
                    tex_div.set("LABEL", f"{tex['type'].capitalize()} Texture - {tex['name']}")
                    tex_div.set("ORDER", str(len(objects) + tex_counter))
                    tex_div.set("TYPE", "FILE")
                    
                    tex_fptr = ET.SubElement(tex_div, "{http://www.loc.gov/METS/}fptr")
                    tex_fptr.set("FILEID", f"TEXTURE_{i+1+tex_counter:02d}")
    
    def add_logical_struct_map(self, struct_map, context, objects):
        """Add logical structure map."""
        # Main div
        main_div = ET.SubElement(struct_map, "{http://www.loc.gov/METS/}div")
        main_div.set("LABEL", "3D Models - Logical Structure")
        main_div.set("TYPE", "FOLDER")
        
        # Models folder
        models_div = ET.SubElement(main_div, "{http://www.loc.gov/METS/}div")
        models_div.set("LABEL", "3D Models")
        models_div.set("TYPE", "FOLDER")
        
        # Add a div for each object
        for i, obj in enumerate(objects):
            obj_div = ET.SubElement(models_div, "{http://www.loc.gov/METS/}div")
            obj_div.set("ID", f"DOL_MODEL_{i+1:03d}")
            obj_div.set("LABEL", obj.name)
            obj_div.set("ORDER", str(i+1))
            obj_div.set("TYPE", "FILE")
            
            # Add file pointer
            fptr = ET.SubElement(obj_div, "{http://www.loc.gov/METS/}fptr")
            fptr.set("FILEID", f"MASTER_{i+1:02d}")
            
            # If this model has materials with textures, add a textures subfolder
            material_info = utils.get_material_and_texture_info(obj)
            if material_info['texture_count'] > 0:
                tex_div = ET.SubElement(models_div, "{http://www.loc.gov/METS/}div")
                tex_div.set("LABEL", f"Textures for {obj.name}")
                tex_div.set("TYPE", "FOLDER")
                
                # Add each texture
                tex_counter = 0
                for mat in material_info['materials']:
                    for tex in mat['textures']:
                        # Only add if texture has a valid filepath
                        if not tex['filepath'] or not os.path.exists(tex['filepath']):
                            continue
                            
                        tex_counter += 1
                        tex_file_div = ET.SubElement(tex_div, "{http://www.loc.gov/METS/}div")
                        tex_file_div.set("ID", f"DOL_TEXTURE_{i+1:03d}_{tex_counter:02d}")
                        tex_file_div.set("LABEL", f"{tex['type'].capitalize()} - {tex['name']}")
                        tex_file_div.set("TYPE", "FILE")
                        
                        tex_fptr = ET.SubElement(tex_file_div, "{http://www.loc.gov/METS/}fptr")
                        tex_fptr.set("FILEID", f"TEXTURE_{i+1+tex_counter:02d}")
    
    def add_struct_links(self, struct_link, context):
        """Add structural links."""
        # In a real implementation, this would add links between different 
        # structural elements. For simplicity in this version, we'll leave it minimal.
        pass  # We're not adding links in this simple version
    
    def add_behaviors(self, behavior_sec, context):
        """Add behavior definitions."""
        # 3D Viewer behavior
        behavior = ET.SubElement(behavior_sec, "{http://www.loc.gov/METS/}behavior")
        behavior.set("ID", "BHVR_3DVIEWER")
        behavior.set("STRUCTID", "DOL_MODEL_001")  # Reference to first model
        
        mechanism = ET.SubElement(behavior, "{http://www.loc.gov/METS/}mechanism")
        mechanism.set("LOCTYPE", "URL")
        mechanism.set("{http://www.w3.org/1999/xlink}href", "https://example.org/3dviewer?model=")
        
        # AR Viewer
        behavior = ET.SubElement(behavior_sec, "{http://www.loc.gov/METS/}behavior")
        behavior.set("ID", "BHVR_AR")
        behavior.set("STRUCTID", "DOL_MODEL_001")  # Reference to first model
        
        mechanism = ET.SubElement(behavior, "{http://www.loc.gov/METS/}mechanism")
        mechanism.set("LOCTYPE", "URL")
        mechanism.set("{http://www.w3.org/1999/xlink}href", "https://example.org/ar-viewer?model=")

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

# List of classes for registration
classes = [
    METS_OT_ExportMETS,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()