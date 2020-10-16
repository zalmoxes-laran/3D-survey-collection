# 3D-survey-collection
3D Survey Collection - shortly 3DS, an addon for Blender 2.8

Hello there! I’m **3D Survey Collection** (Blender Add-on), an open source collection of tools to improve the work-flow of a 3D survey (terrestrial or UAV photogrammetry). 

I am under constant development by [Emanuel Demetrescu](http://www.itabc.cnr.it/team/emanuel-demetrescu) during his research activities at the [CNR-ISPC](http://www.ispc.cnr.it) (Italian National Council for Research, Institute of Heritage Science) (former CNR-ITABC) within the [VHLab](http://www.itabc.cnr.it/pagine/vh-lab) (Virtual Heritage Laboratory - old page, new page under development).

Let me introduce myself with a short list the tools (sorry the images are related to the ol 2.79 version, my creator says he is too busy to update this page, but he is simply lazy..)

I need constant improvements and beta testing in real projects, so, developers out there, email my creator at emanuel.demetrescu at gmail dot com and contribute :-)

* [**Importers** panel](#importers-pane)
* [**Exporters** panel](#exporters-pane)
* [**Quick utils** panel](#quick_utils-pane)
* [**Photogrammetry** panel](#photogrammetry_tool-pane)
* [**Color Correction** panel](#color_correction_tool-pane)
* [**LOD Generator** panel](#LOD_generator-pane)

## <a name="importers-pane"></a>Importers

The **Importers** panel allows to

* import multiple objs at once (with correct orientation), for instance a bunch of models made in Photoscan, Meshroom or Zephyr 3D.
* import points as empty objects from a txt file, for instance a topographic survey made with a total station or DGPS. Optionally I can shift the values of the world coordinates (they are usually to big to be correctly managed by a computer graphic software like Blender and it is a good practice to shift them)
* If you are using BlenderGIS, I will recognize it and I can use its shifting parameters ;-), just click on "use BlenderGIS".

![Importers screenshot](https://raw.githubusercontent.com/zalmoxes-laran/BlenderLandscape/master/README_images/Importers_139.png)

## <a name="exporters-pane"></a>Exporters

The **Exporters** panel allows to

![Importers screenshot](https://raw.githubusercontent.com/zalmoxes-laran/BlenderLandscape/master/README_images/Exporters_139.png)

## <a name="quick_utils-pane"></a>Quick Utils

The **Quick Utils** panel allows to

![Importers screenshot](https://raw.githubusercontent.com/zalmoxes-laran/BlenderLandscape/master/README_images/Quick_utils_139.png)

### Fast utilities
#### turn on/off lights

### Dealing with Cycles/GLSL materials
#### create cycles materials


## <a name="photogrammetry_tool-pane"></a>Photogrammetry

The **Photogrammetry** panel allows to

![Importers screenshot](https://raw.githubusercontent.com/zalmoxes-laran/BlenderLandscape/master/README_images/Photogrammetry_tool_139.png)

## <a name="color_correction_tool-pane"></a>Color correction

The **Color correction** panel allows to

![Importers screenshot](https://raw.githubusercontent.com/zalmoxes-laran/BlenderLandscape/master/README_images/Color_correction_tool_139.png)

## <a name="LOD_generator-pane"></a>LOD generator

The **Color correction** panel allows to

![Importers screenshot](https://raw.githubusercontent.com/zalmoxes-laran/BlenderLandscape/master/README_images/LOD_generator_139.png)

### How to cite this tool

You can link this github repo [3DSC Website](https://github.com/zalmoxes-laran/BlenderLandscape "Title") or cite

	@software{demetrescu_3d_2020,
	author = {Demetrescu, Emanuel},
	title = {3D {Survey} {Collection}},
	url = {https://github.com/zalmoxes-laran/3D-survey-collection},
	version = {1.4.42},
	date = {2020-04-07},
	}

### Contact
If something goes wrong with me or if you have comments or suggestions, please report a feedback to <emanuel.demetrescu@gmail.com> 


