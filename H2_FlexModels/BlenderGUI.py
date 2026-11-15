import os, traceback, bpy
from bpy.props import StringProperty, IntProperty, BoolProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from pathlib import Path

from .BlenderImport import import_fm_file
from .BlenderExport import export_fm_file
from .H2FMtags import REFERENCE_TYPE_ITEMS, SKELETON_TYPE_ITEMS

H2FM_icon = None

class H2FM_OT_import(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.h2fm"
    bl_label = "Import FlexModel"
    bl_description = "Import a Heretic 2 FlexModel (.fm)."
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".fm"
    filter_glob: StringProperty(
        default="*.fm",
        options={'HIDDEN'},
        maxlen=255,
    )

    BaseFrame: IntProperty(
        name="Base frame",
        description="When importing animations, this frame will be the primary frame, upon which all the shape keys will be based on.\nIf no animations are imported, this frame will be imported as a static mesh.",
        default=0,
        min=0,
        soft_min=0
    )

    UVsFromGLCommands: BoolProperty(
        name="Fetch UV data from GL Commands",
        description="If unchecked, the model's UV and Triangle structs will be used to fetch the UV data. Keep in mind, they are unused in-game, since Heretic 2 lacks a software renderer.",
        default=False
    )

    ImportAnimations: BoolProperty(
        name="Import animations",
        description="If checked, animation frames will be imported as relative Shape Keys.",
        default=True
    )

    TimelineMarkersFromFrames: BoolProperty(
        name="Timeline Markers",
        description="If checked, Timeline Markers will be fetched from the frame names, with their numbers stripped. The current markers will be deleted.",
        default=True
    )

    ImportSkeleton: BoolProperty(
        name="Import Skeleton",
        description="If checked, the mesh will contain cluster vertex groups, and the joints will be placed as animated empties.",
        default=True
    )

    ImportReferences: BoolProperty(
        name="Import References",
        description="If checked, the references will be placed as animated empties.",
        default=True
    )

    ImportTextures: BoolProperty(
        name="Import textures",
        description="If checked, the importer will look for the .M8 files that are mentioned in the skin paths and load them as textures, assigning them to the materials.",
        default=False
    )

    def draw(self, context):
        layout = self.layout

        box1 = layout.box()
        box1.label(text="Basic settings", icon="OBJECT_DATA")
        box1.prop(self, "BaseFrame")
        box1.prop(self, "ImportTextures")
        box1.prop(self, "UVsFromGLCommands")
        box1.prop(self, "ImportSkeleton")
        box1.prop(self, "ImportReferences")

        box2 = layout.box()
        box2.label(text="Animation", icon="ANIM_DATA")
        row1 = box2.column_flow(columns=1, align=True)
        row1.prop(self, "ImportAnimations")
        row2 = box2.column_flow(columns=1, align=True)
        row2.enabled = self.ImportAnimations
        row2.prop(self, "TimelineMarkersFromFrames")

    def execute(self, context):
        try:
            import_fm_file(self.filepath, self.BaseFrame, self.UVsFromGLCommands, self.ImportAnimations, self.TimelineMarkersFromFrames, self.ImportReferences, self.ImportSkeleton, self.ImportTextures)
            self.report({'INFO'}, f"Successfully imported {os.path.basename(self.filepath)}")
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, f"Failed to import fm: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}

def LimitFrameRange(self, context):
    scene = context.scene
    if self.StartFrame < scene.frame_start:
        self.StartFrame = scene.frame_start
    elif self.StartFrame > scene.frame_end:
        self.StartFrame = scene.frame_end
    if self.EndFrame < scene.frame_start:
        self.EndFrame = scene.frame_start
    elif self.EndFrame > scene.frame_end:
        self.EndFrame = scene.frame_end

class H2FM_OT_export(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.fm"
    bl_label = "Export FlexModel"
    bl_description = "Export the selected objects as a Heretic 2 FlexModel (.fm)."
    bl_options = {'REGISTER'}

    ExportAnimations: BoolProperty(
        name="Export animations",
        description="Export all types of animations of the selected objects between set points in the timeline.",
        default = True
    )

    StartFrame: IntProperty(
        name="Start animation frame",
        description="First timeline frame to export. It becomes frame 0 of the model.",
        default=0,
        min=0,
        soft_min=0,
        update=LimitFrameRange
    )

    EndFrame: IntProperty(
        name="End animation frame",
        description="Last timeline frame to export (inclusive).",
        default=2048,
        min=0,
        soft_min=0,
        update=LimitFrameRange
    )

    FramesFromMarkers: BoolProperty(
        name="Fetch frame names from Timeline Markers",
        description="If unchecked, the frames will have a generic name \"frame\" with a number appended to it",
        default = True
    )

    MeshNodesFromVertexGroups: BoolProperty(
        name="Create Mesh Nodes from Vertex Groups",
        description="If checked, mesh nodes are built from vertex groups named __FM_Meshnode_<number>. A triangle goes to the lowest-numbered group containing all three of its vertices, and triangles in no group go to node 0.\nIf unchecked, vertex groups are ignored and the whole model is a single mesh node.",
        default=True
    )

    ReferenceType: bpy.props.EnumProperty(
        name="Reference Type",
        description="Which set of reference points to write. The model needs empties named __FM_Ref_<number>, one for each point of the type (e.g. 7 for Corvus). None writes no reference block.",
        items=REFERENCE_TYPE_ITEMS,
        default='0'
    )

    SkeletonType: bpy.props.EnumProperty(
        name="Skeleton Type",
        description="Which skeleton to write. The model needs __FM_Cluster_<number> vertex groups and __FM_Joint_<number> empties, one for each joint of the type (e.g. 3 for Corvus). None writes no skeleton block.",
        items=SKELETON_TYPE_ITEMS,
        default='5'
    )

    ExportTextures: BoolProperty(
        name="Export textures",
        description="If checked, the textures used by the model(s) will be exported as .M8 files, in the same folder as the .FM model.",
        default = False
    )

    filename_ext = ".fm"
    filter_glob: StringProperty(
        default="*.fm",
        options={'HIDDEN'},
        maxlen=255,
    )

    def invoke(self, context, event):
        self.StartFrame = context.scene.frame_start
        self.EndFrame = context.scene.frame_end
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout

        box1 = layout.box()
        box1.label(text="Model Properties", icon="OBJECT_DATA")
        box1.prop(self, "ExportTextures")
        box1.prop(self, "MeshNodesFromVertexGroups")
        box1.prop(self, "SkeletonType")
        box1.prop(self, "ReferenceType")

        box2 = layout.box()
        box2.label(text="Animation", icon="ANIM_DATA")
        row1 = box2.column_flow(columns=1, align=True)
        row1.prop(self, "ExportAnimations")
        row2 = box2.column_flow(columns=1, align=True)
        row2.enabled = self.ExportAnimations
        row2.prop(self, "StartFrame")
        row2.prop(self, "EndFrame")
        row2.prop(self, "FramesFromMarkers")

    def execute(self, context):
        try:
            objs = [o for o in context.selected_objects if o.type in {'MESH', 'EMPTY'}]
            if not any(o.type == 'MESH' for o in objs):
                active = context.active_object
                if active is not None and active.type == 'MESH':
                    objs.append(active)
                else:
                    self.report({'ERROR'}, "Select at least one mesh object to export")
                    return {'CANCELLED'}

            export_fm_file(self.filepath, objs, int(self.ReferenceType), int(self.SkeletonType), self.ExportAnimations, self.FramesFromMarkers, self.StartFrame, self.EndFrame, self.MeshNodesFromVertexGroups, self.ExportTextures)
            self.report({'INFO'}, f"Successfully exported {os.path.basename(self.filepath)}")
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, f"Failed to export fm: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}


def menu_func_import(self, context):
    icon_id = H2FM_icon["fm_icon"].icon_id if H2FM_icon else 0
    self.layout.operator(H2FM_OT_import.bl_idname, text="Heretic 2 FlexModel (.fm)", icon_value=icon_id)

def menu_func_export(self, context):
    icon_id = H2FM_icon["fm_icon"].icon_id if H2FM_icon else 0
    self.layout.operator(H2FM_OT_export.bl_idname, text="Heretic 2 FlexModel (.fm)", icon_value=icon_id)

def register_icon():
    global H2FM_icon
    import bpy.utils.previews
    H2FM_icon = bpy.utils.previews.new()
    icon_path = Path(__file__).parent / "icon.svg"

    if icon_path.exists():
        H2FM_icon.load("fm_icon", str(icon_path), 'IMAGE')
    else:
        print(f"Warning: Icon file not found at {icon_path}")

def unregister_icon():
    global H2FM_icon
    if H2FM_icon is not None:
        bpy.utils.previews.remove(H2FM_icon)
        H2FM_icon = None

classes = (
    H2FM_OT_import,
    H2FM_OT_export,
)