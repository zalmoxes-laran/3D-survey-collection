import os
import shutil

def list_files(startpath, output_file):
    with open(output_file, 'w') as f:
        for root, dirs, files in os.walk(startpath):
            # Filtra directory nascoste, __pycache__, e la directory dev_utils
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('addon_updater') and d != '__pycache__' and d != 'dev_utils' and d !='GPL3-license.txt' and d != 'README.md' and d !='complete-json.json' ]
            # Filtra file nascosti e rimuove file .png e .glb
            files = [file for file in files if not file.startswith('.')]
            files = [file for file in files if not (file.lower().endswith('.png') or file.lower().endswith('.glb'))]
            
            level = root.replace(startpath, '').count(os.sep)
            indent = '  ' * level
            f.write(f"{indent}- {os.path.basename(root)}/\n")
            subindent = '  ' * (level + 1)
            for file in files:
                f.write(f"{subindent}- {file}\n")

def copy_files_to_plain(startpath, output_dir, file_filter):
    # Assicura che la cartella di destinazione esista
    os.makedirs(output_dir, exist_ok=True)
    
    for root, dirs, files in os.walk(startpath):
        # Filtra directory nascoste, __pycache__, e la directory dev_utils
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'dev_utils']
        
        for file in files:
            # Se il file non è nella lista (che proviene da foldertree.txt), non copiare
            if file not in file_filter:
                continue
            
            source_file = os.path.join(root, file)
            
            # Per i file "__init__.py", aggiungi un prefisso per renderli unici
            if file == "__init__.py":
                relative_path = os.path.relpath(root, startpath)
                relative_path = relative_path.replace(os.sep, "_")  # Sostituisce i separatori con underscore
                if relative_path == ".":
                    unique_name = "[root]__init__.py"
                else:
                    unique_name = f"[{relative_path}]__init__.py"
                destination_file = os.path.join(output_dir, unique_name)
            else:
                destination_file = os.path.join(output_dir, file)
            
            # Copia il file
            shutil.copy2(source_file, destination_file)

def read_filter(file_path):
    """Legge il filtro dei file dal file foldertree.txt."""
    with open(file_path, 'r') as f:
        return [line.strip().split('- ')[-1] for line in f if line.strip().startswith('- ') and not line.strip().endswith('/')]

# Percorsi
#start_path = r"/Users/emanueldemetrescu/Library/Application Support/Blender/4.2/scripts/addons/EM-blender-tools"
start_path_file = os.path.abspath(__file__)

start_path = os.path.abspath(os.path.join(start_path_file, "../../"))

output_dir = os.path.join(os.path.dirname(start_path), "plain_code_3dsc")
folder_tree_file = os.path.join(os.path.dirname(__file__), "foldertree.txt")

# Genera la struttura dei file e salva in foldertree.txt
list_files(start_path, folder_tree_file)

# Leggi il filtro dei file dal file foldertree.txt
file_filter = read_filter(folder_tree_file)

# Copia i file nella cartella plain_code
copy_files_to_plain(start_path, output_dir, file_filter)

# Copia foldertree.txt nella cartella plain_code
shutil.copy2(folder_tree_file, os.path.join(output_dir, "foldertree.txt"))

print(f"Tutti i file filtrati e il file foldertree.txt sono stati copiati in: {output_dir}")
