import bpy
import os
import shutil
from mathutils import Vector
import tempfile
from datetime import datetime
from mathutils import kdtree

def print_header(title):
    print(f"\n-- {datetime.now().strftime('%H:%M:%S')} :: {title} --\n")

def print_subheader(title):
    print(f"\n~~ {title} ~~\n")

def log_progress(message, indent=0):
    timestamp = datetime.now().strftime('%H:%M:%S')
    indent_str = "  " * indent
    print(f"[{timestamp}] {indent_str}{message}")

def material_has_transparency(material):
    if not material or not material.use_nodes:
        return False
    
    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            if material.blend_method != 'OPAQUE':
                return True
            alpha_socket = node.inputs.get('Alpha')
            if alpha_socket and alpha_socket.default_value < 1.0:
                return True
    return False

def should_preserve_uv(obj, material):
    if not material or not material.use_nodes:
        return False
        
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            if node.image.size[0] <= 512 or node.image.size[1] <= 512:
                return True
    return False

def create_master_export_folder(master_name):
    base_paths = [
        bpy.path.abspath("//"),
        os.path.join(os.path.expanduser("~"), "Documents"),
        tempfile.gettempdir(),
        os.path.dirname(os.path.realpath(__file__)),
        os.path.join(os.path.expanduser("~"), "Desktop")
    ]
    
    for base_path in base_paths:
        if base_path and os.path.exists(base_path) and os.access(base_path, os.W_OK):
            master_folder = os.path.join(base_path, master_name)
            os.makedirs(master_folder, exist_ok=True)
            return master_folder
    return None

def create_export_folder(master_folder, obj_name):
    if not master_folder:
        print("No master folder available.")
        return None
    
    export_folder = os.path.join(master_folder, f"{obj_name.replace('.', '_')}_bake")
    os.makedirs(export_folder, exist_ok=True)
    return export_folder

def create_gdt_content(filepath, obj_name):
    parent_folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(filepath))))
    sub_folder = os.path.basename(os.path.dirname(os.path.dirname(filepath)))
    curr_folder = os.path.basename(os.path.dirname(filepath))
    
    rel_xmodel = os.path.join("..", parent_folder, sub_folder, curr_folder, f"{obj_name.replace('.', '_').lower()}.xmodel_bin").replace('/', '\\')
    rel_texture = os.path.join(parent_folder, sub_folder, curr_folder, f"{obj_name.replace('.', '_').lower()}_bake_main.png").replace('/', '\\')

    gdt_name = obj_name.replace('.', '_')

    gdt_content = "{\n"
    
    gdt_content += f'''    "i_{safe_name}" ( "image.gdf" )
    {{
        "arabicUnsafe" "0"
        "baseImage" "{rel_texture}"
        "clampU" "0"
        "clampV" "0"
        "colorSRGB" "0"
        "compressionMethod" "compressed high color"
        "coreSemantic" "sRGB3chAlpha"
        "doNotResize" "0"
        "forceStreaming" "0"
        "germanUnsafe" "0"
        "imageType" "Texture"
        "japaneseUnsafe" "0"
        "mipBase" "1/1"
        "semantic" "diffuseMap"
        "streamable" "1"
        "type" "image"
    }}

'''

    gdt_content += f'''    "{safe_name}_m" ( "material.gdf" )
    {{
        "colorMap" "i_{safe_name}"
        "materialType" "lit_advanced_fullspec"
        "surfaceType" "default"
        "template" "material.template"
        "glossSurfaceType" "paint"
        "specAmount" "1"
        "specColorTint" "0.760757 0.764664 0.764664 1"
        "glossRangeMax" "7.0"
        "glossRangeMin" "2.0"
        "materialCategory" "Geometry Advanced"
        "gSpecLobeAWeight" "0.375" 
        "gSpecLobeRoughnessA" "0.05"
        "gSpecLobeRoughnessB" "0.1875"
        "gSpecIndexOfRefraction" "1.333"
    }}

'''

    gdt_content += f'''    "{safe_name}" ( "xmodel.gdf" )
    {{
        "filename" "{rel_xmodel}"
        "type" "animated"
        "usage_zombie_body" "1"
        "scale" "10.0"
        "skinOverride" "rs_untextured {safe_name}_m\\r\\n"
    }}'''

    gdt_content += "\n}"
    return gdt_content

def save_gdt_file(filepath, content):
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        log_progress(f"GDT file saved: {filepath}")
    except Exception as e:
        log_progress(f"Error saving GDT file: {e}")

