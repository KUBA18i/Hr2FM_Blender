from pathlib import Path
import struct, sys
from .H2FMtypes import (
    FM_HEADER_NAME,
    FM_HEADER_VER,
    FM_SKIN_NAME,
    FM_SKIN_VER,
    FM_ST_NAME,
    FM_ST_VER,
    FM_TRI_NAME,
    FM_TRI_VER,
    FM_FRAME_NAME,
    FM_FRAME_VER,
    FM_GLCMDS_NAME,
    FM_GLCMDS_VER,
    FM_MESH_NAME,
    FM_MESH_VER,
    FM_SKELETON_NAME,
    FM_SKELETON_VER,
    FM_REFERENCES_NAME,
    FM_REFERENCES_VER,

    h2_fm_blockheader_t,
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

    H2_FM_file
)

def ReadFM(inpath: str | Path) -> H2_FM_file:
    inpath = Path(inpath)
    print(f"Loading Daikatana model: \"{inpath}\"")
    NewFlexModel = H2_FM_file()

    with (open(inpath, "rb") as f):
        while f.peek(1):
            BlockHeader = h2_fm_blockheader_t()
            BlockHeader.ident = f.read(32).split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
            BlockHeader.version = struct.unpack("<i", f.read(4))[0]
            BlockHeader.size = struct.unpack("<i", f.read(4))[0]
            print(f"Found Block: {BlockHeader.ident} | Version: {BlockHeader.version} | Size: {BlockHeader.size} bytes.")
            curpos: int = f.tell()

            if BlockHeader.ident == FM_HEADER_NAME and BlockHeader.version == FM_HEADER_VER:
                header_data = struct.unpack("10i", f.read(40))
                NewFlexModel.header.skinwidth = header_data[0]
                NewFlexModel.header.skinheight = header_data[1]
                NewFlexModel.header.framesize = header_data[2]
                NewFlexModel.header.num_skins = header_data[3]
                NewFlexModel.header.num_xyz = header_data[4]
                NewFlexModel.header.num_st = header_data[5]
                NewFlexModel.header.num_tris = header_data[6]
                NewFlexModel.header.num_glcmds = header_data[7]
                NewFlexModel.header.num_frames = header_data[8]
                NewFlexModel.header.num_mesh_nodes = header_data[9]
                print("Model Header parsed.")
            elif BlockHeader.ident == FM_SKIN_NAME and BlockHeader.version == FM_SKIN_VER:
                for _ in range(NewFlexModel.header.num_skins):
                    skin_path = f.read(64).split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
                    NewFlexModel.skins.append(skin_path)
                print("Skin block parsed.")
            elif BlockHeader.ident == FM_ST_NAME and BlockHeader.version == FM_ST_VER:
                for _ in range(NewFlexModel.header.num_st):
                    s, t = struct.unpack("hh", f.read(4))
                    NewFlexModel.uv.append(h2_fm_stvert_t(s=s, t=t))
                print("UV block parsed.")
            elif BlockHeader.ident == FM_TRI_NAME and BlockHeader.version == FM_TRI_VER:
                for _ in range(NewFlexModel.header.num_tris):
                    data = struct.unpack("6h", f.read(12))
                    tri = h2_fm_triangle_t(
                        vertexIndices=[data[0], data[1], data[2]],
                        textureIndices=[data[3], data[4], data[5]],
                    )
                    NewFlexModel.triangles.append(tri)
                print("Triangle block parsed.")
            elif BlockHeader.ident == FM_FRAME_NAME and BlockHeader.version == FM_FRAME_VER:
                for _ in range(NewFlexModel.header.num_frames):
                    scale = struct.unpack("3f", f.read(12))
                    translate = struct.unpack("3f", f.read(12))
                    name = f.read(16).split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()

                    vertices = []
                    for _ in range(NewFlexModel.header.num_xyz):
                        vx, vy, vz = struct.unpack("3B", f.read(3))
                        light_normal = struct.unpack("B", f.read(1))[0]
                        vert = h2_fm_triangleVertex_t(vertex=[vx, vy, vz], lightNormalIndex=light_normal)
                        vertices.append(vert)

                    frame = h2_fm_frame_t(
                        scale=list(scale),
                        translate=list(translate),
                        name=name,
                        vertices=vertices,
                    )
                    NewFlexModel.frames.append(frame)
                print("Frame block parsed.")
            elif BlockHeader.ident == FM_GLCMDS_NAME and BlockHeader.version == FM_GLCMDS_VER:
                end = curpos + BlockHeader.size
                while f.tell() < end:
                    command = struct.unpack("<i", f.read(4))[0]
                    if command == 0:  # node terminator, keep it
                        NewFlexModel.glCommands.append(h2_fm_glCommand_t(count=0, vertices=[]))
                        continue
                    num_verts = abs(command)
                    if f.tell() + num_verts * 12 > end:
                        sys.exit(f"GL command overruns block (count={command} at {f.tell() - 4}).")
                    cmd_verts = []
                    for _ in range(num_verts):
                        v_s, v_t, v_idx = struct.unpack("<ffi", f.read(12))
                        cmd_verts.append(h2_fm_glCommandVertex_t(s=v_s, t=v_t, vertexIndex=v_idx))
                    NewFlexModel.glCommands.append(h2_fm_glCommand_t(count=command, vertices=cmd_verts))
                print("GL commands block parsed.")
            elif BlockHeader.ident == FM_MESH_NAME and BlockHeader.version == FM_MESH_VER:
                for _ in range(NewFlexModel.header.num_mesh_nodes):
                    NewunusedTris = list(struct.unpack("256B", f.read(256)))
                    NewunusedVerts = list(struct.unpack("256B", f.read(256)))
                    Newstart_glcmds, Newnum_glcmds = struct.unpack("2H", f.read(4))
                    newMeshNode = h2_fm_meshnode_t(
                        unusedTris = NewunusedTris,
                        unusedVerts = NewunusedVerts,
                        start_glcmds = Newstart_glcmds,
                        num_glcmds = Newnum_glcmds
                    )
                    NewFlexModel.meshNodes.append(newMeshNode)
                print("Mesh node block parsed.")
            elif BlockHeader.ident == FM_SKELETON_NAME and BlockHeader.version == FM_SKELETON_VER:
                NewFlexModel.skeleton.isUsed = True
                NewFlexModel.skeleton.skeletalType, NewFlexModel.skeleton.numClusters = struct.unpack("2i", f.read(8))
                if NewFlexModel.skeleton.numClusters:
                    cluster_vert_counts = list(struct.unpack(f"{NewFlexModel.skeleton.numClusters}i", f.read(NewFlexModel.skeleton.numClusters * 4)))
                    NewFlexModel.skeleton.clusters = []
                    for count in cluster_vert_counts:
                        if count:
                            vertices = list(struct.unpack(f"{count}i", f.read(count * 4)))
                        else:
                            vertices = []
                        NewFlexModel.skeleton.clusters.append(h2_fm_SkeletalCluster_t(vertices=vertices))
                NewFlexModel.skeleton.haveSkeleton = struct.unpack("<i", f.read(4))[0]
                if NewFlexModel.skeleton.numClusters != 0:
                    NewFlexModel.skeleton.frames = [h2_fm_SkeletonFrame_t(joints=[h2_fm_Placement_t() for _ in range(NewFlexModel.skeleton.numClusters)]) for _ in range(NewFlexModel.header.num_frames)]
                    for i in range(NewFlexModel.header.num_frames):
                        for c in range(NewFlexModel.skeleton.numClusters):
                            NewOrigin = list(struct.unpack("3f", f.read(12)))
                            NewDir = list(struct.unpack("3f", f.read(12)))
                            NewUp = list(struct.unpack("3f", f.read(12)))
                            jointPlacement = h2_fm_Placement_t(origin=NewOrigin,direction=NewDir,up=NewUp)
                            NewFlexModel.skeleton.frames[i].joints[c] = jointPlacement
                    print(f"Skeleton block parsed {NewFlexModel.skeleton.numClusters} clusters across {NewFlexModel.header.num_frames} frames).")
                else:
                    print(f"Skeleton block parsed {NewFlexModel.skeleton.numClusters} clusters, no frame joint transforms).")
            elif BlockHeader.ident == FM_REFERENCES_NAME and BlockHeader.version == FM_REFERENCES_VER:
                NewFlexModel.references.isUsed = True
                NewFlexModel.references.referenceType, NewFlexModel.references.haveRefs = struct.unpack("2i", f.read(8))
                if NewFlexModel.references.haveRefs != 0:
                    bytesRemaining: int = BlockHeader.size - 8
                    count: int = int(bytesRemaining / 12)
                    NewFlexModel.references.placements = []
                    for unpacked in struct.iter_unpack("9f", f.read(bytesRemaining)):
                        placement = h2_fm_Placement_t(
                            origin=list(unpacked[0:3]),
                            direction=list(unpacked[3:6]),
                            up=list(unpacked[6:9])
                        )
                        NewFlexModel.references.placements.append(placement)
                    print(f"Reference block parsed {count} placements).")
                else:
                    print("Reference block parsed (haveRefs = 0).")
            else:
                sys.exit("Illegal block ident or version! Terminating program.")

            if f.tell() - curpos != BlockHeader.size:
                sys.exit(f"Block reading error; mismatch with block size: {(f.tell()-curpos)} vs {BlockHeader.size} bytes.")
    f.close()
    return NewFlexModel

