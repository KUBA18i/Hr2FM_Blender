# Heretic ][ FlexModel add-on for Blender
Blender add-on for import/export of Heretic 2's FlexModels (.fm)

# Examples
1.An Ogle's model being imported into the Blender scene, with imported textures and mesh nodes turned into vertex groups.  
![Ogle model in Blender](https://i.imgur.com/5IhF6ku.png)  
2. Corvus's imported model in Blender, with empty objects representing joints and references, and additional vertex groups for clusters. 
![Corvus model in Blender](https://i.imgur.com/X4UVci8.png)  
3. An exported player model of Mario, with all the required set-up.  
![Mario set-up in Blender](https://i.imgur.com/lqphTkx.png)  
![In-game screenshot of the Mario player model](https://i.imgur.com/rmVZDZy.png)  
Open links to see videos of the model in action:  
[Part 1](https://imgur.com/pSpfBKL)  
[Part 2](https://imgur.com/FTv51MJ)  

# Usage Manual
## Import
![Import FlexModel menu](https://i.imgur.com/wDXknLX.png)  
* You're given the option to import UVs from either the Triangle/UV structs, or from the GL Commands block.  
* You can either import a static mesh, or animated with shape keys.  
* If importing a static mesh, the base frame will be the only one that's imported. Otherwise, all shape keys will based on it.  
* If the Import Textures option is checked, the program will take the model's skin paths and try to find their corresponding .M8 files in the same folder as the model.  
* If importing animations, you have the option to populate the timeline with markers, depending on the frame names.  
* Mesh nodes will be imported as vertex groups, with a naming scheme of `__FM_Meshnode_<number>`. Clusters, if importing a skeleton, will also be imported, named  `__FM_Cluster_<number>`.
* If importing References or the Skeleton, the reference placements and joints will be imported as animated empties, respectively named `__FM_Ref_<number>_<name>` and `__FM_Joint_<number>_<name>`.

## Export
![Export FlexModel menu](https://i.imgur.com/RtciOQj.png)  
* You can select multiple objects to be exported as a single model. Their total material and surface lists will be fused after the objects are sorted in alphabetic order.  
* Unless you are creating player models, material names will be used as path names that the game looks for to find textures, so make sure they point to valid files (with an.m8 extension).  
* If the Export Textures option is checked, the materials' textures will be saved as .m8 files, in the same folder as the model. The filename will be trimmed to only the stem.  
* If the corresponding option is checked, the objects' vertex groups will be used to create mesh nodes, using the naming scheme of `__FM_Meshnode_<number>`. Otherwise, a single default surface will be made.  
* You can either export a static mesh, or an animation range. The export will fail if the vertex count changes throughout the timeline.  
* You can create frame names from timeline markers, or set to default values of `frame#`.  
* If the option to export the skeleton is checked, empties named `__FM_Joint_<number>_<name>` will be used to create placements, and vertex groups named `__FM_Cluster_<number>` will be used to create clusters. Make sure to pick the correct skeleton type before exporting.  
* If the option to export references is checked, empties named `__FM_Ref_<number>_<name>` will be used to create placements. Make sure to pick the correct reference type before exporting.  

# Installation
You can install this add-on like any other: grab the zip from the releases, or download the repo. In Blender, select `Edit > Preferences > Add-ons > Install` and pick the zip you just downloaded. Then you can enable it in the add-on list.

# Credits
This add-on was made by Jakub Majewski.  
Heretic ][ and its model format is by Raven Software.  
Blender is by the Blender Foundation.  
I used the following as reference:  
* Kingpin MD2/MDX addon by Hypov8; their GL Commands builder was very useful to me.  
*  `Blender_BSP_Importer` by SomaZ; the way it converted between MD3 tags and empty objects was very useful here.  
* An old program known as MipMaker, by ViTalSoftware; to understand the structure of the M8 texture format.  
* The Heretic2R repo by M-x-d was crucial in understanding how the FlexModel format works.  
