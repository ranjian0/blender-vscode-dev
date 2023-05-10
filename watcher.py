"""
script_watcher.py: Reload watched script upon changes.

Copyright (C) 2015 Isaac Weaver
Author: Isaac Weaver <wisaac407@gmail.com>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import os
import sys
import io
import traceback
import types
import subprocess

import bpy
import console_python
from bpy.app.handlers import persistent

from .utils import make_annotations

@persistent
def load_handler(dummy):
    running = bpy.context.scene.sw_settings.running

    # First of all, make sure script watcher is off on all the scenes.
    for scene in bpy.data.scenes:
        bpy.ops.wm.sw_watch_end({'scene': scene})

    # Startup script watcher on the current scene if needed.
    if running and bpy.context.scene.sw_settings.auto_watch_on_startup:
        bpy.ops.wm.sw_watch_start()


def add_scrollback(ctx, text, text_type):
    for line in text:
        bpy.ops.console.scrollback_append(ctx, text=line.replace('\t', '    '),
                                          type=text_type)


def get_console_id(area):
    """Return the console id of the given region."""
    if area.type == 'CONSOLE':  # Only continue if we have a console area.
        for region in area.regions:
            if region.type == 'WINDOW':
                return hash(region)  # The id is the hash of the window region.
    return False


def isnum(s):
    return s[1:].isnumeric() and s[0] in '-+1234567890'


class SplitIO(io.StringIO):
    """Feed the input stream into another stream."""
    PREFIX = '[Script Watcher]: '

    _can_prefix = True

    def __init__(self, stream):
        io.StringIO.__init__(self)

        self.stream = stream

    def write(self, s):
        # Make sure we prefix our string before we do anything else with it.
        if self._can_prefix:
            s = self.PREFIX + s
        # only add the prefix if the last stream ended with a newline.
        self._can_prefix = s.endswith('\n')

        # Make sure to call the super classes write method.
        io.StringIO.write(self, s)

        # When we are written to, we also write to the secondary stream.
        self.stream.write(s)


# Define the script watching operator.
class SW_OP_WatchScript(bpy.types.Operator):
    """Watches the script for changes, reloads the script if any changes occur."""
    bl_idname = "wm.sw_watch_start"
    bl_label = "Watch Script"

    _timer = None
    _running = False
    _times = None
    filepath = None

    def get_paths(self):
        """Find all the python paths surrounding the given filepath."""

        dirname = os.path.dirname(self.filepath)

        paths = []
        filepaths = []

        for root, dirs, files in os.walk(dirname, topdown=True):
            if '__init__.py' in files:
                paths.append(root)
                for f in files:
                    filepaths.append(os.path.join(root, f))
            else:
                dirs[:] = [] # No __init__ so we stop walking this dir.

        # If we just have one (non __init__) file then return just that file.
        return paths, filepaths or [self.filepath]

    def get_mod_name(self):
        """Return the module name and the root path of the givin python file path."""
        dir, mod = os.path.split(self.filepath)

        # Module is a package.
        if mod == '__init__.py':
            mod = os.path.basename(dir)
            dir = os.path.dirname(dir)

        # Module is a single file.
        else:
            mod = os.path.splitext(mod)[0]

        return mod, dir

    def remove_cached_mods(self):
        """Remove all the script modules from the system cache."""
        paths, files = self.get_paths()
        for mod_name, mod in list(sys.modules.items()):
            try:
                if hasattr(mod, '__file__') and os.path.dirname(mod.__file__) in paths:
                    del sys.modules[mod_name]
            except TypeError:
                pass

    def _reload_script_module(self):
        print('Reloading script:', self.filepath)
        self.remove_cached_mods()
        try:
            f = open(self.filepath)
            paths, files = self.get_paths()

            # Get the module name and the root module path.
            mod_name, mod_root = self.get_mod_name()

            # Create the module and setup the basic properties.
            mod = types.ModuleType('__main__')
            mod.__file__ = self.filepath
            mod.__path__ = paths
            mod.__package__ = mod_name

            # Add the module to the system module cache.
            sys.modules[mod_name] = mod

            # Fianally, execute the module.
            exec(compile(f.read(), self.filepath, 'exec'), mod.__dict__)
        except IOError:
            print('Could not open script file.')
        except:
            sys.stderr.write("There was an error when running the script:\n" + traceback.format_exc())
        else:
            f.close()

    def reload_script(self, context):
        """Reload this script while printing the output to blenders python console."""

        # Setup stdout and stderr.
        stdout = SplitIO(sys.stdout)
        stderr = SplitIO(sys.stderr)

        sys.stdout = stdout
        sys.stderr = stderr

        # Run the script.
        self._reload_script_module()

        # Go back to the begining so we can read the streams.
        stdout.seek(0)
        stderr.seek(0)

        # Don't use readlines because that leaves trailing new lines.
        output = stdout.read().split('\n')
        output_err = stderr.read().split('\n')

        if self.use_py_console:
            # Print the output to the consoles.
            for area in context.screen.areas:
                if area.type == "CONSOLE":
                    ctx = context.copy()
                    ctx.update({"area": area})

                    # Actually print the output.
                    if output:
                        add_scrollback(ctx, output, 'OUTPUT')

                    if output_err:
                        add_scrollback(ctx, output_err, 'ERROR')

        # Cleanup
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def modal(self, context, event):
        if not context.scene.sw_settings.running:
            self.cancel(context)
            return {'CANCELLED'}

        if context.scene.sw_settings.reload:
            context.scene.sw_settings.reload = False
            self.reload_script(context)
            return {'PASS_THROUGH'}

        if event.type == 'TIMER':
            for path in self._times:
                cur_time = os.stat(path).st_mtime

                if cur_time != self._times[path]:
                    self._times[path] = cur_time
                    self.reload_script(context)

        return {'PASS_THROUGH'}

    def execute(self, context):
        if context.scene.sw_settings.running:
            return {'CANCELLED'}

        # Grab the settings and store them as local variables.
        self.filepath = bpy.path.abspath(context.scene.sw_settings.filepath)
        self.use_py_console = context.scene.sw_settings.use_py_console

        # If it's not a file, doesn't exist or permistion is denied we don't preceed.
        if not os.path.isfile(self.filepath):
            self.report({'ERROR'}, 'Unable to open script.')
            return {'CANCELLED'}

        # Setup the times dict to keep track of when all the files where last edited.
        dirs, files = self.get_paths()
        self._times = dict((path, os.stat(path).st_mtime) for path in files) # Where we store the times of all the paths.
        self._times[files[0]] = 0  # We set one of the times to 0 so the script will be loaded on startup.

        # Setup the event timer.
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        context.scene.sw_settings.running = True
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

        self.remove_cached_mods()

        context.scene.sw_settings.running = False


class SW_OP_StopScriptWatcher(bpy.types.Operator):
    """Stop watching the current script."""
    bl_idname = "wm.sw_watch_end"
    bl_label = "Stop Watching"

    def execute(self, context):
        # Setting the running flag to false will cause the modal to cancel itself.
        context.scene.sw_settings.running = False
        return {'FINISHED'}


class SW_OP_ReloadScriptWatcher(bpy.types.Operator):
    """Reload the current script."""
    bl_idname = "wm.sw_reload"
    bl_label = "Reload Script"

    def execute(self, context):
        # Setting the reload flag to true will cause the modal to cancel itself.
        context.scene.sw_settings.reload = True
        return {'FINISHED'}


class SW_OP_OpenExternalEditor(bpy.types.Operator):
    """Edit script in an external text editor."""
    bl_idname = "wm.sw_edit_externally"
    bl_label = "Edit Externally"

    def execute(self, context):
        if bpy.app.version < (2, 80):
            addon_prefs = context.user_preferences.addons[__package__].preferences
        else:
            addon_prefs = context.preferences.addons[__package__].preferences

        filepath = bpy.path.abspath(context.scene.sw_settings.filepath)

        subprocess.Popen((addon_prefs.editor_path, filepath))
        return {'FINISHED'}


# Create the UI for the operator. NEEDS FINISHING!!
class SW_PT_ScriptWatcherPanel(bpy.types.Panel):
    """UI for the script watcher."""
    bl_label = "Script Watcher"
    bl_idname = "SCENE_PT_script_watcher"
    bl_space_type = 'TEXT_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Code Tools"

    def draw(self, context):
        layout = self.layout
        running = context.scene.sw_settings.running

        col = layout.column()
        col.prop(context.scene.sw_settings, 'filepath')
        col.prop(context.scene.sw_settings, 'use_py_console')
        col.prop(context.scene.sw_settings, 'auto_watch_on_startup')
        col.prop(context.scene.sw_settings, 'run_main')

        if bpy.app.version < (2, 80, 0):
            col.operator('wm.sw_watch_start', icon='VISIBLE_IPO_ON')
        else:
            col.operator('wm.sw_watch_start', icon='HIDE_OFF')

        col.enabled = not running

        if running:
            row = layout.row(align=True)
            row.operator('wm.sw_watch_end', icon='CANCEL')
            row.operator('wm.sw_reload', icon='FILE_REFRESH')

        layout.separator()
        layout.operator('wm.sw_edit_externally', icon='TEXT')


@make_annotations
class ScriptWatcherSettings(bpy.types.PropertyGroup):
    """All the script watcher settings."""
    running = bpy.props.BoolProperty(default=False)
    reload = bpy.props.BoolProperty(default=False)

    filepath = bpy.props.StringProperty(
        name='Script',
        description='Script file to watch for changes.',
        subtype='FILE_PATH'
    )

    use_py_console = bpy.props.BoolProperty(
        name='Use py console',
        description='Use blenders built-in python console for program output (e.g. print statements and error messages)',
        default=False
    )

    auto_watch_on_startup = bpy.props.BoolProperty(
        name='Watch on startup',
        description='Watch script automatically on new .blend load',
        default=False
    )

    run_main = bpy.props.BoolProperty(
        name='Run Main',
        description='Instead of running the module with the name __main__ execute the module and call main()',
        default=False,
    )



classes = (
    SW_OP_WatchScript,
    SW_OP_StopScriptWatcher,
    SW_OP_ReloadScriptWatcher,
    SW_OP_OpenExternalEditor,

    ScriptWatcherSettings,

    SW_PT_ScriptWatcherPanel,
)

def register_watcher():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.sw_settings = bpy.props.PointerProperty(
        type=ScriptWatcherSettings
    )
    bpy.app.handlers.load_post.append(load_handler)


def unregister_watcher():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)

    bpy.app.handlers.load_post.remove(load_handler)

    del bpy.types.Scene.sw_settings