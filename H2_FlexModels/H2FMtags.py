import math, bpy
from mathutils import Matrix
from typing import Final

EMPTY_DISPLAY_SIZE: Final = 4.0
PLACEMENT_AXIS_LENGTH: Final = 20.0

#Name patterns used by this addon:
REF_NAME_PREFIX: Final = "__FM_Ref_"
JOINT_NAME_PREFIX: Final = "__FM_Joint_"
CLUSTER_NAME_PREFIX: Final = "__FM_Cluster_"
MESHNODE_NAME_PREFIX: Final = "__FM_Meshnode_"

#Info fetched from the game's Reference.h and Skeletons.h; required to split the placement arrays into proper groups:
REFERENCE_COUNTS: Final = {0: 7, 1: 5, 2: 6, 3: 7}
SKELETON_JOINT_COUNTS: Final = {0: 3, 1: 1, 2: 2, 3: 2, 4: 3, 5: 3}

REFERENCE_TYPE_ITEMS: Final = [
    ("-1", "None", "Don't write a reference block"),
    ("0", "Corvus", "REF_CORVUS: 7 reference points"),
    ("1", "Insect (Tchekrik)", "REF_INSECT: 5 reference points"),
    ("2", "Priestess", "REF_PRIESTESS: 6 reference points"),
    ("3", "Morcalavin", "REF_MORK: 7 reference points"),
]
SKELETON_TYPE_ITEMS: Final = [
    ("-1", "None", "Don't write a skeleton block"),
    ("0", "Raven", "SKEL_RAVEN: 3 joints"),
    ("1", "Box", "SKEL_BOX: 1 joint"),
    ("2", "Beetle", "SKEL_BEETLE: 2 joints"),
    ("3", "Elflord", "SKEL_ELFLORD: 2 joints"),
    ("4", "Plague Elf", "SKEL_PLAGUE_ELF: 3 joints"),
    ("5", "Corvus", "SKEL_CORVUS: 3 joints"),
]

REFERENCE_NAMES: Final = {
    0: ["LEFTHAND", "RIGHTHAND", "LEFTFOOT", "RIGHTFOOT", "STAFF", "BLADE", "HELL_HEAD"],   #REF_CORVUS
    1: ["STAFF", "SWORD", "SPEAR", "RIGHTFOOT", "LEFTFOOT"],                                 #REF_INSECT
    2: ["BACK", "STAFF", "LHAND", "RHAND", "RFOOT", "LFOOT"],                                #REF_PRIESTESS
    3: ["STAFFREF", "RFOOTREF", "LFOOTREF", "RHANDREF", "LHANDREF", "LEYEREF", "REYEREF"],   #REF_MORK
}
SKELETON_JOINT_NAMES: Final = {
    0: ["LOWERBACK", "UPPERBACK", "HEAD"],       #SKEL_RAVEN
    1: ["CENTER"],                               #SKEL_BOX
    2: ["NECK", "HEAD"],                         #SKEL_BEETLE
    3: [],                                       #SKEL_ELFLORD (joints are unnamed in the header)
    4: ["LOWERBACK", "UPPERBACK", "HEAD"],       #SKEL_PLAGUE_ELF
    5: ["LOWERBACK", "UPPERBACK", "HEAD"],       #SKEL_CORVUS
}
#End of data definitions.

def _tag_names(table, type_id, count, prefix):
    labels = table.get(type_id, [])
    if len(labels) != count:
        labels = []
    return [f"{prefix}{i}_{labels[i]}" if labels else f"{prefix}{i}" for i in range(count)]

def _norm(v):
    length = math.sqrt(sum(c * c for c in v))
    return [c / length for c in v] if length > 1e-9 else [1.0, 0.0, 0.0]

def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _placement_axes(p, scale, translate):
    o = [p.origin[i] * scale[i] + translate[i] for i in range(3)]
    d = [(p.direction[i] - p.origin[i]) * scale[i] for i in range(3)]
    u = [(p.up[i] - p.origin[i]) * scale[i] for i in range(3)]
    x = _norm(d)
    dot = sum(u[i] * x[i] for i in range(3))
    z = _norm([u[i] - dot * x[i] for i in range(3)])
    y = _cross(z, x)
    return o, x, y, z

def _placement_matrix(p, frame):
    o, x, y, z = _placement_axes(p, frame.scale, frame.translate)
    return Matrix((
        (x[0], y[0], z[0], o[0]),
        (x[1], y[1], z[1], o[1]),
        (x[2], y[2], z[2], o[2]),
        (0.0, 0.0, 0.0, 1.0),
    ))

def _make_empty(name, parent):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'ARROWS'
    empty.empty_display_size = EMPTY_DISPLAY_SIZE
    bpy.context.collection.objects.link(empty)
    empty.parent = parent
    return empty

def _apply_matrix(empty, matrix, prev_euler):
    empty.location = matrix.to_translation()
    euler = matrix.to_euler('XYZ', prev_euler) if prev_euler is not None else matrix.to_euler('XYZ')
    empty.rotation_euler = euler #compat euler avoids 360-degree flips between frames
    return euler

def _build_empties(obj, frames, flat, count, names, base_idx, animate):
    empties = []
    for k in range(count):
        empty = _make_empty(names[k], obj)
        empties.append(empty)
        if not animate:
            _apply_matrix(empty, _placement_matrix(flat[base_idx * count + k], frames[base_idx]), None)
            continue
        prev = None
        for f, frame in enumerate(frames):
            prev = _apply_matrix(empty, _placement_matrix(flat[f * count + k], frame), prev)
            empty.keyframe_insert('location', frame=f)
            empty.keyframe_insert('rotation_euler', frame=f)
    return empties

def import_references(obj, fm_data, base_idx: int, animate: bool):
    refs = fm_data.references
    if not (refs.isUsed and refs.haveRefs and refs.placements):
        return []
    frames = fm_data.frames
    count, remainder = divmod(len(refs.placements), len(frames))
    if count == 0 or remainder:
        print(f"Warning: {len(refs.placements)} reference placements don't divide into {len(frames)} frames; references skipped.")
        return []
    names = _tag_names(REFERENCE_NAMES, refs.referenceType, count, REF_NAME_PREFIX)
    return _build_empties(obj, frames, refs.placements, count, names, base_idx, animate)

def import_skeleton(obj, fm_data, base_idx: int, animate: bool):
    sk = fm_data.skeleton
    if not sk.isUsed:
        return []

    #Cluster -> vertex group
    num_verts = len(obj.data.vertices)
    for k, cluster in enumerate(sk.clusters):
        vg = obj.vertex_groups.new(name=f"{CLUSTER_NAME_PREFIX}{k}")
        valid = [v for v in cluster.vertices if 0 <= v < num_verts]
        if valid:
            vg.add(valid, 1.0, 'REPLACE')

    #Joint placements -> empties
    frames = fm_data.frames
    if not (sk.haveSkeleton and sk.numClusters and len(sk.frames) == len(frames)):
        return []
    flat = [j for fr in sk.frames for j in fr.joints]
    if len(flat) != len(frames) * sk.numClusters:
        print("Warning: skeleton joint count doesn't match numClusters * frames; joints skipped.")
        return []
    names = _tag_names(SKELETON_JOINT_NAMES, sk.skeletalType, sk.numClusters, JOINT_NAME_PREFIX)
    return _build_empties(obj, frames, flat, sk.numClusters, names, base_idx, animate)