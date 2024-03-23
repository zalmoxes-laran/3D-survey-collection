import bpy
import bmesh
from mathutils import Vector
from math import radians

# Parametri
DENSITA_SOGLIA = 0.2  # soglia per la densità di vertici (esempio). Aumentando questo valore, verranno selezionati solo i vertici che sono ancora più isolati, il che implica una superficie meno densa e potenzialmente più ruvida.
VARIANZA_NORMALE_SOGLIA = radians(20)  # soglia per la variazione angolare delle normali in radianti. Riducendo questa soglia, richiederai una variazione angolare minore tra le normali per considerare una faccia come parte di una superficie ruvida. Questo significa che anche le piccole variazioni delle normali saranno considerate significative, portando alla selezione di meno facce. 

def densita_vertice(vertice, bm):
    # Calcola la densità basata sulla distanza media dai vertici vicini
    distanze = [vertice.co - e.other_vert(vertice).co for e in vertice.link_edges if e.other_vert(vertice)]
    if distanze:
        somma_distanze = sum((d.length for d in distanze), 0.0)
        return somma_distanze / len(distanze)
    return 0.0

# Ottieni l'oggetto attivo e verifica che sia una mesh
oggetto = bpy.context.active_object
if oggetto.type == 'MESH':
    # Entra in modalità di modifica e crea una BMesh
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(oggetto.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Deseleziona tutte le facce
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.mesh.select_all(action='DESELECT')

    # Analizza la mesh
    for vertice in bm.verts:
        densita = densita_vertice(vertice, bm)
        angoli = []
        for faccia in vertice.link_faces:
            for altra_faccia in vertice.link_faces:
                if faccia != altra_faccia and faccia.normal.length and altra_faccia.normal.length:
                    # Calcola l'angolo tra le normali delle facce
                    angolo = faccia.normal.angle(altra_faccia.normal)
                    angoli.append(angolo)
        
        varianza_normale = max(angoli, default=0)

        # Seleziona vertici con densità bassa e variazione alta delle normali
        if densita < DENSITA_SOGLIA and varianza_normale > VARIANZA_NORMALE_SOGLIA:
            for f in vertice.link_faces:
                f.select = True

    # Aggiorna la mesh e il viewport
    bmesh.update_edit_mesh(oggetto.data, True)
    bpy.context.view_layer.update()

    # Torna in modalità oggetto
    bpy.ops.object.mode_set(mode='OBJECT')
else:
    print("L'oggetto selezionato non è una mesh.")
