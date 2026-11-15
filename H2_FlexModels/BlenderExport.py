import re, bpy
from pathlib import Path
import numpy as np
from typing import Final
from .H2FM_IO import WriteFM
from .H2FMtypes import (
    h2_fm_startheader_t,
    h2_fm_Placement_t,
    h2_fm_stvert_t,
    h2_fm_triangle_t,
    h2_fm_triangleVertex_t,
    h2_fm_meshnode_t,
    h2_fm_frame_t,
    h2_fm_ReferenceBlock_t,
    h2_fm_SkeletalCluster_t,
    h2_fm_SkeletonFrame_t,
    h2_fm_SkeletonBlock_t,
    h2_fm_glCommandVertex_t,
    h2_fm_glCommand_t,
    H2_FM_file,
)
from .H2FMnormals import light_normal_indices
from .H2FMtags import (
    PLACEMENT_AXIS_LENGTH,
    REF_NAME_PREFIX, JOINT_NAME_PREFIX, CLUSTER_NAME_PREFIX, MESHNODE_NAME_PREFIX,
    REFERENCE_COUNTS, SKELETON_JOINT_COUNTS,
)
from .H2_TexM8 import RGBToM8Data, WriteM8

INT16_MAX: Final = 32767
BITMASK_BITS: Final = 2048
MAX_GL_COMMAND_VERTS: Final = None

def _build_commands(tris, max_verts=None):
    edges = {}
    for t, (a, b, c) in enumerate(tris):
        for p, q, r in ((a, b, c), (b, c, a), (c, a, b)):
            edges.setdefault((p, q), []).append((t, r))
    used = [False] * len(tris)

    def find(p, q, in_cmd):
        for t, r in edges.get((p, q), ()):
            if not used[t] and t not in in_cmd:
                return t, r
        return None

    def full(verts):
        return max_verts is not None and len(verts) >= max_verts

    def strip(t0, a, b, c):
        verts, members = [a, b, c], {t0}
        while not full(verts):
            n = len(verts)
            p, q = (verts[-2], verts[-1]) if (n - 2) % 2 == 0 else (verts[-1], verts[-2])
            hit = find(p, q, members)
            if hit is None:
                break
            members.add(hit[0])
            verts.append(hit[1])
        return members, verts

    def fan(t0, hub, b, c):
        verts, members = [hub, b, c], {t0}
        while not full(verts):
            hit = find(hub, verts[-1], members)
            if hit is None:
                break
            members.add(hit[0])
            verts.append(hit[1])
        return members, verts

    commands = []
    for i, (a, b, c) in enumerate(tris):
        if used[i]:
            continue
        best = None
        for rot in ((a, b, c), (b, c, a), (c, a, b)):
            for is_fan, grow in ((False, strip), (True, fan)):
                members, verts = grow(i, *rot)
                if best is None or len(members) > len(best[1]):
                    best = (is_fan, members, verts)
        is_fan, members, verts = best
        for t in members:
            used[t] = True
        commands.append((is_fan, verts))
    return commands

def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else np.array([1.0, 0.0, 0.0])

def _encode_placement(mat, frame):
    sc = np.array(frame.scale)
    tr = np.array(frame.translate)
    o = np.array(mat[:3, 3], dtype=np.float64)
    x = _unit(np.array(mat[:3, 0], dtype=np.float64))
    z = np.array(mat[:3, 2], dtype=np.float64)
    z = _unit(z - np.dot(z, x) * x)
    L = PLACEMENT_AXIS_LENGTH
    return h2_fm_Placement_t(
        origin=((o - tr) / sc).tolist(),
        direction=((o + L * x - tr) / sc).tolist(),
        up=((o + L * z - tr) / sc).tolist(),
    )

