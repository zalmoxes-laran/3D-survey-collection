import json
import os
import re
import textwrap

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

_DOCS_BASE = "https://docs.extendedmatrix.org/projects/3DSC/en"


def _addon_root_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalize_version(version_str):
    if not version_str:
        return ""
    match = re.match(r"^(\d+\.\d+\.\d+)", str(version_str).strip())
    return match.group(1) if match else str(version_str).strip()


def get_docs_version():
    root_dir = _addon_root_dir()

    manifest_path = os.path.join(root_dir, "blender_manifest.toml")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("version") and "=" in stripped:
                        version_raw = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                        version = _normalize_version(version_raw)
                        if version:
                            return version
        except OSError:
            pass

    version_json_path = os.path.join(root_dir, "version.json")
    if os.path.exists(version_json_path):
        try:
            with open(version_json_path, "r", encoding="utf-8") as f:
                version_data = json.load(f)
            major = version_data.get("major")
            minor = version_data.get("minor")
            patch = version_data.get("patch")
            if major is not None and minor is not None and patch is not None:
                return f"{major}.{minor}.{patch}"
        except (OSError, ValueError, TypeError):
            pass

    # Fallback to addon bl_info version tuple (e.g. (1, 6, 2) -> "1.6.2")
    try:
        from .. import get_3dsc_bl_info
        bl_info = get_3dsc_bl_info()
        version_tuple = bl_info.get("version")
        if isinstance(version_tuple, tuple) and len(version_tuple) >= 3:
            return f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}"
    except Exception:
        pass

    return "latest"


def build_docs_url(path=""):
    path = (path or "").strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path

    version = get_docs_version()
    clean_path = path.lstrip("/")
    if clean_path:
        return f"{_DOCS_BASE}/{version}/{clean_path}"
    return f"{_DOCS_BASE}/{version}/"


class E3DSC_OT_help_popup(Operator):
    bl_idname = "e3dsc.help_popup"
    bl_label = "3DSC Help"
    bl_description = "Show a contextual help popup with a link to online docs"

    title: StringProperty(name="Title", default="3D Survey Collection Help")  # type: ignore
    text: StringProperty(name="Text", default="")  # type: ignore
    url: StringProperty(name="Documentation Path", default="")  # type: ignore

    def invoke(self, context, event):
        self._popup_width = 460
        return context.window_manager.invoke_popup(self, width=self._popup_width)

    def _wrapped_lines(self, context):
        region_width = getattr(context.region, "width", self._popup_width if hasattr(self, "_popup_width") else 420)
        usable_width = min(region_width, self._popup_width if hasattr(self, "_popup_width") else 460)
        wrap_width = max(32, min(58, int(usable_width / 7.4)))

        raw_text = (self.text or "").replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = raw_text.split("\n")
        lines = []
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                lines.append("")
                continue
            wrapped = textwrap.wrap(
                paragraph,
                width=wrap_width,
                break_long_words=False,
                break_on_hyphens=False,
            )
            lines.extend(wrapped if wrapped else [""])
        return lines or ["No help text available."]

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.title, icon='INFO')

        wrapped_lines = self._wrapped_lines(context)
        col = layout.column(align=True)
        for line in wrapped_lines:
            if line:
                col.label(text=line)
            else:
                col.separator()

        docs_url = build_docs_url(self.url)
        row = layout.row(align=True)
        row.operator("wm.url_open", text="Open Documentation", icon='URL').url = docs_url
        layout.label(text="Click outside this panel to close.", icon='INFO')

    def execute(self, context):
        return {'FINISHED'}


classes = (
    E3DSC_OT_help_popup,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
