import bpy
import os
import shutil
from mathutils import Vector
import tempfile
from datetime import datetime

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
    
    export_folder = os.path.join(master_folder, f"{obj_name}_bake")
    os.makedirs(export_folder, exist_ok=True)
    return export_folder

def export_to_xmodel(filepath, obj):
    # Final verification before export
    vert_count = len(obj.data.vertices)
    if vert_count > 65534:
        print(f"EMERGENCY: {obj.name} has {vert_count} vertices - performing last-minute split")
        verify_and_split_if_needed(obj)
        return False
    
    # Pre-export cleanup
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # Apply all modifiers
    for mod in obj.modifiers:
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except:
            print(f"Couldn't apply {mod.name}, removing instead")
            obj.modifiers.remove(mod)
    
    # Force triangulation
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode='OBJECT')
    
    export_dir = os.path.dirname(filepath)
    os.makedirs(export_dir, exist_ok=True)
    
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    try:
        result = bpy.ops.export_scene.xmodel(
            filepath=filepath,
            check_existing=True,
            target_format='XMODEL_BIN',
            version='7',
            use_selection=True,
            apply_unit_scale=True,
            use_vertex_colors=True,
            use_vertex_cleanup=True,
            apply_modifiers=True,
            modifier_quality='PREVIEW',
            use_armature=True,
            use_weight_min=True,
            use_weight_min_threshold=0.001
        )
        return result == {'FINISHED'}
    except Exception as e:
        print(f"Export error: {str(e)}")
        return False

def create_blank_image(name, width, height):
    img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
    pixels = [0.0] * (width * height * 4)
    img.pixels = pixels
    return img