def WriteBlockHeader(f, ident: str, version: int, size: int):
    ident_bytes = ident.encode('ascii')[:32].ljust(32, b'\x00')
    header = struct.pack('<32siI', ident_bytes, version, size)
    f.write(header)

def WriteFM(fm: H2_FM_file, outpath: str | Path):
    outpath = Path(outpath)
    with open(outpath, "wb") as f:
        WriteBlockHeader(f, FM_HEADER_NAME, FM_HEADER_VER, 40)
        header_values = (
            fm.header.skinwidth,
            fm.header.skinheight,
            fm.header.framesize,
            fm.header.num_skins,
            fm.header.num_xyz,
            fm.header.num_st,
            fm.header.num_tris,
            fm.header.num_glcmds,
            fm.header.num_frames,
            fm.header.num_mesh_nodes
        )
        f.write(struct.pack("10i", *header_values))

        WriteBlockHeader(f, FM_SKIN_NAME, FM_SKIN_VER, fm.header.num_skins * 64)
        for skin in fm.skins:
            f.write(skin.encode("ascii").ljust(64, b"\x00")[:64])

        WriteBlockHeader(f, FM_ST_NAME, FM_ST_VER, fm.header.num_st * 4)
        for uv in fm.uv:
            f.write(struct.pack("hh", uv.s, uv.t))

        WriteBlockHeader(f, FM_TRI_NAME, FM_TRI_VER, fm.header.num_tris * 12)
        for tri in fm.triangles:
            f.write(
                struct.pack(
                    "6h",
                    tri.vertexIndices[0],
                    tri.vertexIndices[1],
                    tri.vertexIndices[2],
                    tri.textureIndices[0],
                    tri.textureIndices[1],
                    tri.textureIndices[2],
                )
            )

        WriteBlockHeader(f, FM_FRAME_NAME, FM_FRAME_VER, fm.header.framesize * fm.header.num_frames)
        for frame in fm.frames:
            f.write(struct.pack("3f", *frame.scale))
            f.write(struct.pack("3f", *frame.translate))
            f.write(frame.name.encode("ascii").ljust(16, b"\x00")[:16])
            for vert in frame.vertices:
                f.write(struct.pack("3B", *vert.vertex))
                f.write(struct.pack("B", vert.lightNormalIndex))

        payload = bytearray()
        for cmd in fm.glCommands:
            payload += struct.pack("<i", cmd.count)
            for v in cmd.vertices:
                payload += struct.pack("<ffi", v.s, v.t, v.vertexIndex)
        WriteBlockHeader(f, FM_GLCMDS_NAME, FM_GLCMDS_VER, len(payload))
        f.write(payload)

        WriteBlockHeader(f, FM_MESH_NAME, FM_MESH_VER, fm.header.num_mesh_nodes * 516)
        for mn in fm.meshNodes:
            f.write(struct.pack("256B",*mn.unusedTris))
            f.write(struct.pack("256B", *mn.unusedVerts))
            f.write(struct.pack("2h", mn.start_glcmds,mn.num_glcmds))

        if fm.skeleton.isUsed:
            print("Skeleton data block present.")
            skelblocksize = 12
            skelblocksize += fm.skeleton.numClusters * 4
            for c in fm.skeleton.clusters:
                skelblocksize += len(c.vertices) * 4
            if fm.skeleton.haveSkeleton:
                for i in fm.skeleton.frames:
                    skelblocksize += len(i.joints) * 36
            WriteBlockHeader(f, FM_SKELETON_NAME, FM_SKELETON_VER, skelblocksize)
            f.write(struct.pack("2i", fm.skeleton.skeletalType, fm.skeleton.numClusters))
            for c in fm.skeleton.clusters:
                count = len(c.vertices)
                f.write(struct.pack("i", count))
            for c in fm.skeleton.clusters:
                for v in c.vertices:
                    f.write(struct.pack("i",v))
            f.write(struct.pack("i", fm.skeleton.haveSkeleton))
            if fm.skeleton.haveSkeleton:
                for i in fm.skeleton.frames:
                    for j in i.joints:
                        f.write(struct.pack("3f",*j.origin))
                        f.write(struct.pack("3f", *j.direction))
                        f.write(struct.pack("3f", *j.up))
        else:
            print("Skeleton data is absent, skipping.")

        if fm.references.isUsed:
            print("Reference data block present.")
            WriteBlockHeader(f, FM_REFERENCES_NAME, FM_REFERENCES_VER, 8 + len(fm.references.placements) * 36)
            f.write(struct.pack("2i", fm.references.referenceType, fm.references.haveRefs))
            if fm.references.haveRefs:
                for p in fm.references.placements:
                    f.write(struct.pack("3f",*p.origin))
                    f.write(struct.pack("3f", *p.direction))
                    f.write(struct.pack("3f", *p.up))
        else:
            print("Reference data is absent, skipping.")
    f.close()
    print(f"FM constructed successfully: {outpath}")
