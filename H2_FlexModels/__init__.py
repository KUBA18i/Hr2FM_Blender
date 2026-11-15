bl_info = {
    "name": "Heretic 2's FlexModels (.fm)",
    "author": "Jakub Majewski",
    "version": (1, 0, 0),
    "blender": (5, 2, 3),
    "location": "File > Import-Export",
    "description": "Import and Export Heretic 2's .FM models.",
    "category": "Import-Export",
}

import bpy

from .BlenderGUI import (
    classes,
    menu_func_import,
    menu_func_export,
    register_icon,
    unregister_icon,
)

def register():
    register_icon()
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_icon()

if __name__ == "__main__":
    register()