def build_frame_names(count: int, use_markers: bool, start: int) -> list[str]:
    scene = bpy.context.scene
    markers = sorted(scene.timeline_markers, key=lambda m: m.frame) if use_markers else []
    names = []
    for i in range(count):
        name = f"frame{i}"
        if markers:
            tl_frame = start + i
            current = None
            for m in markers:
                if m.frame <= tl_frame:
                    current = m
                else:
                    break
            if current is not None:
                n = tl_frame - current.frame + 1
                suffix = f"{n:02d}"
                base = current.name.strip().replace(" ", "_")
                name = base[:15 - len(suffix)] + suffix
        names.append(name[:15])
    return names

def _material_image(mat):
    img = None
    if mat is not None:
        if mat.use_nodes and mat.node_tree:
            nodes = mat.node_tree.nodes
            active = nodes.active
            if active is not None and active.type == 'TEX_IMAGE' and active.image:
                img = active.image
            else:
                for n in nodes:
                    if n.type == 'TEX_IMAGE' and n.image:
                        img = n.image
                        break
        if img is None:
            img = bpy.data.images.get(mat.name) or bpy.data.images.get(Path(mat.name).name)
    return img

def _material_skin_size(mat) -> tuple[int, int]:
    img = _material_image(mat)
    if img is not None:
        w, h = img.size
        if w > 0 and h > 0:
            return int(w), int(h)
        print(f"Warning: image '{img.name}' has no pixel data; assuming 256x256.")
    return 256, 256

#Function to have 'part2' before 'part10'.
def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]

def _collect_objects(objs):
    if isinstance(objs, bpy.types.Object):
        objs = [objs]
    found = {}
    for o in objs:
        if o is None:
            continue
        found.setdefault(o.name, o)
        if o.type == 'MESH':
            for c in o.children_recursive:
                if c.type == 'EMPTY':
                    found.setdefault(c.name, c)
    meshes = sorted((o for o in found.values() if o.type == 'MESH'), key=lambda o: _natural_key(o.name))
    refs, joints = {}, {}
    for o in found.values():
        if o.type != 'EMPTY':
            continue
        for prefix, target in ((REF_NAME_PREFIX, refs), (JOINT_NAME_PREFIX, joints)):
            m = re.match(re.escape(prefix) + r"(\d+)", o.name)
            if m:
                idx = int(m.group(1))
                if idx in target:
                    raise RuntimeError(f"'{target[idx].name}' and '{o.name}' are both {prefix}{idx}.")
                target[idx] = o
    return meshes, refs, joints

def _read_topology(obj, me, want_clusters: bool, want_nodes: bool):
    me.calc_loop_triangles()
    n_tri = len(me.loop_triangles)
    tv = np.empty(n_tri * 3, dtype=np.int32)
    tl = np.empty(n_tri * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tv)
    me.loop_triangles.foreach_get("loops", tl)

    uv_layer = me.uv_layers.active
    if uv_layer is None:
        raise RuntimeError(f"'{obj.name}' has no UV map.")
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    uv_layer.data.foreach_get("uv", uv)
    tri_uv = uv.reshape(-1, 2)[tl.reshape(-1, 3)]

    def groups_by_prefix(prefix):
        found = {}
        for vg in obj.vertex_groups:
            m = re.match(re.escape(prefix) + r"(\d+)", vg.name)
            if m:
                found[vg.index] = int(m.group(1))
        return found

    wanted = {}
    if want_clusters:
        wanted["clusters"] = groups_by_prefix(CLUSTER_NAME_PREFIX)
    if want_nodes:
        wanted["node_groups"] = groups_by_prefix(MESHNODE_NAME_PREFIX)
    lists = {key: {k: [] for k in table.values()} if key == "node_groups" else {} for key, table in wanted.items()}
    if any(wanted.values()):
        for v in me.vertices:
            for g in v.groups:
                if g.weight > 0.0:
                    for key, table in wanted.items():
                        if g.group in table:
                            lists[key].setdefault(table[g.group], []).append(v.index)
    materials = [s.material for s in obj.material_slots if s.material]
    return {
        "num_verts": len(me.vertices), "tris": tv.reshape(-1, 3), "tri_uv": tri_uv,
        "clusters": lists.get("clusters", {}), "node_groups": lists.get("node_groups", {}),
        "materials": materials,
    }

