"""
LOD Shortcuts Module
Gestisce le shortkey per il cambio rapido dei livelli LOD
"""

import bpy

# Dizionario per tenere traccia delle keymap
addon_keymaps = []

class WM_OT_set_lod_shortcut(bpy.types.Operator):
    """Imposta il livello LOD e attiva l'operatore di cambio LOD"""
    bl_idname = "wm.set_lod_shortcut"
    bl_label = "Set LOD Level Shortcut"
    bl_options = {'REGISTER', 'UNDO'}
    
    lod_level: bpy.props.IntProperty(
        name="LOD Level",
        description="Livello LOD da impostare (0-4)",
        default=0,
        min=0,
        max=4
    )
    
    def execute(self, context):
        # Imposta il livello LOD nella scena
        context.scene.setLODnum = self.lod_level
        
        # Chiama l'operatore object.change_lod
        try:
            bpy.ops.object.change_lod()
            self.report({'INFO'}, f"LOD{self.lod_level} applicato con successo")
        except Exception as e:
            self.report({'ERROR'}, f"Errore nell'applicazione del LOD: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


def register():
    # Registra l'operatore
    bpy.utils.register_class(WM_OT_set_lod_shortcut)
    
    # Ottieni il window manager per le keymap
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        # Crea una nuova keymap per la vista 3D
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        
        # Definisci le 5 shortkey (Ctrl+Shift+Alt + Numpad 0-4)
        lod_shortcuts = [
            ('NUMPAD_0', 0),
            ('NUMPAD_1', 1),
            ('NUMPAD_2', 2),
            ('NUMPAD_3', 3),
            ('NUMPAD_4', 4),
        ]
        
        for key, lod_level in lod_shortcuts:
            kmi = km.keymap_items.new(
                'wm.set_lod_shortcut',
                key,
                'PRESS',
                ctrl=True,
                shift=True,
                alt=True
            )
            kmi.properties.lod_level = lod_level
            addon_keymaps.append((km, kmi))
            print(f"Registrata shortkey: Ctrl+Shift+Alt+{key} per LOD{lod_level}")


def unregister():
    # Rimuovi tutte le keymap registrate
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Deregistra l'operatore
    bpy.utils.unregister_class(WM_OT_set_lod_shortcut)


if __name__ == "__main__":
    register()