class GDTBuilder:
    def __init__(self):
        self.images = []
        self.materials = []
        self.models = []
        self.submodels = []
        
    def add_image(self, name, rel_path):
        self.images.append({
            'name': name,
            'path': rel_path
        })
        
    def add_material(self, name, image_name):
        self.materials.append({
            'name': name,
            'image': image_name
        })
        
    def add_model(self, name, rel_path, material_name):
        rel_path = rel_path.replace('/', '\\\\').replace('\\', '\\\\')
        self.models.append({
            'name': name,
            'path': rel_path,
            'material': material_name
        })
        
    def add_submodel(self, parent_name, name, rel_path, material_name):
        rel_path = rel_path.replace('/', '\\\\').replace('\\', '\\\\')
        self.submodels.append({
            'parent': parent_name,
            'name': name,
            'path': rel_path,
            'material': material_name
        })
        
    def build_gdt_content(self):
        gdt_content = "{\n"
        
        for img in self.images:
            img_path = img['path'].replace('/', '\\')
            gdt_content += f'''    "i_{img['name']}" ( "image.gdf" )
    {{
        "arabicUnsafe" "0"
        "baseImage" "{img_path}"
        "clampU" "0"
        "clampV" "0"
        "colorSRGB" "0"
        "compositeChannel1" ""
        "compositeChannel2" ""
        "compositeChannel3" ""
        "compositeChannel4" ""
        "compositeImage1" ""
        "compositeImage2" ""
        "compositeImage3" ""
        "compositeImage4" ""
        "compositeSample1" ""
        "compositeSample2" ""
        "compositeSample3" ""
        "compositeSample4" ""
        "compositeType" ""
        "compressionMethod" "compressed high color"
        "coreSemantic" "sRGB3chAlpha"
        "doNotResize" "0"
        "forceStreaming" "0"
        "fromAlpha" "0"
        "germanUnsafe" "0"
        "glossVarianceScale" "1"
        "himipStreaming" "0"
        "imageType" "Texture"
        "japaneseUnsafe" "0"
        "legallyApproved" "0"
        "matureContent" "0"
        "mipBase" "1/1"
        "mipMask" ""
        "mipMode" "Average"
        "mipNorm" "0"
        "noMipMaps" "0"
        "noPicMip" "0"
        "premulAlpha" "0"
        "semantic" "diffuseMap"
        "streamable" "1"
        "textureAtlasColumnCount" "1"
        "textureAtlasRowCount" "1"
        "type" "image"
    }}\n\n'''

        for mat in self.materials:
            gdt_content += f'''    "{mat['name']}" ( "material.gdf" )
    {{
        "adsZscaleOn" "0"
        "aiClip" "0"
        "aiSightClip" "0"
        "alphaDissolveInt" "255"
        "alphaDissolveMarginAbove" "0"
        "alphaMap" ""
        "alphaRevealMap" ""
        "alphaRevealRamp" "0.5"
        "alphaRevealSoftEdge" "0.01"
        "alphaTexture" "0"
        "arabicUnsafe" "0"
        "areaLight" "0"
        "backlightScatterColor" "1 1 1 1"
        "bulletClip" "0"
        "camoDetailMap" ""
        "camoMaskMap" ""
        "canShootClip" "0"
        "caulk" "0"
        "causticMap" ""
        "colorDetailMap" ""
        "colorDetailScaleX" "8"
        "colorDetailScaleY" "8"
        "colorMap" "i_{mat['image']}"
        "colorTint" "1 1 1 1"
        "colorWriteAlpha" "Enable"
        "colorWriteBlue" "Enable"
        "colorWriteGreen" "Enable"
        "colorWriteRed" "Enable"
        "detail" "0"
        "doNotUse" "0"
        "doubleSidedLighting" "0"
        "drawToggle" "0"
        "germanUnsafe" "0"
        "glossRangeMax" "7.0"
        "glossRangeMin" "2.0"
        "glossSurfaceType" "paint"
        "gSpecIndexOfRefraction" "1.333"
        "gSpecLobeAWeight" "0.375"
        "gSpecLobeRoughnessA" "0.05"
        "gSpecLobeRoughnessB" "0.1875"
        "japaneseUnsafe" "0"
        "materialCategory" "Geometry Advanced"
        "materialType" "lit_advanced_fullspec"
        "surfaceType" "concrete"
        "specAmount" "1"
        "specColorTint" "0.760757 0.764664 0.764664 1"
        "template" "material.template"
        "usage" "<not in editor>"
    }}\n\n'''

        for model in self.models:
            gdt_content += self._build_model_entry(model)
            submodels = [s for s in self.submodels if s['parent'] == model['name']]
            for submodel in submodels:
                gdt_content += self._build_submodel_entry(submodel)

        gdt_content += "}"
        return gdt_content
    
    def _build_model_entry(self, model):
        model_entry = f'''    "{model['name']}" ( "xmodel.gdf" )
    {{
        "arabicUnsafe" "0"
        "autogenLod4" "0"
        "autogenLod4Percent" "13"
        "autogenLod5" "0"
        "autogenLod5Percent" "13"
        "autogenLod6" "0"
        "autogenLod6Percent" "13"
        "autogenLod7" "0"
        "autogenLod7Percent" "13"
        "autogenLowestLod" "0"
        "autogenLowestLodPercent" "13"
        "autogenLowLod" "0"
        "autogenLowLodPercent" "25"
        "autogenMediumLod" "0"
        "autogenMediumLodPercent" "50"
        "boneControllers" ""
        "boneStabilizers" ""
        "BulletCollisionFile" ""
        "BulletCollisionLOD" "High"
        "BulletCollisionRigid" "0"
        "CollisionMap" ""
        "cullOutDiameter" "0"
        "cullOutOffsetCP" "1"
        "cullOutOffsetMP" "1"
        "customAutogenParams" "0"
        "DetailShadows" "0"
        "doNotUse" "0"
        "dropLOD" "Auto"
        "filename" "{model['path']}"
        "forceLod4Rigid" "0"
        "forceLod5Rigid" "0"
        "forceLod6Rigid" "0"
        "forceLod7Rigid" "0"
        "forceLowestLodRigid" "0"
        "forceLowLodRigid" "0"
        "forceMediumLodRigid" "0"
        "germanUnsafe" "0"
        "heroAsset" "0"
        "heroLighting" "0"
        "highLodDist" "0"
        "hitBoxModel" ""
        "isSiege" "0"
        "japaneseUnsafe" "0"
        "LodColorPriority" "0.008"
        "lodNormalPriority" "1.54"
        "lodPositionPriority" "12"
        "lodPresets" "performance"
        "LodUvPriority" "3.5"
        "noCastShadow" "0"
        "noOutdoorOcclude" "0"
        "notInEditor" "0"
        "physicsConstraints" ""
        "physicsPreset" ""
        "preserveOriginalUVs" "0"
        "scale" "10.0"
        "scaleCollMap" "0"
        "ShadowLOD" "Auto"
        "skinOverride" "rs_untextured {model['material']}\\r\\n"
        "type" "rigid"
        "usage_attachment" "0"
        "usage_hero" "0"
        "usage_view" "0"
        "usage_weapon" "0"
        "usage_zombie_body" "1"
        "usage_zombie_world_prop" "0"
        "submodel0_Name" "{model['name']}_f"
    }}\n\n'''
        return model_entry
    
    def _build_submodel_entry(self, submodel):
        return f'''    "{submodel['name']}" ( "xmodel.gdf" )
    {{
        "filename" "{submodel['path']}"
        "type" "animated"
        "usage_zombie_body" "1"
        "scale" "10.0"
        "skinOverride" "rs_untextured {submodel['material']}\\r\\n"
    }}\n\n'''

