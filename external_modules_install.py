import subprocess
import sys
import os
import bpy
import site
import pkg_resources

from bpy.props import BoolProperty, StringProperty

from .blender_pip import Pip
Pip._ensure_user_site_package()

import logging
log = logging.getLogger(__name__)


def check_external_modules():
    addon_prefs = bpy.context.preferences.addons.get(__package__, None)
    try:
        import pandas
        #import openpyxl 
        #import webdavclient3
        #import lxml
        #import googleapiclient
        #import google_auth_oauthlib
        #import google_auth_httplib2
        addon_prefs.preferences.is_external_module = True
        print("emdb ci sono")
    except ImportError:
        addon_prefs.preferences.is_external_module = False
        print("emdb Non ci sono")

class OBJECT_OT_install_3dsc_missing_modules(bpy.types.Operator):
    bl_idname = "install_3dsc_missing.modules"
    bl_label = "missing modules"
    bl_options = {"REGISTER", "UNDO"}

    is_install : BoolProperty()
    list_modules_to_install: StringProperty()

    def execute(self, context):
        if self.list_modules_to_install == "Google":
            list_modules = google_list_modules()
        elif self.list_modules_to_install == "EMdb_xlsx":
            list_modules = EMdb_xlsx_modules()
        elif self.list_modules_to_install == "py3dtiles":
             list_modules = py3dtiles_modules()
        elif self.list_modules_to_install == "kml":
             list_modules = kml_modules()
        if self.is_install:
            install_modules(list_modules)
        else:
            uninstall_modules(list_modules)
        check_external_modules()
        return {'FINISHED'}

def google_list_modules():
    list_of_modules =[
        #"google-api-python-client==2.28.0",
        "google-auth-httplib2==0.1.0",
        "google-auth-oauthlib==0.4.6",
        "six==1.16.0",
        "httplib2",
        "pyparsing==2.4.7",
        "uritemplate",
        "google==3.0.0",
        #"googleapiclient"
        "google.auth==2.3.2",
        "google-api-core==2.2.2",
        "google-api-python-client==2.31.0",
        "pyasn1==0.4.8",
        "pyasn1_modules==0.2.8",
        "rsa==4.7.2",
        "cachetools==4.2.4",
        "requests_oauthlib==1.3.0",
        "oauthlib==3.1.1",
        "python-telegram-bot==13.7",
        "pytz==2021.3",
        "apscheduler==3.8.1",
        "tzlocal==4.1",
        "pytz-deprecation-shim==0.1.0.post0",
        "tornado==6.1",
        "exchange==0.3"
        ]
    return list_of_modules

def EMdb_xlsx_modules():
    # https://pypi.org/project/optimize-images/
    # da aggiungere per ottimizzare le immagini in export
    list_of_modules =[
        "pandas",
        "pytz",
        "python-dateutil",
        "numpy",
        "six",
        "openpyxl",
        "webdavclient3",
        "lxml"
    ]
    return list_of_modules

def py3dtiles_modules():
    #list_of_modules =["py3dtiles==7.0.0","psutil","pyzmq","pyproj","lz4","setuptools","numba","llvmlite"]
    #list_of_modules =["py3dtiles==7.0.0"]
    list_of_modules = (
        "cython",
        "earcut==1.1.5",
        "lz4",
        "numba",
        "numpy>=1.24.0,<2.0.0",
        "psutil",
        "pyproj",
        "pyzmq",
        "plyfile",
        "laspy>=2.0,<3.0",
        "py3dtiles=7.0.0",
        "simplekml"
    )

    return list_of_modules 


def kml_modules():
    list_of_modules = (
        "simplekml"
    )

    return list_of_modules 

def install_modules(list_of_modules):
    Pip.upgrade_pip()
    for module_istall in list_of_modules:
        Pip.install(module_istall)

def uninstall_modules(list_of_modules):
    for module_istall in list_of_modules:
        Pip.uninstall(module_istall)

classes = [
    OBJECT_OT_install_3dsc_missing_modules,
    ]

def register():
	for cls in classes:
		try:
			bpy.utils.register_class(cls)
		except ValueError as e:
			log.warning('{} is already registered, now unregister and retry... '.format(cls))
			bpy.utils.unregister_class(cls)
			bpy.utils.register_class(cls)


def unregister():
	for cls in classes:
		bpy.utils.unregister_class(cls)

if __name__ == '__main__':
    #install_modules(google_list_modules())
    install_modules(EMdb_xlsx_modules())    