def _image_rgb8(img) -> np.ndarray:
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    rgb = np.flipud(px.reshape(h, w, 4)[..., :3])
    rgb = np.clip(rgb, 0.0, 1.0)
    if img.is_float:
        rgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    return np.rint(rgb * 255.0).astype(np.uint8)

def _export_textures(folder: Path, topo):
    done = set()
    for t in topo:
        for mat in t["materials"]:
            skin = re.sub(r"\.\d{3}$", "", mat.name)
            stem = Path(skin.replace("\\", "/")).stem
            if not stem or stem in done:
                continue
            done.add(stem)
            img = _material_image(mat)
            if img is None:
                print(f"Texture: no image found for material '{mat.name}', skipped.")
                continue
            w, h = img.size
            if w == 0 or h == 0:
                print(f"Texture: image '{img.name}' has no pixel data, skipped.")
                continue
            if (w & (w - 1)) or (h & (h - 1)):
                print(f"Warning: '{img.name}' is {w}x{h}, not a power of two; mip levels will have odd sizes.")
            mipmaps, palette = RGBToM8Data(_image_rgb8(img))
            out = folder / f"{stem}.m8"
            WriteM8(out, stem[:31], mipmaps, palette)
            print(f"Texture: wrote '{out.name}' ({w}x{h}, {len(mipmaps)} mip levels).")