gdt_builder = GDTBuilder()

def apply_material_based_offset(obj):
    if not obj or obj.type != 'MESH':
        return
        
    materials = obj.material_slots
    mat_properties = {}
    
    for i, mat_slot in enumerate(materials):
        if mat_slot.material:
            is_transparent = material_has_transparency(mat_slot.material)
            mat_properties[i] = {
                'transparent': is_transparent,
                'priority': 0
            }
            if is_transparent:
                mat_properties[i]['priority'] = 2
    
    BASE_OFFSET = 0.005
    
    processed_verts = {}
    
    for poly in obj.data.polygons:
        mat_index = poly.material_index
        mat_priority = mat_properties.get(mat_index, {}).get('priority', 0)
        
        offset = BASE_OFFSET * (mat_index + 1) + (BASE_OFFSET * 2 * mat_priority)
        
        if poly.normal.z > 0:
            offset += BASE_OFFSET * 0.5
        elif poly.normal.z < 0:
            offset -= BASE_OFFSET * 0.5
            
        for vert_idx in poly.vertices:
            if vert_idx not in processed_verts:
                processed_verts[vert_idx] = []
            processed_verts[vert_idx].append(offset)
    
    for vert_idx, offsets in processed_verts.items():
        avg_offset = sum(offsets) / len(offsets)
        obj.data.vertices[vert_idx].co.z += avg_offset
    
    for poly in obj.data.polygons:
        mat_index = poly.material_index
        if mat_properties.get(mat_index, {}).get('transparent', False):
            backface_offset = -BASE_OFFSET * 0.1
            for vert_idx in poly.vertices:
                obj.data.vertices[vert_idx].co += poly.normal * backface_offset