def unwrap_and_bake_selected(obj, master_folder):
    print_header("STARTING BAKE PROCESS")
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

    # Ensure proper selection before UV unwrapping
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')  # Select all faces first
    
    # Check if we have any faces to unwrap
    if len(obj.data.polygons) == 0:
        log_progress("Error: Object has no faces to unwrap")
        return
        
    # Ensure we're in face select mode
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    
    # Mark seams for better unwrapping
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.mark_seam(clear=True)  # Clear existing seams
    bpy.ops.mesh.mark_sharp(clear=True)  # Clear existing sharp edges
    
    try:
        bpy.ops.uv.smart_project(
            angle_limit=45.0,
            island_margin=0.03,
            area_weight=0.7,
            correct_aspect=True,
            scale_to_bounds=True
        )
    except RuntimeError as e:
        log_progress(f"UV unwrapping failed: {str(e)}")
        # Try basic unwrap as fallback
        try:
            bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.03)
        except:
            log_progress("Both UV unwrapping methods failed!")
            return
    
    bpy.ops.object.mode_set(mode='OBJECT')

    def create_black_image(name, width, height):
        img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
        # Create a list of black pixels with alpha
        pixels = [0.0, 0.0, 0.0, 1.0] * (width * height)
        # Convert to float array and assign
        img.pixels.foreach_set(pixels)
        return img

    bake_image_main = create_black_image(
        name=f"{original_obj.name}_bake_main",
        width=1024,  # Increased from 2048 for better quality
        height=1024
    )
    
    bake_image_preserved = create_black_image(
        name=f"{original_obj.name}_bake_preserved",
        width=1024,  # Increased from 512 for better quality
        height=1024
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
    bpy.context.scene.cycles.samples = 512  # Increased from 256
    bpy.context.scene.cycles.bake_type = 'DIFFUSE'
    bpy.context.scene.render.bake.use_pass_direct = True
    bpy.context.scene.render.bake.use_pass_indirect = True
    bpy.context.scene.render.bake.margin = 32  # Increased from 16
    bpy.context.scene.render.bake.use_selected_to_active = False
    bpy.context.scene.render.bake.use_clear = True
    bpy.context.scene.render.bake.target = 'IMAGE_TEXTURES'
    
    # Add cage settings for better projection
    bpy.context.scene.render.bake.use_cage = True
    bpy.context.scene.render.bake.cage_extrusion = 0.05  # Reduced from 0.1 for more precision
    
    # Add anti-aliasing settings
    bpy.context.scene.cycles.use_adaptive_sampling = True
    bpy.context.scene.cycles.adaptive_threshold = 0.01
    bpy.context.scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    
    # Add padding between UV islands
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.pack_islands(margin=0.05)  # Increased UV island margin
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
    
    print_subheader("BAKING TEXTURES")
    if preserve_faces:
        log_progress("Baking preserved UV areas...", 1)
        # Initialize black pixels for preserved image
        black_pixels = [0.0, 0.0, 0.0, 1.0] * (1024 * 1024)  # Updated size
        bake_image_preserved.pixels.foreach_set(black_pixels)
        for poly in original_obj.data.polygons:
            poly.select = poly.index in preserve_faces
        bpy.ops.object.bake(type='DIFFUSE')

    log_progress("Baking main texture...", 1)
    # Initialize black pixels for main image
    black_pixels = [0.0, 0.0, 0.0, 1.0] * (1024 * 1024)  # Updated size
    bake_image_main.pixels.foreach_set(black_pixels)
    for poly in original_obj.data.polygons:
        poly.select = poly.index not in preserve_faces
    bpy.ops.object.bake(type='DIFFUSE')
    
    main_path = os.path.join(export_folder, f"{original_obj.name}_bake_main.png")
    try:
        bake_image_main.save_render(filepath=main_path)
        print(f"Main texture saved to: {main_path}")
    except Exception as e:
        print(f"Error saving main texture: {e}")

    xmodel_path = os.path.join(export_folder, f"{original_obj.name}_baked.XMODEL_BIN")
    try:
        if export_to_xmodel(xmodel_path, original_obj):
            print(f"XMODEL_BIN file saved to: {xmodel_path}")
        else:
            print("Failed to export XMODEL_BIN file")
    except Exception as e:
        print(f"Error saving XMODEL_BIN file: {e}")

def verify_and_split_if_needed(obj):
    MAX_SAFE_VERTICES = 12000  # Even more conservative for OSRS terrain
    ABSOLUTE_MAX = 60000  # Far below 65534 for safety margin
    
    def optimize_mesh(obj):
        print(f"Optimizing mesh for {obj.name}")
        bpy.context.view_layer.objects.active = obj
        
        # Clean up mesh before processing
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.001)  # Increased threshold for OSRS models
        bpy.ops.mesh.dissolve_degenerate()  # Remove bad geometry
        bpy.ops.mesh.delete_loose()  # Remove floating vertices
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return len(obj.data.vertices)

    def force_decimation(obj, target_ratio=None):
        print(f"Applying aggressive decimation to {obj.name}")
        bpy.context.view_layer.objects.active = obj
        
        current_verts = len(obj.data.vertices)
        if target_ratio is None:
            target_ratio = (ABSOLUTE_MAX * 0.90) / current_verts  # 90% of limit
        
        # First try planar decimation
        modifier = obj.modifiers.new(name="Planar", type='DECIMATE')
        modifier.decimate_type = 'DISSOLVE'
        modifier.angle_limit = 0.087  # 5 degrees
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        
        # If still too high, use collapse decimation
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
        
        # Try optimization first
        optimize_mesh(obj)
        if len(obj.data.vertices) <= MAX_SAFE_VERTICES:
            return True
            
        # Multi-pass splitting
        for attempt in range(3):  # Try up to 3 times
            if len(obj.data.vertices) <= MAX_SAFE_VERTICES:
                break
                
            for axis in [2, 0, 1]:  # Z, X, Y axes
                bounds = [obj.matrix_world @ Vector(coord) for coord in obj.bound_box]
                min_val = min(v[axis] for v in bounds)
                max_val = max(v[axis] for v in bounds)
                mid = (min_val + max_val) / 2
                
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                plane_no = [0, 0, 0]
                plane_no[axis] = 1
                
                # Try different split positions if needed
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
                        
                        # Recursively process both parts
                        verify_and_split_if_needed(obj)
                        verify_and_split_if_needed(new_objs[0])
                        return True
        
        # If splitting failed, force decimation
        print("Split failed, forcing decimation")
        force_decimation(obj, target_ratio=0.85)  # More aggressive ratio
        return True

    # Initial cleanup and check
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

