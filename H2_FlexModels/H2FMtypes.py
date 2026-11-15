from dataclasses import dataclass, field
from typing import Final

@dataclass
class h2_fm_blockheader_t:
    ident: str = ""
    version: int = 0
    size: int = 0

#Block header values listed below:
# Initial Header
FM_HEADER_NAME: Final = "header"
FM_HEADER_VER: Final = 2
# Skin header.
FM_SKIN_NAME: Final = "skin"
FM_SKIN_VER: Final = 1
# ST coord header.
FM_ST_NAME: Final = "st coord"
FM_ST_VER: Final = 1
# Tri header.
FM_TRI_NAME: Final = "tris"
FM_TRI_VER: Final = 1
# Frame header.
FM_FRAME_NAME: Final = "frames"
FM_FRAME_VER: Final = 1
# GLCmds header.
FM_GLCMDS_NAME: Final = "glcmds"
FM_GLCMDS_VER: Final = 1
# Mesh nodes header.
FM_MESH_NAME: Final = "mesh nodes"
FM_MESH_VER: Final = 3
# Skeleton header.
FM_SKELETON_NAME: Final = "skeleton"
FM_SKELETON_VER: Final = 1
# References header.
FM_REFERENCES_NAME: Final = "references"
FM_REFERENCES_VER: Final = 1
#FM_SHORT_FRAME, FM_NORMAL and FM_COMP blocks are unused.

@dataclass
class h2_fm_startheader_t:
    skinwidth: int = 0
    skinheight: int = 0
    framesize: int = 0

    num_skins: int = 0
    num_xyz: int = 0
    num_st: int = 0
    num_tris: int = 0
    num_glcmds: int = 0
    num_frames: int = 0
    num_mesh_nodes: int = 0

@dataclass
class h2_fm_Placement_t:
    origin: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    direction: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    up: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    #all floats

@dataclass
class h2_fm_stvert_t:
    s: int = 0
    t: int = 0

@dataclass
class h2_fm_triangle_t:
    vertexIndices: list = field(default_factory=lambda: [0, 0, 0])
    textureIndices: list = field(default_factory=lambda: [0, 0, 0])
    #all shorts(signed int16)

@dataclass
class h2_fm_triangleVertex_t:
    vertex: list = field(default_factory=lambda: [0, 0, 0])
    lightNormalIndex: int = 0
    #all unsigned bytes(uint8_t)

@dataclass
class h2_fm_meshnode_t:
    unusedTris: list = field(default_factory=lambda: [0] * 256)
    unusedVerts: list = field(default_factory=lambda: [0] * 256)
    start_glcmds: int = 0
    num_glcmds: int = 0

@dataclass
class h2_fm_frame_t:
    scale: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    translate: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    name: str = "" #16 char limit
    vertices: list = field(default_factory=list) #array of h2_fm_triangleVertex_t

@dataclass
class h2_fm_ReferenceBlock_t:
    isUsed:bool = False
    referenceType: int = 0
    haveRefs: int = 0
    placements: list = field(default_factory=list)  # array of h2_fm_Placement_t

@dataclass
class h2_fm_SkeletalCluster_t:
    vertices: list = field(default_factory=list)

@dataclass
class h2_fm_SkeletonFrame_t:
    joints: list = field(default_factory=list)  # array of h2_fm_Placement_t

@dataclass
class h2_fm_SkeletonBlock_t:
    isUsed:bool = False
    skeletalType: int = 0
    numClusters: int = 0
    clusters: list = field(default_factory=list)  # array of h2_fm_SkeletalCluster_t
    haveSkeleton: int = 0
    frames: list = field(default_factory=list)  # array of h2_fm_SkeletonFrame_t

@dataclass
class h2_fm_glCommandVertex_t:
    s: float = 0.0
    t: float = 0.0
    vertexIndex: int = 0

@dataclass
class h2_fm_glCommand_t:
    count: int = 0 #positive for strip, negative for fan
    vertices: list = field(default_factory=list) # array of h2_fm_glCommandVertex_t

@dataclass
class H2_FM_file:
    header: h2_fm_startheader_t = field(default_factory=h2_fm_startheader_t)
    uv: list = field(default_factory=list) # array of h2_fm_stvert_t
    triangles: list = field(default_factory=list) # array of h2_fm_triangle_t
    frames: list = field(default_factory=list) # array of h2_fm_frame_t
    glCommands: list = field(default_factory=list) # array of h2_fm_glCommand_t
    skins: list = field(default_factory=list) #array of strings(64-char limit)
    meshNodes: list = field(default_factory=list) # array of h2_fm_meshnode_t
    skeleton: h2_fm_SkeletonBlock_t = field(default_factory=h2_fm_SkeletonBlock_t)
    references: h2_fm_ReferenceBlock_t = field(default_factory=h2_fm_ReferenceBlock_t)