def export_to_xmodel(filepath, obj, create_extruded=False):
    vert_count = len(obj.data.vertices)
    if (vert_count > 65534):
        print(f"EMERGENCY: {obj.name} has {vert_count} vertices - performing last-minute split")
        verify_and_split_if_needed(obj)
        return False

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    original_mesh = obj.data.copy()
    original_positions = [(v.co.x, v.co.y, v.co.z) for v in obj.data.vertices]
    
    for mod in obj.modifiers:
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except:
            print(f"Couldn't apply {mod.name}, removing instead")
            obj.modifiers.remove(mod)

    for vertex in obj.data.vertices:
        vertex.co.z += 0.001

    apply_material_based_offset(obj)

    log_progress("Exporting normal model...", 1)
    safe_name = obj.name.replace('.', '_').lower()
    xmodel_filename = f"{safe_name}.xmodel_bin"
    extruded_filename = f"{safe_name}_f.xmodel_bin" if create_extruded else None
    xmodel_dir = os.path.dirname(filepath)
    filepath_normal = os.path.join(xmodel_dir, xmodel_filename)
    
    try:
        result = bpy.ops.export_scene.xmodel(
            filepath=filepath_normal,
            check_existing=True,
            target_format='XMODEL_BIN',
            version='7',
            use_selection=True
        )
        
        if result == {'FINISHED'}:
            log_progress(f"Normal model exported successfully: {xmodel_filename}", 2)
            parent_folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(filepath_normal))))
            sub_folder = os.path.basename(os.path.dirname(os.path.dirname(filepath_normal)))
            curr_folder = os.path.basename(os.path.dirname(filepath_normal))
            
            rel_path = f"..\\{parent_folder}\\{sub_folder}\\{curr_folder}"
            rel_xmodel = os.path.join("..", parent_folder, sub_folder, curr_folder, xmodel_filename).replace('/', '\\')
            
            gdt_builder.add_model(safe_name, rel_xmodel, f"{safe_name}_m")
            
            if create_extruded:
                log_progress("Creating flipped version...", 1)
                obj.data = original_mesh.copy()
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.flip_normals()
                bpy.ops.object.mode_set(mode='OBJECT')
                
                filepath_extruded = os.path.join(xmodel_dir, extruded_filename)
                log_progress(f"Exporting flipped model: {extruded_filename}", 2)
                
                result = bpy.ops.export_scene.xmodel(
                    filepath=filepath_extruded,
                    check_existing=True,
                    target_format='XMODEL_BIN',
                    version='7',
                    use_selection=True
                )
                
                if result == {'FINISHED'}:
                    log_progress("Flipped model exported successfully", 2)
                    rel_xmodel_extruded = os.path.join("..", parent_folder, sub_folder, curr_folder, extruded_filename).replace('/', '\\')
                    gdt_builder.add_submodel(safe_name, f"{safe_name}_f", rel_xmodel_extruded, f"{safe_name}_m")
                else:
                    log_progress("Failed to export extruded model", 2)
            
            return True
        return False
        
    except Exception as e:
        print(f"Export error: {str(e)}")
        return False
    finally:
        if original_mesh:
            obj.data = original_mesh
            for i, pos in enumerate(original_positions):
                obj.data.vertices[i].co = Vector(pos)
            log_progress("Restored original mesh data", 1)

def save_consolidated_gdt(master_folder, base_name):
    blend_file_path = bpy.data.filepath
    if blend_file_path:
        blend_parent = os.path.dirname(os.path.dirname(blend_file_path))
        source_data_path = os.path.join(blend_parent, "source_data")
    else:
        blend_parent = os.path.dirname(os.path.dirname(master_folder))
        source_data_path = os.path.join(blend_parent, "source_data")
    
    os.makedirs(source_data_path, exist_ok=True)
    
    gdt_content = gdt_builder.build_gdt_content()
    
    gdt_filepath = os.path.join(source_data_path, f"{base_name}.gdt")
    save_gdt_file(gdt_filepath, gdt_content)
    print(f"GDT file saved to: {gdt_filepath}")

def create_blank_image(name, width, height):
    img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
    pixels = [0.0] * (width * height * 4)
    img.pixels = pixels
    return img

