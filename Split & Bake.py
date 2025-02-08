import bpy
import os
import shutil
from mathutils import Vector
import tempfile

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
    original_obj = obj
    
    if original_obj is None or original_obj.type != 'MESH':
        print("Please select a mesh object")
        return

    export_folder = create_export_folder(master_folder, original_obj.name)
    if not export_folder:
        print("Could not create export folder!")
        return
    print(f"Created export folder: {export_folder}")

    preserve_faces = set()
    
    for poly in original_obj.data.polygons:
        if poly.material_index < len(original_obj.material_slots):
            mat = original_obj.material_slots[poly.material_index].material
            if should_preserve_uv(original_obj, mat):
                preserve_faces.add(poly.index)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for poly in original_obj.data.polygons:
        poly.select = poly.index not in preserve_faces
    bpy.ops.object.mode_set(mode='EDIT')

    bpy.ops.uv.smart_project(
        angle_limit=66.0,
        island_margin=0.00,
        correct_aspect=True,
        scale_to_bounds=True
    )
    
    bpy.ops.object.mode_set(mode='OBJECT')

    def create_black_image(name, width, height):
        img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
        black_pixels = [0.0, 0.0, 0.0, 1.0] * (width * height)
        img.pixels[:] = black_pixels
        return img

    bake_image_main = create_black_image(
        name=f"{original_obj.name}_bake_main",
        width=1024,
        height=1024
    )
    
    bake_image_preserved = create_black_image(
        name=f"{original_obj.name}_bake_preserved",
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
    bpy.context.scene.cycles.samples = 128
    bpy.context.scene.cycles.bake_type = 'DIFFUSE'
    bpy.context.scene.render.bake.use_pass_direct = True
    bpy.context.scene.render.bake.use_pass_indirect = True
    bpy.context.scene.render.bake.margin = 8
    
    if has_transparency:
        bake_image_main.alpha_mode = 'NONE'
        bake_image_preserved.alpha_mode = 'NONE'
        print("Transparency detected. Disabling alpha channel in bake.")
    
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
    
    if preserve_faces:
        bake_image_preserved.pixels[:] = [0.0, 0.0, 0.0, 1.0] * (512 * 512)
        for poly in original_obj.data.polygons:
            poly.select = poly.index in preserve_faces
        bpy.ops.object.bake(type='DIFFUSE')

    bake_image_main.pixels[:] = [0.0, 0.0, 0.0, 1.0] * (1024 * 1024)
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

def split_object_into_sixteen():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("Please select a mesh object")
        return None, None
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    verts = [v.co for v in obj.data.vertices]
    min_x = min(v.x for v in verts)
    max_x = max(v.x for v in verts)
    min_y = min(v.y for v in verts)
    max_y = max(v.y for v in verts)
    
    x_lines = [min_x + (max_x - min_x) * i / 4 for i in range(5)]
    y_lines = [min_y + (max_y - min_y) * i / 4 for i in range(5)]
    
    for group in obj.vertex_groups:
        obj.vertex_groups.remove(group)
    
    groups = []
    for i in range(16):
        group = obj.vertex_groups.new(name=f"Section_{i+1}")
        groups.append(group)
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode='OBJECT')
    
    for v in obj.data.vertices:
        co = v.co
        
        x_index = 0
        y_index = 0
        
        for i in range(4):
            if co.x >= x_lines[i] and co.x <= x_lines[i + 1]:
                x_index = i
            if co.y >= y_lines[i] and co.y <= y_lines[i + 1]:
                y_index = i
        
        group_index = x_index + (y_index * 4)
        groups[group_index].add([v.index], 1.0, 'REPLACE')
        
        threshold = 0.0001
        
        for i in range(1, 4):
            if abs(co.x - x_lines[i]) < threshold:
                left_index = (i - 1) + (y_index * 4)
                right_index = i + (y_index * 4)
                groups[left_index].add([v.index], 1.0, 'REPLACE')
                groups[right_index].add([v.index], 1.0, 'REPLACE')
        
        for i in range(1, 4):
            if abs(co.y - y_lines[i]) < threshold:
                bottom_index = x_index + ((i - 1) * 4)
                top_index = x_index + (i * 4)
                groups[bottom_index].add([v.index], 1.0, 'REPLACE')
                groups[top_index].add([v.index], 1.0, 'REPLACE')
                
        for x in range(1, 4):
            for y in range(1, 4):
                if (abs(co.x - x_lines[x]) < threshold and 
                    abs(co.y - y_lines[y]) < threshold):
                    indices = [
                        (x - 1) + ((y - 1) * 4),
                        x + ((y - 1) * 4),
                        (x - 1) + (y * 4),
                        x + (y * 4)
                    ]
                    for idx in indices:
                        groups[idx].add([v.index], 1.0, 'REPLACE')
    
    new_objects = []
    for i in range(16):
        group_name = f"Section_{i + 1}"
        obj.vertex_groups.active_index = obj.vertex_groups[group_name].index
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.vertex_group_select()
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        new_obj = [o for o in bpy.context.selected_objects if o != obj][-1]
        new_objects.append(new_obj)
    
    bpy.ops.object.select_all(action='DESELECT')
    
    obj_name = obj.name
    
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.delete()

    return obj_name, new_objects

def split_and_bake():
    obj_name, new_objects = split_object_into_sixteen()
    
    if obj_name is None:
        print("No object selected or object is not a mesh.")
        return
    
    master_folder_name = f"{obj_name}_baked"
    master_folder = create_master_export_folder(master_folder_name)
    
    if not master_folder:
        print("Could not create master export folder!")
        return
    
    if new_objects:
        for i, new_obj in enumerate(new_objects):
            print(f"Processing object {i+1} of {len(new_objects)}")
            
            for img in list(bpy.data.images):
                if any(name in img.name for name in ['_bake_main', '_bake_preserved']):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            bpy.context.view_layer.update()
            
            bpy.context.view_layer.objects.active = new_obj
            unwrap_and_bake_selected(new_obj, master_folder)
            
            for img in list(bpy.data.images):
                if img.name.startswith(f"{new_obj.name}_bake"):
                    img.user_clear()
                    bpy.data.images.remove(img, do_unlink=True)
            
            mesh_data = new_obj.data
            bpy.data.objects.remove(new_obj, do_unlink=True)
            bpy.data.meshes.remove(mesh_data, do_unlink=True)
            
            
            bpy.context.view_layer.update()
    else:
        print("No objects were created during the split operation.")

split_and_bake()
