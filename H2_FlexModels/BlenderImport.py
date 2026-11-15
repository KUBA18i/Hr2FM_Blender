import bpy, re, struct, bmesh
from bisect import bisect_left
import numpy as np
from pathlib import Path
from .H2FM_IO import ReadFM
from .H2FMtags import import_references, import_skeleton
from .H2FMtags import MESHNODE_NAME_PREFIX
from .H2_TexM8 import M8ToRGBA

def _command_triangles(cmd):
    v = cmd.vertices
    n = len(v)
    if cmd.count == 0 or n < 3:
        return
    if cmd.count < 0: #fan
        hub = v[0]
        for i in range(1, n - 1):
            yield (hub, v[i + 1], v[i])
    else: #strip
        for i in range(n - 2):
            if i % 2 == 0:
                yield (v[i], v[i + 2], v[i + 1])
            else:
                yield (v[i], v[i + 1], v[i + 2])

def _geometry_from_gl(fm_data):
    faces, uvs = [], []
    for cmd in fm_data.glCommands:
        for tri in _command_triangles(cmd):
            faces.append(tuple(v.vertexIndex for v in tri))
            for v in tri:
                uvs.append((v.s, 1.0 - v.t))
    return faces, uvs

def _geometry_from_triangles(fm_data):
    w = fm_data.header.skinwidth or 256
    h = fm_data.header.skinheight or 256
    faces, uvs = [], []
    for tri in fm_data.triangles:
        vi, ti = tri.vertexIndices, tri.textureIndices
        faces.append((vi[0], vi[2], vi[1]))
        for k in (0, 2, 1):
            if 0 <= ti[k] < len(fm_data.uv):
                uv = fm_data.uv[ti[k]]
                uvs.append((uv.s / w, 1.0 - uv.t / h))
            else:
                uvs.append((0.0, 0.0))
    return faces, uvs

def _node_command_ranges(fm_data):
    cmds = fm_data.glCommands
    offsets, off = [], 0
    for c in cmds:
        offsets.append(off)
        off += 1 + 3 * len(c.vertices)
    boundaries = set(offsets)
    boundaries.add(off)

    ranges, ok = [], True
    for mn in fm_data.meshNodes:
        lo, hi = mn.start_glcmds, mn.start_glcmds + mn.num_glcmds
        if hi < lo or lo not in boundaries or hi not in boundaries:
            ok = False
            break
        ranges.append(range(bisect_left(offsets, lo), bisect_left(offsets, hi)))
    if ok and sum(len(r) for r in ranges) == len(cmds):
        return ranges

    print("Warning: mesh node start/num values don't match the GL command layout; splitting at terminators instead.")
    ranges, start = [], 0
    for i, c in enumerate(cmds):
        if c.count == 0:
            ranges.append(range(start, i + 1))
            start = i + 1
    if start < len(cmds):
        ranges.append(range(start, len(cmds)))
    ranges += [range(0)] * (len(fm_data.meshNodes) - len(ranges))
    return ranges

def _node_vertex_sets(fm_data):
    cmds = fm_data.glCommands
    return [
        {v.vertexIndex for k in r for v in cmds[k].vertices}
        for r in _node_command_ranges(fm_data)
    ]

def _gl_face_nodes(fm_data):
    cmd_node = {}
    for node_idx, r in enumerate(_node_command_ranges(fm_data)):
        for k in r:
            cmd_node[k] = node_idx
    face_nodes = []
    for k, cmd in enumerate(fm_data.glCommands):
        n_tris = sum(1 for _ in _command_triangles(cmd))
        face_nodes.extend([cmd_node.get(k, -1)] * n_tris)
    return face_nodes

def _triangle_block_face_nodes(fm_data):
    gl_faces, _ = _geometry_from_gl(fm_data)
    lookup = {}
    for face, node in zip(gl_faces, _gl_face_nodes(fm_data)):
        lookup.setdefault(tuple(sorted(face)), []).append(node)
    out = []
    for tri in fm_data.triangles:
        nodes = lookup.get(tuple(sorted(tri.vertexIndices)))
        out.append(nodes.pop(0) if nodes else -1)
    return out

def _find_m8(skin_path: str, search_dir: Path):
    if not skin_path:
        return None
    stem = Path(skin_path.replace("\\", "/")).stem.lower()
    for f in search_dir.iterdir():
        if f.is_file() and f.suffix.lower() == ".m8" and f.stem.lower() == stem:
            return f
    return None

def _load_m8_image(m8_path: Path):
    name = m8_path.name[:63]
    img = bpy.data.images.get(name)
    if img is not None:
        return img
    try:
        w, h, rgba = M8ToRGBA(m8_path)
    except Exception as e:
        print(f"Warning: couldn't read '{m8_path}': {e}")
        return None
    img = bpy.data.images.new(name, width=w, height=h, alpha=False)
    img.pixels.foreach_set(rgba)
    img.update()
    img.pack()
    return img

def _get_or_create_material(skin_path: str, search_dir: Path, ImportTextures: bool):
    name = (skin_path or "H2FM_Material")[:63]
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        nodes.clear()
        diffuse = nodes.new(type='ShaderNodeBsdfDiffuse')
        out = nodes.new(type='ShaderNodeOutputMaterial')
        out.location = (200, 0)
        links.new(diffuse.outputs['BSDF'], out.inputs['Surface'])
        if ImportTextures:
            m8_path = _find_m8(skin_path, search_dir)
            if m8_path is None:
                print(f"No .m8 found for skin '{skin_path}' in {search_dir}")
            else:
                img = _load_m8_image(m8_path)
                if img is not None:
                    tex = nodes.new(type='ShaderNodeTexImage')
                    tex.image = img
                    tex.interpolation = 'Closest'
                    tex.location = (-300, 0)
                    links.new(tex.outputs['Color'], diffuse.inputs['Color'])
    return mat