def unwrap_and_bake_selected(obj, master_folder):
    print_header("STARTING BAKE PROCESS")
    log_progress(f"Baking object: {obj.name}")
    original_obj = obj
    
    if original_obj is None or original_obj.type != 'MESH':
        log_progress("Error: Please select a mesh object")
        return

    export_folder = create_export_folder(master_folder, original_obj.name)
    if not export_folder:
        log_progress("Error: Could not create export folder!")
        return
    log_progress(f"Created export folder: {export_folder}")

    preserve_faces = set()
    
    for poly in original_obj.data.polygons:
        if poly.material_index < len(original_obj.material_slots):
            mat = original_obj.material_slots[poly.material_index].material
            if should_preserve_uv(original_obj, mat):
                preserve_faces.add(poly.index)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    
    if len(obj.data.polygons) == 0:
        log_progress("Error: Object has no faces to unwrap")
        return
        
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.mark_seam(clear=True)
    bpy.ops.mesh.mark_sharp(clear=True)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    for poly in original_obj.data.polygons:
        poly.select = poly.index not in preserve_faces
    bpy.ops.object.mode_set(mode='EDIT')
    
    log_progress("Starting UV unwrap for non-preserved faces...", 1)
    try:
        bpy.ops.uv.smart_project(
            angle_limit=89.0,
            island_margin=0.001,
            area_weight=1.0,
            correct_aspect=True,
            scale_to_bounds=True
        )
        log_progress("UV unwrap completed successfully", 1)
    except RuntimeError as e:
        log_progress(f"UV unwrapping failed: {str(e)}", 1)
        try:
            log_progress("Trying fallback unwrap method...", 1)
            bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
            log_progress("Fallback unwrap successful", 1)
        except:
            log_progress("Both UV unwrapping methods failed!", 1)
            return
    
    bpy.ops.object.mode_set(mode='OBJECT')

    def create_black_image(name, width, height):
        img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
        pixels = [0.0, 0.0, 0.0, 1.0] * (width * height)
        img.pixels.foreach_set(pixels)
        return img

    safe_name = original_obj.name.replace('.', '_').lower()
    bake_image_main = create_black_image(
        name=f"{safe_name}_bake_main",
        width=1024,
        height=1024
    )
    
    bake_image_preserved = create_black_image(
        name=f"{safe_name}_bake_preserved",
        width=512,
        height=512
    )

    has_transparency = False
    for material_slot in original_obj.material_slots:
        if not material_slot.material:
            continue
            
        material = material_slot.material
        if material_has_transparency(material):
            has_transparency = True
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        for node in list(nodes):
            if node.type == 'TEX_IMAGE' and node.image in [bake_image_main, bake_image_preserved]:
                nodes.remove(node)
        
        is_preserved = should_preserve_uv(original_obj, material)
        target_image = bake_image_preserved if is_preserved else bake_image_main
        bake_node = nodes.new('ShaderNodeTexImage')
        bake_node.image = target_image
        bake_node.select = True
        nodes.active = bake_node
        
        principled = None
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                principled = node
                break
        
        if not principled:
            principled = nodes.new('ShaderNodeBsdfPrincipled')
            
        principled.inputs['Emission Strength'].default_value = 0.5

    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)

    lights = [
        ('Top', (0, 0, -3.14159)),
        ('Front', (1.5708, 0, 0)),
        ('Left', (0, -1.5708, 0)),
        ('Right', (0, 1.5708, 0)),
        ('Back', (-1.5708, 0, 0))
    ]

    for name, rotation in lights:
        light_data = bpy.data.lights.new(name=name, type='SUN')
        light_data.energy = 5.0
        light_data.angle = 180.0
        light_object = bpy.data.objects.new(name=name, object_data=light_data)
        bpy.context.scene.collection.objects.link(light_object)
        light_object.rotation_euler = rotation

    bpy.context.scene.world.use_nodes = True
    world_nodes = bpy.context.scene.world.node_tree.nodes
    world_nodes["Background"].inputs["Strength"].default_value = 2.0
    world_nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)

    bpy.context.scene.cycles.diffuse_bounces = 2
    bpy.context.scene.cycles.caustics_reflective = False
    bpy.context.scene.cycles.caustics_refractive = False

    cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
    cycles_prefs.compute_device_type = 'CUDA'
    cycles_prefs.refresh_devices()
    
    for device_type in cycles_prefs.get_devices_for_type('CUDA'):
        device_type.use = True
    cycles_prefs.get_devices_for_type('CPU')[0].use = True
    
    bpy.context.scene.cycles.device = 'GPU'
    bpy.context.scene.cycles.use_denoising = True
    bpy.context.scene.cycles.preview_denoising = True
    
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = 512
    bpy.context.scene.cycles.diffuse_bounces = 4
    bpy.context.scene.render.bake.margin = 16
    bpy.context.scene.render.bake.use_pass_direct = True
    bpy.context.scene.render.bake.use_pass_indirect = True
    bpy.context.scene.render.bake.use_selected_to_active = False
    bpy.context.scene.render.bake.use_clear = True
    bpy.context.scene.render.bake.target = 'IMAGE_TEXTURES'
    
    bpy.context.scene.render.bake.use_cage = True
    bpy.context.scene.render.bake.cage_extrusion = 0.02
    
    bpy.context.scene.cycles.use_adaptive_sampling = False
    bpy.context.scene.cycles.use_denoising = False
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.pack_islands(margin=0.02, rotate=False)
    bpy.ops.uv.pin(clear=True)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode='OBJECT')
    
    if has_transparency:
        bake_image_main.alpha_mode = 'NONE'
        bake_image_preserved.alpha_mode = 'NONE'
    
    original_obj.select_set(True)
    bpy.context.view_layer.objects.active = original_obj

    def get_save_path(filename):
        possible_paths = [
            bpy.path.abspath("//"),
            os.path.join(os.path.expanduser("~"), "Documents"),
            tempfile.gettempdir(),
            os.path.dirname(os.path.realpath(__file__))
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path) and os.access(path, os.W_OK):
                return os.path.join(path, filename)
                
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        return os.path.join(desktop, filename)
    
    log_progress("Setting up bake parameters...", 1)
    print_subheader("BAKING TEXTURES")
    if preserve_faces:
        log_progress("Starting preserved UV bake...", 1)
        black_pixels = [0.0, 0.0, 0.0, 1.0] * (512 * 512)
        bake_image_preserved.pixels.foreach_set(black_pixels)

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        for poly in original_obj.data.polygons:
            poly.select = poly.index in preserve_faces
        bpy.ops.object.mode_set(mode='OBJECT')

        log_progress("Beginning preserved bake operation...", 2)
        bpy.ops.object.bake(type='DIFFUSE')
        log_progress("Preserved bake completed", 2)

    log_progress("Starting main texture bake...", 1)
    black_pixels = [0.0, 0.0, 0.0, 1.0] * (1024 * 1024)
    bake_image_main.pixels.foreach_set(black_pixels)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    for poly in original_obj.data.polygons:
        poly.select = poly.index not in preserve_faces
    bpy.ops.object.mode_set(mode='OBJECT')

    log_progress("Beginning main bake operation...", 2)
    bpy.ops.object.bake(type='DIFFUSE')
    log_progress("Main bake completed", 2)
    
    safe_name = original_obj.name.replace('.', '_').lower()
    main_path = os.path.join(export_folder, f"{safe_name}_bake_main.png")
    xmodel_path = os.path.join(export_folder, f"{safe_name}.xmodel_bin")
    
    try:
        log_progress("Saving main texture...", 1)
        bake_image_main.save_render(filepath=main_path)
        log_progress(f"Main texture saved to: {main_path}", 1)
        
        parent_folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(main_path))))
        sub_folder = os.path.basename(os.path.dirname(os.path.dirname(main_path)))
        curr_folder = os.path.basename(os.path.dirname(main_path))
        
        rel_texture = f"{parent_folder}\\{sub_folder}\\{curr_folder}\\{safe_name}_bake_main.png"
        
        gdt_builder.add_image(safe_name, rel_texture) 
        gdt_builder.add_material(f"{safe_name}_m", safe_name)
        
    except Exception as e:
        log_progress(f"Error saving main texture: {e}", 1)

    try:
        if export_to_xmodel(xmodel_path, original_obj, create_extruded=True):
            print(f"XMODEL_BIN files saved to: {xmodel_path}")
        else:
            print("Failed to export XMODEL_BIN files")
    except Exception as e:
        print(f"Error saving XMODEL_BIN files: {e}")
        