def export_fm_file(filepath, objs, ReferenceType: int, SkeletonType: int, ExportAnimations: bool, MarkerFrameNames: bool, StartAnimFrame: int, EndAnimFrame: int, MeshNodesFromVertexGroups: bool, ExportTextures: bool):
    filepath = Path(filepath)
    meshes, ref_empties, joint_empties = _collect_objects(objs)
    if not meshes:
        raise RuntimeError("No mesh objects to export.")
    if not ExportAnimations:
        StartAnimFrame = EndAnimFrame = bpy.context.scene.frame_current
        MarkerFrameNames = False
    if EndAnimFrame < StartAnimFrame:
        raise RuntimeError("End frame must be >= start frame.")
    if ReferenceType < 0:
        ref_empties = {}
    if SkeletonType < 0:
        joint_empties = {}

    scene = bpy.context.scene
    original_frame = scene.frame_current
    topo = [None] * len(meshes)
    coords = [[] for _ in meshes]
    ref_mats = {i: [] for i in ref_empties}
    joint_mats = {i: [] for i in joint_empties}

    try:
        for f in range(StartAnimFrame, EndAnimFrame + 1):
            scene.frame_set(f)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            for mi, obj in enumerate(meshes):
                eval_obj = obj.evaluated_get(depsgraph)
                me = eval_obj.to_mesh()
                try:
                    if topo[mi] is None:
                        topo[mi] = _read_topology(obj, me, SkeletonType >= 0, MeshNodesFromVertexGroups)
                    elif len(me.vertices) != topo[mi]["num_verts"]:
                        raise RuntimeError(f"'{obj.name}': vertex count changes at frame {f}: ({len(me.vertices)} vs {topo[mi]['num_verts']}). FM needs a constant count.")
                    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
                    me.vertices.foreach_get("co", co)
                    m = np.array(eval_obj.matrix_world)
                    coords[mi].append(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
                finally:
                    eval_obj.to_mesh_clear()
            for empties, store in ((ref_empties, ref_mats), (joint_empties, joint_mats)):
                for i, e in empties.items():
                    store[i].append(np.array(e.evaluated_get(depsgraph).matrix_world))
    finally:
        scene.frame_set(original_frame)

    #Concatenate the objects
    offsets = np.cumsum([0] + [t["num_verts"] for t in topo])
    all_coords = np.concatenate([np.stack(c) for c in coords], axis=1)          # (F, V, 3)
    all_tris = np.concatenate([t["tris"] + offsets[i] for i, t in enumerate(topo)])
    all_uvs = np.concatenate([t["tri_uv"] for t in topo])

    #Mesh nodes
    if MeshNodesFromVertexGroups:
        node_verts = {}
        for i, t in enumerate(topo):
            for n, verts in t["node_groups"].items():
                node_verts.setdefault(n, []).extend(v + int(offsets[i]) for v in verts)
        if not node_verts:
            raise RuntimeError(f"No {MESHNODE_NAME_PREFIX}# vertex groups found on the exported meshes.")
        num_nodes = max(node_verts) + 1
        member = np.zeros((all_coords.shape[1], num_nodes), dtype=bool)
        for n, verts in node_verts.items():
            member[verts, n] = True
        count = member[all_tris].sum(axis=1)
        full = count == 3
        all_nodes = np.where(full.any(axis=1), full.argmax(axis=1), np.where(count.any(axis=1), count.argmax(axis=1), 0))
        spanning = int((~full.any(axis=1) & count.any(axis=1)).sum())
        outside = int((~count.any(axis=1)).sum())
        if spanning or outside:
            print(f"Note: {spanning} triangle(s) span several mesh node groups (put in the group with most corners), {outside} are in no group (put in node 0).")
    else:
        all_nodes = np.zeros(len(all_tris), dtype=np.int64)
        num_nodes = 1

    #Skins
    skins, skin_size = [], None
    for t in topo:
        for mat in t["materials"]:
            name = re.sub(r"\.\d{3}$", "", mat.name) #drop Blender's duplicate suffix
            if name not in skins:
                skins.append(name)
            size = _material_skin_size(mat)
            if skin_size is None:
                skin_size = size
            elif size != skin_size:
                print(f"Warning: material '{mat.name}' is {size[0]}x{size[1]}, using {skin_size[0]}x{skin_size[1]}.")
    if not skins:
        skins = ["default_skin.m8"]
    skin_size = skin_size or (256, 256)

    #Skeleton clusters
    clusters = {}
    for i, t in enumerate(topo):
        for k, verts in t["clusters"].items():
            clusters.setdefault(k, []).extend(v + int(offsets[i]) for v in verts)

    names = build_frame_names(EndAnimFrame - StartAnimFrame + 1, MarkerFrameNames, StartAnimFrame)
    fm = build_fm(all_coords, all_tris, all_uvs, all_nodes, num_nodes, skins, skin_size, names,
                  ref_type=ReferenceType, ref_mats={i: np.stack(m) for i, m in ref_mats.items()},
                  skeleton_type=SkeletonType, clusters=clusters,
                  joint_mats={i: np.stack(m) for i, m in joint_mats.items()})

    n_fan = sum(1 for c in fm.glCommands if c.count < 0)
    n_strip = sum(1 for c in fm.glCommands if c.count > 0)
    print(f"{len(fm.glCommands) - num_nodes} GL commands ({n_strip} strips, {n_fan} fans) in {num_nodes} mesh nodes.")
    WriteFM(fm, filepath)
    if ExportTextures:
        _export_textures(filepath.parent, topo)
    print(f"Exported {len(meshes)} object(s) to '{filepath.name}'.")
    return True

def build_fm(coords, tris, tri_uvs, tri_nodes, num_nodes, skins, skin_size, frame_names, ref_type=-1, ref_mats=None, skeleton_type=-1, clusters=None, joint_mats=None):
    coords = np.asarray(coords, dtype=np.float64)
    num_frames, num_verts = coords.shape[:2]
    tris = np.asarray(tris, dtype=np.int64)
    tri_uvs = np.asarray(tri_uvs, dtype=np.float64)
    tri_nodes = np.asarray(tri_nodes, dtype=np.int64)
    W, H = skin_size

    if num_verts > INT16_MAX:
        raise RuntimeError(f"{num_verts} vertices; triangle indices are 16 bit, the maximum is {INT16_MAX}.")
    if len(tris) == 0:
        raise RuntimeError("The selected meshes have no faces.")

    #Triangles grouped by node
    order = np.argsort(tri_nodes, kind="stable")
    tris, tri_uvs, tri_nodes = tris[order], tri_uvs[order], tri_nodes[order]
    num_tris = len(tris)

    #Texture coordinates
    uv_index, st = {}, []

    def uv_for(uv):
        key = (int(round(uv[0] * W)), int(round((1.0 - uv[1]) * H)))
        if key not in uv_index:
            uv_index[key] = len(st)
            st.append(key)
        return uv_index[key]

    #H2's winding is the reverse of Blender's
    tri_v = tris[:, (0, 2, 1)]
    tri_u = np.array([[uv_for(tri_uvs[t, k]) for k in (0, 2, 1)] for t in range(num_tris)], dtype=np.int64)
    if len(st) > INT16_MAX or min(min(k) for k in st) < -32768 or max(max(k) for k in st) > INT16_MAX:
        raise RuntimeError("Texture coordinates don't fit into 16 bits (UVs too large or too many).")

    #Mesh nodes: GL commands + terminator, and the node's tri/vert bitmasks
    #Bitmask arrays are not used in-game, since it lacks a software renderer.
    owner = np.full(num_verts, -1, dtype=np.int64)
    np.maximum.at(owner, tri_v.ravel(), np.repeat(tri_nodes, 3))
    bounds = np.searchsorted(tri_nodes, np.arange(num_nodes + 1))
    gl_commands, mesh_nodes, running = [], [], 0
    overflow_bits = False
    for n in range(num_nodes):
        lo, hi = int(bounds[n]), int(bounds[n + 1])
        keys = [tuple((int(tri_v[t, k]), int(tri_u[t, k])) for k in range(3)) for t in range(lo, hi)]
        ints = 0
        for is_fan, corners in _build_commands(keys, MAX_GL_COMMAND_VERTS):
            verts = [h2_fm_glCommandVertex_t(s=st[u][0] / W, t=st[u][1] / H, vertexIndex=v) for v, u in corners]
            gl_commands.append(h2_fm_glCommand_t(count=-len(verts) if is_fan else len(verts), vertices=verts))
            ints += 1 + 3 * len(verts)
        gl_commands.append(h2_fm_glCommand_t(count=0, vertices=[]))      # node terminator
        ints += 1
        if running > INT16_MAX or ints > INT16_MAX:
            raise RuntimeError(
                f"The GL command data is too large: mesh node {n} starts at int {running} and takes {ints}, but both fields are 16 bit (max {INT16_MAX}). Reduce the polygon count.")

        tri_bits, vert_bits = bytearray(256), bytearray(256)
        for t in range(lo, hi):
            if t < BITMASK_BITS:
                tri_bits[t >> 3] |= 1 << (t & 7)
            else:
                overflow_bits = True
        for v in np.nonzero(owner == n)[0]:
            if v < BITMASK_BITS:
                vert_bits[int(v) >> 3] |= 1 << (int(v) & 7)
            else:
                overflow_bits = True
        mesh_nodes.append(h2_fm_meshnode_t(unusedTris=list(tri_bits), unusedVerts=list(vert_bits), start_glcmds=running, num_glcmds=ints))
        running += ints
    if overflow_bits:
        print(f"Warning: more than {BITMASK_BITS} triangles or vertices; the mesh node bitmasks are incomplete.")

    #Frames
    frames = []
    for name, co in zip(frame_names, coords):
        normal_idx = light_normal_indices(co, tris)
        mn = co.min(axis=0)
        rng = co.max(axis=0) - mn
        scale = np.where(rng > 0, rng / 255.0, 1.0)
        q = np.clip(np.rint((co - mn) / scale), 0, 255).astype(int)
        frames.append(h2_fm_frame_t(
            scale=[float(x) for x in scale], translate=[float(x) for x in mn], name=name[:15],
            vertices=[h2_fm_triangleVertex_t(vertex=[int(a), int(b), int(c)], lightNormalIndex=int(n))
                      for (a, b, c), n in zip(q, normal_idx)]))

    #References
    references = h2_fm_ReferenceBlock_t()
    ref_mats = ref_mats or {}
    if ref_type >= 0:
        expected = REFERENCE_COUNTS.get(ref_type)
        if expected is None:
            raise RuntimeError(f"Unknown reference type {ref_type}.")
        missing = [i for i in range(expected) if i not in ref_mats]
        if missing:
            raise RuntimeError(f"This reference type needs {expected} empties named {REF_NAME_PREFIX}0 to {REF_NAME_PREFIX}{expected - 1}; missing: {missing}.")
        extra = sorted(i for i in ref_mats if i >= expected)
        if extra:
            print(f"Warning: ignoring reference empties with index {extra} (type only has {expected}).")
        references = h2_fm_ReferenceBlock_t(
            isUsed=True, referenceType=ref_type, haveRefs=1,
            placements=[_encode_placement(ref_mats[i][f], frames[f]) for f in range(num_frames) for i in range(expected)])
    elif ref_mats:
        print("Note: reference empties found but no reference type selected; no reference block written.")

    #Skeleton
    skeleton = h2_fm_SkeletonBlock_t()
    clusters = clusters or {}
    joint_mats = joint_mats or {}
    if skeleton_type >= 0:
        expected = SKELETON_JOINT_COUNTS.get(skeleton_type)
        if expected is None:
            raise RuntimeError(f"Unknown skeleton type {skeleton_type}.")
        if not clusters and not joint_mats:
            raise RuntimeError(f"A skeleton type is selected, but there are no {CLUSTER_NAME_PREFIX}# vertex groups or {JOINT_NAME_PREFIX}# empties.")
        extra = sorted({i for i in list(clusters) + list(joint_mats) if i >= expected})
        if extra:
            print(f"Warning: ignoring skeleton clusters/joints with index {extra} (type only has {expected}).")
        skeleton = h2_fm_SkeletonBlock_t(
            isUsed=True, skeletalType=skeleton_type, numClusters=expected,
            clusters=[h2_fm_SkeletalCluster_t(vertices=sorted(set(clusters.get(i, [])))) for i in range(expected)])
        if joint_mats:
            missing = [i for i in range(expected) if i not in joint_mats]
            if missing:
                raise RuntimeError(f"This skeleton type needs {expected} empties named {JOINT_NAME_PREFIX}0 to {JOINT_NAME_PREFIX}{expected - 1}; missing: {missing}.")
            skeleton.haveSkeleton = 1
            skeleton.frames = [h2_fm_SkeletonFrame_t(joints=[_encode_placement(joint_mats[i][f], frames[f]) for i in range(expected)])
                               for f in range(num_frames)]
        else:
            print("Warning: no joint empties found, writing the skeleton clusters without joint placements.")
    elif clusters or joint_mats:
        print("Note: skeleton clusters/joints found but no skeleton type selected; no skeleton block written.")

    header = h2_fm_startheader_t(
        skinwidth=W, skinheight=H, framesize=40 + 4 * num_verts,
        num_skins=len(skins), num_xyz=num_verts, num_st=len(st), num_tris=num_tris,
        num_glcmds=running, num_frames=num_frames, num_mesh_nodes=num_nodes)
    return H2_FM_file(
        header=header,
        uv=[h2_fm_stvert_t(s=s, t=t) for s, t in st],
        triangles=[h2_fm_triangle_t(vertexIndices=[int(x) for x in tri_v[t]], textureIndices=[int(x) for x in tri_u[t]])
                   for t in range(num_tris)],
        frames=frames, glCommands=gl_commands, skins=list(skins), meshNodes=mesh_nodes,
        skeleton=skeleton, references=references)
