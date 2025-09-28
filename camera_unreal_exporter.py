# camera_unreal_exporter.py
# Camera to Unreal Engine Exporter per 3D Survey Collection
# Integrazione nel framework 3DSC

import bpy
import math
from mathutils import Vector
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, FloatProperty


class EXPORT_OT_camera_to_unreal_3dsc(Operator):
    """Export camera transform to Unreal Engine format (3DSC Integration)"""
    bl_idname = "export.camera_to_unreal_3dsc"
    bl_label = "Export Camera to Unreal"
    bl_description = "Convert selected camera transform from Blender to Unreal Engine format"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Proprietà aggiuntive per integrazione 3DSC
    use_world_shift: BoolProperty(
        name="Use World Shift",
        description="Apply 3DSC world shift coordinates",
        default=False
    )
    
    scale_factor: FloatProperty(
        name="Scale Factor", 
        description="Scale factor for units conversion (default: 100 for cm)",
        default=100.0,
        min=0.1,
        max=1000.0
    )
    
    def n180(self, a):
        """Normalizza angolo in [-180, 180]"""
        return ((a + 180.0) % 360.0) - 180.0
    
    def to_ue(self, v: Vector) -> Vector:
        """Converte coordinate Blender -> Unreal: (x, -y, z)"""
        return Vector((v.x, -v.y, v.z))
    
    def get_world_shift(self, context):
        """Ottiene i valori di shift dal 3DSC se disponibili"""
        scene = context.scene
        shift_x = getattr(scene, 'shift_x', 0.0)
        shift_y = getattr(scene, 'shift_y', 0.0) 
        shift_z = getattr(scene, 'shift_z', 0.0)
        return shift_x, shift_y, shift_z
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'CAMERA':
            self.report({'WARNING'}, "⚠️ Seleziona una CAMERA per esportare")
            return {'CANCELLED'}
        
        try:
            # Matrice world della camera
            mw = obj.matrix_world.copy()
            R = mw.to_3x3()
            
            # Assi locali in world space (Blender)
            x_bl = R.col[0]          # right
            y_bl = R.col[1]          # up  
            z_bl = R.col[2]          # forward (per camera è -Z)
            
            # Vettori in sistema Unreal
            f_ue = self.to_ue(-z_bl).normalized()  # forward UE (X+)
            u_ue = self.to_ue(y_bl).normalized()   # up UE (Z+)
            
            # ---- Calcolo Yaw & Pitch dal forward (come in UE) ----
            yaw = math.degrees(math.atan2(f_ue.y, f_ue.x))
            # Correzione segno: guardare in basso = pitch negativo
            pitch = math.degrees(math.atan2(f_ue.z, math.hypot(f_ue.x, f_ue.y)))
            
            # ---- Calcolo Roll ----
            world_up = Vector((0.0, 0.0, 1.0))
            right0 = world_up.cross(f_ue)
            
            if right0.length < 1e-6:
                right0 = Vector((1.0, 0.0, 0.0)).cross(f_ue)
            
            right0.normalize()
            up0 = f_ue.cross(right0).normalized()
            
            sin_a = up0.cross(u_ue).dot(f_ue)
            cos_a = up0.dot(u_ue)
            roll = math.degrees(math.atan2(sin_a, cos_a))
            
            # Normalizza angoli come UE
            roll = self.n180(roll)
            pitch = self.n180(pitch)
            yaw = self.n180(yaw)
            
            # ---- Location con supporto world shift 3DSC ----
            loc = mw.translation
            
            if self.use_world_shift:
                shift_x, shift_y, shift_z = self.get_world_shift(context)
                loc.x += shift_x
                loc.y += shift_y  
                loc.z += shift_z
            
            # Conversione a unità Unreal (cm)
            ue_loc = (loc.x * self.scale_factor, -loc.y * self.scale_factor, loc.z * self.scale_factor)
            
            # ---- Informazioni camera ----
            cam = obj.data
            
            # ---- Output nella console con stile 3DSC ----
            print("\n" + "="*60)
            print("🎬 3DSC - CAMERA TO UNREAL EXPORT")
            print("="*60)
            print(f"📹 Camera Name: {obj.name}")
            print(f"📍 Location (cm): X={ue_loc[0]:.3f}, Y={ue_loc[1]:.3f}, Z={ue_loc[2]:.3f}")
            print(f"🔄 Rotation (deg): Roll={roll:.3f}, Pitch={pitch:.3f}, Yaw={yaw:.3f}")
            print(f"📐 UE Rotator (P,Y,R): ({pitch:.3f}, {yaw:.3f}, {roll:.3f})")
            print(f"🎯 Focal Length: {cam.lens:.2f} mm")
            print(f"📏 Sensor Size: {cam.sensor_width:.2f} × {cam.sensor_height:.2f} mm")
            
            if self.use_world_shift:
                shift_x, shift_y, shift_z = self.get_world_shift(context)
                print(f"🌍 World Shift Applied: X={shift_x:.3f}, Y={shift_y:.3f}, Z={shift_z:.3f}")
            
            print(f"📏 Scale Factor: {self.scale_factor}")
            print("="*60)
            
            # Copia negli appunti per facilità d'uso (opzionale)
            clipboard_text = f"Location: {ue_loc[0]:.3f}, {ue_loc[1]:.3f}, {ue_loc[2]:.3f}\nRotation: {pitch:.3f}, {yaw:.3f}, {roll:.3f}"
            context.window_manager.clipboard = clipboard_text
            
            # Messaggio di successo
            self.report({'INFO'}, f"✅ Camera '{obj.name}' esportata per Unreal - Dati copiati negli appunti")
            
        except Exception as e:
            self.report({'ERROR'}, f"❌ Errore durante l'esportazione: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class VIEW3D_PT_camera_unreal_3dsc(Panel):
    """Pannello Camera to Unreal integrato in 3DSC"""
    bl_label = "Camera to Unreal"
    bl_idname = "VIEW3D_PT_camera_unreal_3dsc"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '3DSC'  # Integrazione nella categoria 3DSC esistente
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        # Header con icona 3DSC style
        row = layout.row()
        row.label(text="🎮 Unreal Engine Export", icon='EXPORT')
        
        layout.separator()
        
        # Status camera
        if obj and obj.type == 'CAMERA':
            box = layout.box()
            box.label(text=f"✅ Camera: {obj.name}", icon='CAMERA_DATA')
            
            # Proprietà export
            col = layout.column(align=True)
            col.label(text="📋 Export Settings:")
            
            op = col.operator("export.camera_to_unreal_3dsc", 
                            text="Export Camera Transform", 
                            icon='CONSOLE')
            
            # Opzioni avanzate
            box = layout.box()
            box.label(text="⚙️ Advanced Options:", icon='SETTINGS')
            
            col = box.column(align=True)
            col.prop(op, "scale_factor")
            col.prop(op, "use_world_shift")
            
        else:
            box = layout.box()
            box.label(text="⚠️ Seleziona una Camera", icon='ERROR')
            
            # Pulsante disabilitato
            row = layout.row()
            row.enabled = False
            row.operator("export.camera_to_unreal_3dsc", 
                        text="Export Camera Transform", 
                        icon='CONSOLE')
        
        layout.separator()
        
        # Istruzioni stile 3DSC
        col = layout.column(align=True)
        col.label(text="📋 Instructions:")
        col.label(text="1. Select a Camera object")
        col.label(text="2. Configure export settings")
        col.label(text="3. Click Export Camera Transform")
        col.label(text="4. Check Console for output")
        col.label(text="5. Data copied to clipboard")


# Classi da registrare
classes = [
    EXPORT_OT_camera_to_unreal_3dsc,
    VIEW3D_PT_camera_unreal_3dsc,
]


def register():
    """Registrazione per integrazione 3DSC"""
    for cls in classes:
        bpy.utils.register_class(cls)
    print("🎬 Camera to Unreal Exporter (3DSC) registered!")


def unregister():
    """De-registrazione per integrazione 3DSC"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()