def verify_and_split_if_needed(obj):
    MAX_SAFE_VERTICES = 12000
    ABSOLUTE_MAX = 60000
    
    def optimize_mesh(obj):
        print(f"Optimizing mesh for {obj.name}")
        bpy.context.view_layer.objects.active = obj
        
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.001)
        bpy.ops.mesh.dissolve_degenerate()
        bpy.ops.mesh.delete_loose()
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return len(obj.data.vertices)

    def force_decimation(obj, target_ratio=None):
        print(f"Applying aggressive decimation to {obj.name}")
        bpy.context.view_layer.objects.active = obj
        
        current_verts = len(obj.data.vertices)
        if target_ratio is None:
            target_ratio = (ABSOLUTE_MAX * 0.90) / current_verts
        
        modifier = obj.modifiers.new(name="Planar", type='DECIMATE')
        modifier.decimate_type = 'DISSOLVE'
        modifier.angle_limit = 0.087
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        
        if len(obj.data.vertices) > ABSOLUTE_MAX:
            modifier = obj.modifiers.new(name="Collapse", type='DECIMATE')
            modifier.decimate_type = 'COLLAPSE'
            modifier.ratio = min(target_ratio, 0.95)
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        
        optimize_mesh(obj)
        print(f"Decimated from {current_verts} to {len(obj.data.vertices)} vertices")

    def perform_emergency_split(obj):
        print(f"Performing multi-pass split for {obj.name}")
        bpy.context.view_layer.objects.active = obj
        
        optimize_mesh(obj)
        if len(obj.data.vertices) <= MAX_SAFE_VERTICES:
            return True
            
        for attempt in range(3):
            if len(obj.data.vertices) <= MAX_SAFE_VERTICES:
                break
                
            for axis in [2, 0, 1]:
                bounds = [obj.matrix_world @ Vector(coord) for coord in obj.bound_box]
                min_val = min(v[axis] for v in bounds)
                max_val = max(v[axis] for v in bounds)
                mid = (min_val + max_val) / 2
                
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                plane_no = [0, 0, 0]
                plane_no[axis] = 1
                
                for split_factor in [0.5, 0.333, 0.667]:
                    split_pos = min_val + (max_val - min_val) * split_factor
                    bpy.ops.mesh.bisect(
                        plane_co=[split_pos if i == axis else 0 for i in range(3)],
                        plane_no=plane_no,
                        clear_inner=True,
                        clear_outer=False
                    )
                    bpy.ops.object.mode_set(mode='OBJECT')
                    
                    new_objs = [o for o in bpy.context.selected_objects if o != obj]
                    if new_objs:
                        optimize_mesh(obj)
                        optimize_mesh(new_objs[0])
                        
                        verify_and_split_if_needed(obj)
                        verify_and_split_if_needed(new_objs[0])
                        return True
        
        print("Split failed, forcing decimation")
        force_decimation(obj, target_ratio=0.85)
        return True

    optimize_mesh(obj)
    vert_count = len(obj.data.vertices)
    print(f"Checking {obj.name}: {vert_count} vertices")
    
    if vert_count > ABSOLUTE_MAX:
        print(f"CRITICAL: {obj.name} exceeds vertex limit")
        perform_emergency_split(obj)
        return True
    
    if vert_count > MAX_SAFE_VERTICES:
        return perform_emergency_split(obj)
    
    return False