def split_by_material_vertices(obj):
    print_header("STARTING MATERIAL SPLIT")
    MAX_VERTICES = 12000  # Match the new MAX_SAFE_VERTICES
    
    if not obj or obj.type != 'MESH':
        log_progress("Error: Please select a mesh object")
        return None, None

    # Apply transformations and clean mesh
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode='OBJECT')

    # Build efficient lookup structures
    vert_to_polys = {i: [] for i in range(len(obj.data.vertices))}
    vert_to_mats = {i: set() for i in range(len(obj.data.vertices))}
    
    for poly in obj.data.polygons:
        mat_index = poly.material_index
        for vert_idx in poly.vertices:
            vert_to_polys[vert_idx].append(poly.index)
            vert_to_mats[vert_idx].add(mat_index)

    # Create groups
    vertex_groups = []
    current_group = set()
    processed_verts = set()
    
    for mat_index in range(len(obj.material_slots)):
        
        # Get all vertices using this material
        material_verts = {v for v, mats in vert_to_mats.items() if mat_index in mats}
        material_verts -= processed_verts
        
        for vert_idx in material_verts:
            if len(current_group) >= MAX_VERTICES:
                if current_group:
                    vertex_groups.append(current_group)
                current_group = set()
            
            current_group.add(vert_idx)
            processed_verts.add(vert_idx)
            
            # Add connected vertices that share the material
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
        log_progress(f"Processing group {i + 1}/{len(vertex_groups)}", 1)
        group = obj.vertex_groups.new(name=f"Split_{i+1}")
        for vert_idx in vertices:
            group.add([vert_idx], 1.0, 'REPLACE')

    # Separate by vertex groups
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

    # Clean up original object
    obj_name = obj.name
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.delete()

    print("Split operation completed")
    
    # Verify and potentially split large objects further
    final_objects = []
    for new_obj in new_objects:
        if verify_and_split_if_needed(new_obj):
            # If object was split, add all visible objects that aren't the original
            final_objects.extend([o for o in bpy.context.visible_objects 
                               if o.type == 'MESH' and o not in new_objects])
        else:
            final_objects.append(new_obj)
    
    return obj_name, final_objects

def clear_bake_image_references(obj):
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if mat and mat.use_nodes:
            for node in list(mat.node_tree.nodes):
                if node.type == 'TEX_IMAGE' and node.image and any(suffix in node.image.name for suffix in ["_bake_main", "_bake_preserved"]):
                    node.image = None

def split_and_bake():
    start_time = datetime.now()  # Track start time
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
    
    print_subheader("PROCESSING OBJECTS")
    if new_objects:
        total_objects = len(new_objects)
        for i, new_obj in enumerate(new_objects, 1):
            log_progress(f"Baking object {i} of {total_objects}...", 1)
            
            for img in list(bpy.data.images):
                if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            bpy.context.view_layer.update()
            
            bpy.context.view_layer.objects.active = new_obj
            unwrap_and_bake_selected(new_obj, master_folder)
            
            clear_bake_image_references(new_obj)
            for img in list(bpy.data.images):
                if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            mesh_data = new_obj.data
            bpy.data.objects.remove(new_obj, do_unlink=True)
            bpy.data.meshes.remove(mesh_data, do_unlink=True)
            
            bpy.context.view_layer.update()
    else:
        print("No objects were created during the split operation.")
    
    # Add new code to handle remaining mesh objects
    print()
    print("Checking for remaining mesh objects...")
    remaining_meshes = [obj for obj in bpy.context.scene.objects 
                       if obj.type == 'MESH' and obj.visible_get()]
    
    if remaining_meshes:
        print(f"Found {len(remaining_meshes)} remaining mesh objects to process")
        for i, rem_obj in enumerate(remaining_meshes):
            print()
            print(f"Processing remaining object {i+1} of {len(remaining_meshes)}: {rem_obj.name}")
            
            # Clear any existing bake images
            for img in list(bpy.data.images):
                if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            bpy.context.view_layer.update()
            
            # Process the remaining object
            bpy.context.view_layer.objects.active = rem_obj
            unwrap_and_bake_selected(rem_obj, master_folder)
            
            clear_bake_image_references(rem_obj)
            for img in list(bpy.data.images):
                if img.name.startswith(f"{rem_obj.name}_bake"):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            # Clean up the object
            mesh_data = rem_obj.data
            bpy.data.objects.remove(rem_obj, do_unlink=True)
            bpy.data.meshes.remove(mesh_data, do_unlink=True)
            
            bpy.context.view_layer.update()

    print_header("OPERATION COMPLETED")
    end_time = datetime.now()  # Track end time
    elapsed = (end_time - start_time).total_seconds()
    print(f"Bake completed in {elapsed:.2f} seconds!")

split_and_bake()