def _import_animation(obj, fm_data, marker_mode: bool):
    basis_key = obj.shape_key_add(name="Basis")
    basis_key.value = 0.0

    scene = bpy.context.scene
    scene.frame_start = 0

    for f_idx, frame in enumerate(fm_data.frames):
        key_name = frame.name if frame.name else f"Frame_{f_idx:03d}"
        s_key = obj.shape_key_add(name=key_name, from_mix=False)
        s_key.relative_key = basis_key
        s_key.value = 0.0

        f_scale = frame.scale
        f_translate = frame.translate
        for v_i, v in enumerate(frame.vertices):
            s_key.data[v_i].co = (
                v.vertex[0] * f_scale[0] + f_translate[0],
                v.vertex[1] * f_scale[1] + f_translate[1],
                v.vertex[2] * f_scale[2] + f_translate[2])

        s_key.value = 0.0
        s_key.keyframe_insert(data_path="value", frame=max(0, f_idx - 1))
        s_key.value = 1.0
        s_key.keyframe_insert(data_path="value", frame=f_idx)
        s_key.value = 0.0
        s_key.keyframe_insert(data_path="value", frame=f_idx + 1)

    scene.frame_end = len(fm_data.frames) - 1

    if marker_mode:
        mark = scene.timeline_markers
        mark.clear()
        last_name = ""
        for f_idx, frame in enumerate(fm_data.frames):
            raw = frame.name if frame.name else f"frame_{f_idx}"
            base = raw.rstrip("0123456789_")
            if base and base != last_name:
                mark.new(name=base, frame=f_idx)
                last_name = base

    obj.active_shape_key_index = 0


def import_fm_file(filepath: str | Path, base_frame_index: int, UVsFromGLCommands: bool, ImportAnimations: bool, TimelineMarkersFromFrames: bool, ImportReferences: bool, ImportSkeleton: bool, ImportTextures:bool):
    filepath = Path(filepath)
    fm_data = ReadFM(filepath)

    if not fm_data.frames:
        print("Error: No frames found in the FM file.")
        return None

    #Base frame vertex positions
    base_idx = min(max(0, base_frame_index), len(fm_data.frames) - 1)
    base_frame = fm_data.frames[base_idx]
    sx, sy, sz = base_frame.scale
    tx, ty, tz = base_frame.translate
    base_vertices = [
        (v.vertex[0] * sx + tx, v.vertex[1] * sy + ty, v.vertex[2] * sz + tz)
        for v in base_frame.vertices
    ]

    #Faces and UVs
    #Note: Triangle winding here is reversed on purpose, since the game's winding is flipped relative to Blender's.
    if UVsFromGLCommands:
        faces, uv_loops = _geometry_from_gl(fm_data)
    else:
        faces, uv_loops = _geometry_from_triangles(fm_data)

    #Create mesh object
    mesh_name = filepath.stem
    mesh = bpy.data.meshes.new(mesh_name)
    obj = bpy.data.objects.new(mesh_name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    mesh.from_pydata(base_vertices, [], faces)
    mesh.update()

    #UV loops
    uv_layer = mesh.uv_layers.new(name="H2FM_UVMap")
    if len(uv_loops) == len(mesh.loops):
        uv_layer.data.foreach_set("uv", [c for uv in uv_loops for c in uv])
    else:
        print(f"Warning: {len(uv_loops)} UVs for {len(mesh.loops)} loops; UVs skipped.")

    #Materials (in H2, all polys share the same skin)
    skins = fm_data.skins if fm_data.skins else [""]
    for skin_path in skins:
        obj.data.materials.append(_get_or_create_material(skin_path, filepath.parent, ImportTextures))

    #Below is a debug feature: faces get a Mesh Node attribute that can be viewed in the GeoNodes tab.
    #This is helpful when a vertex belongs to multiple Mesh Nodes/Vertex Groups.
    face_nodes = _gl_face_nodes(fm_data) if UVsFromGLCommands else _triangle_block_face_nodes(fm_data)
    if len(face_nodes) == len(mesh.polygons):
        attr = mesh.attributes.new(name="fm_meshnode", type='INT', domain='FACE')
        attr.data.foreach_set("value", face_nodes)

    # Mesh nodes -> vertex groups (empty nodes get an empty group)
    for node_idx, vert_set in enumerate(_node_vertex_sets(fm_data)):
        vg = obj.vertex_groups.new(name=f"{MESHNODE_NAME_PREFIX}{node_idx}")
        valid = [v for v in vert_set if 0 <= v < len(base_vertices)]
        if valid:
            vg.add(valid, 1.0, 'REPLACE')

    # Reference points / skeleton joints -> empties, skeleton clusters -> vertex groups
    if ImportReferences:
        import_references(obj, fm_data, base_idx, ImportAnimations)
    if ImportSkeleton:
        import_skeleton(obj, fm_data, base_idx, ImportAnimations)

    if ImportAnimations:
        _import_animation(obj, fm_data, TimelineMarkersFromFrames)

    print(f"Successfully imported '{mesh_name}'.")
    return obj