def store_original_data(obj):
    original_data = {
        'materials': list(obj.material_slots),
        'mesh': obj.data.copy(),
        'vert_dominant_mat': {}
    }

    vert_mat_counts = {}
    for poly in obj.data.polygons:
        mat_index = poly.material_index
        for vert_idx in poly.vertices:
            if vert_idx not in vert_mat_counts:
                vert_mat_counts[vert_idx] = {}
            vert_mat_counts[vert_idx][mat_index] = vert_mat_counts[vert_idx].get(mat_index, 0) + 1

    for vert_idx, counts in vert_mat_counts.items():
        original_data['vert_dominant_mat'][vert_idx] = max(counts, key=counts.get) if counts else 0

    return original_data

def transfer_original_data(new_obj, original_data):
    log_progress("Transferring materials (optimized)...", 1)
    
    original_mesh = original_data['mesh']
    kd = kdtree.KDTree(len(original_mesh.vertices))
    for i, vert in enumerate(original_mesh.vertices):
        kd.insert(vert.co, i)
    kd.balance()

    vert_mat_mapping = {}
    for new_idx, vert in enumerate(new_obj.data.vertices):
        try:
            nearest, orig_idx, dist = kd.find(vert.co)
            if dist < 0.001:
                vert_mat_mapping[new_idx] = original_data['vert_dominant_mat'].get(orig_idx, 0)
        except:
            continue

    mat_list = [mat.material for mat in original_data['materials'] if mat.material]
    new_obj.data.materials.clear()
    for mat in mat_list:
        new_obj.data.materials.append(mat)

    mat_array = []
    for poly in new_obj.data.polygons:
        counts = {}
        for vert_idx in poly.vertices:
            if vert_idx in vert_mat_mapping:
                mat_idx = vert_mat_mapping[vert_idx]
                counts[mat_idx] = counts.get(mat_idx, 0) + 1
        mat_array.append(max(counts, key=counts.get) if counts else 0)

    for i, poly in enumerate(new_obj.data.polygons):
        poly.material_index = mat_array[i] if i < len(mat_array) else 0

