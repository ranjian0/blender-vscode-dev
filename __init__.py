bl_info = {
    "name": "Blender VS Code Tools",
    "author": "Ian Karanja",
    "version": (0, 0, 1),
    "blender": (2, 80, 0),
    "location": "Text Editor > UI > Code Tools",
    "description": "Collection of tools for external addon development with VS Code.",
    "warning": "Early Development.",
    "doc_url": "https://github.com/ranjian0/blender-vscode-dev",
    "tracker_url": "https://github.com/ranjian0/blender-vscode-dev/issues/new",
    "category": "Development",
}

import bpy 

from .utils import make_annotations
from .watcher import register_watcher, unregister_watcher
from .debugger import register_debugger, unregister_debugger, check_for_debugpy


@make_annotations
class AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    editor_path = bpy.props.StringProperty(
        name='Editor Path',
        description='Path to external editor.',
        subtype='FILE_PATH'
    )

    path = bpy.props.StringProperty(
      name="Location of debugpy (site-packages folder)",
      subtype="DIR_PATH",
      default=check_for_debugpy()
    )

    timeout = bpy.props.IntProperty(
      name="Timeout",
      default=20
    )

    port = bpy.props.IntProperty(
      name="Port",
      min=0,
      max=65535,
      default=5678
    )


    def draw(self, context):
        layout = self.layout

        layout.prop(self, 'editor_path')

        row_path = layout
        row_path.label(text="The addon will try to auto-find the location of debugpy, if no path is found, or you would like to use a different path, set it here.")
        row_path.prop(self, "path")

        row_timeout = layout.split()
        row_timeout.prop(self, "timeout")
        row_timeout.label(text="Timeout in seconds for the attach confirmation listener.")

        row_port = layout.split()
        row_port.prop(self, "port")
        row_port.label(text="Port to use. Should match port in VS Code's launch.json.")



def register():
    bpy.utils.register_class(AddonPreferences)
    register_watcher()
    register_debugger()

def unregister():
    bpy.utils.unregister_class(AddonPreferences)
    unregister_watcher()
    unregister_debugger()


if __name__ == '__main__':
    register()