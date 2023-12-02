import bpy 

def make_annotations(cls):
    """Converts class fields to annotations if running with Blender 2.8"""
    if bpy.app.version < (2, 80):
        return cls
    PropType = type(bpy.props.IntProperty())
    bl_props = {k: v for k, v in cls.__dict__.items() if isinstance(v, PropType)}
    if bl_props:
        if '__annotations__' not in cls.__dict__:
            setattr(cls, '__annotations__', {})
        annotations = cls.__dict__['__annotations__']
        for k, v in bl_props.items():
            annotations[k] = v
            delattr(cls, k)
    return cls


def update_ui_panel():
    for area in bpy.context.window.screen.areas:
        if area.type == 'TEXT_EDITOR':
            for region in area.regions:
                if region.type == 'UI':
                    region.tag_redraw()
                    
                    
def operator_with_context(op, ctx, **kwargs):
    """Execute an operator with a specific context"""

    if bpy.app.version < (4, 0, 0):
        op(ctx, **kwargs)
    else:
        context_override = bpy.context.copy()
        context_override.update(ctx)
        with bpy.context.temp_override(context_override):
            op(**kwargs)