def split_by_material_vertices(obj):
    print_header("STARTING MATERIAL SPLIT (OPTIMIZED)")
    MAX_VERTICES = 12000
    
    if not obj or obj.type != 'MESH':
        log_progress("Error: Please select a mesh object")
        return None, None

    log_progress("Storing original mesh data...")
    original_data = store_original_data(obj)

    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode='OBJECT')

    vert_to_polys = {i: [] for i in range(len(obj.data.vertices))}
    vert_to_mats = {i: set() for i in range(len(obj.data.vertices))}
    
    for poly in obj.data.polygons:
        mat_index = poly.material_index
        for vert_idx in poly.vertices:
            vert_to_polys[vert_idx].append(poly.index)
            vert_to_mats[vert_idx].add(mat_index)

    vertex_groups = []
    current_group = set()
    processed_verts = set()
    
    for mat_index in range(len(obj.material_slots)):
        
        material_verts = {v for v, mats in vert_to_mats.items() if mat_index in mats}
        material_verts -= processed_verts
        
        for vert_idx in material_verts:
            if len(current_group) >= MAX_VERTICES:
                if current_group:
                    vertex_groups.append(current_group)
                current_group = set()
            
            current_group.add(vert_idx)
            processed_verts.add(vert_idx)
            
            for poly_idx in vert_to_polys[vert_idx]:
                poly = obj.data.polygons[poly_idx]
                if poly.material_index == mat_index:
                    for connected_vert in poly.vertices:
                        if (connected_vert not in processed_verts and 
                            len(current_group) < MAX_VERTICES):
                            current_group.add(connected_vert)
                            processed_verts.add(connected_vert)

    if current_group:
        vertex_groups.append(current_group)

    print_subheader("PROCESSING VERTEX GROUPS")
    for i, vertices in enumerate(vertex_groups):
        group = obj.vertex_groups.new(name=f"Split_{i+1}")
        for vert_idx in vertices:
            group.add([vert_idx], 1.0, 'REPLACE')

    new_objects = []
    for i in range(len(vertex_groups)):
        group_name = f"Split_{i+1}"
        obj.vertex_groups.active_index = obj.vertex_groups[group_name].index
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.vertex_group_select()
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        new_obj = [o for o in bpy.context.selected_objects if o != obj][-1]
        new_objects.append(new_obj)

    obj_name = obj.name
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.delete()

    print("Split operation completed")
    
    master_folder_name = f"{obj_name}_baked"
    master_folder = create_master_export_folder(master_folder_name)
    
    if not master_folder:
        print("Could not create master export folder!")
        return None, None

    processed_objects = []
    total_chunks = len(new_objects)
    print_subheader(f"PROCESSING {total_chunks} CHUNKS")
    
    for i, new_obj in enumerate(new_objects, 1):
        print_header(f"PROCESSING CHUNK {i}/{total_chunks}: {new_obj.name}")
        
        log_progress("Transferring materials...", 1)
        transfer_original_data(new_obj, original_data)
        
        log_progress("Clearing previous bake data...", 1)
        for img in list(bpy.data.images):
            if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                img.user_clear()
                bpy.data.images.remove(img, do_unlink=True)
        
        log_progress("Starting bake process...", 1)
        bpy.context.view_layer.objects.active = new_obj
        unwrap_and_bake_selected(new_obj, master_folder)
        
        log_progress("Cleaning up...", 1)
        clear_bake_image_references(new_obj)
        for img in list(bpy.data.images):
            if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                img.user_clear()
                bpy.data.images.remove(img, do_unlink=True)
        
        processed_objects.append(new_obj)
        
        bpy.context.view_layer.update()
        print_subheader(f"CHUNK {i}/{total_chunks} COMPLETED")
        
    
    if 'mesh' in original_data:
        bpy.data.meshes.remove(original_data['mesh'], do_unlink=True)
    original_data.clear()
    
    return obj_name, processed_objects

def clear_bake_image_references(obj):
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if mat and mat.use_nodes:
            for node in list(mat.node_tree.nodes):
                if node.type == 'TEX_IMAGE' and node.image and any(suffix in node.image.name for suffix in ["_bake_main", "_bake_preserved"]):
                    node.image = None

def split_and_bake():
    start_time = datetime.now()
    print_header("STARTING SPLIT AND BAKE OPERATION")
    obj = bpy.context.active_object
    
    if not obj:
        log_progress("Error: No object selected")
        return
        
    log_progress("Applying modifiers...")
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for mod in obj.modifiers:
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except:
            print(f"Couldn't apply {mod.name}, removing instead")
            obj.modifiers.remove(mod)
    
    obj_name, new_objects = split_by_material_vertices(obj)
    
    if obj_name is None:
        print("No object selected or object is not a mesh.")
        return
        
    master_folder_name = f"{obj_name}_baked"
    master_folder = create_master_export_folder(master_folder_name)
    
    if not master_folder:
        print("Could not create master export folder!")
        return
    
    if new_objects:
        for new_obj in new_objects:
            mesh_data = new_obj.data
            bpy.data.objects.remove(new_obj, do_unlink=True)
            bpy.data.meshes.remove(mesh_data, do_unlink=True)
            
        bpy.context.view_layer.update()
    
    print()
    print("Checking for remaining mesh objects...")
    remaining_meshes = [obj for obj in bpy.context.scene.objects 
                       if obj.type == 'MESH' and obj.visible_get()]
    
    if remaining_meshes:
        print(f"Found {len(remaining_meshes)} remaining mesh objects to process")
        for i, rem_obj in enumerate(remaining_meshes):
            print()
            print(f"Processing remaining object {i+1} of {len(remaining_meshes)}: {rem_obj.name}")
            
            for img in list(bpy.data.images):
                if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            bpy.context.view_layer.update()
            
            bpy.context.view_layer.objects.active = rem_obj
            unwrap_and_bake_selected(rem_obj, master_folder)
            
            clear_bake_image_references(rem_obj)
            for img in list(bpy.data.images):
                if img.name.startswith(f"{rem_obj.name}_bake"):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            mesh_data = rem_obj.data
            bpy.data.objects.remove(rem_obj, do_unlink=True)
            bpy.data.meshes.remove(mesh_data, do_unlink=True)
            
            bpy.context.view_layer.update()

    if master_folder:
        save_consolidated_gdt(master_folder, obj_name)

    print_header("OPERATION COMPLETED")
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    print(f"Bake completed in {elapsed:.2f} seconds!")

split_and_bake()
