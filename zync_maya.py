"""
ZYNC Submit

This module provides a maya + Python implementation of the web-based ZYNC
Job Submit GUI. There are a few advantages to doing render submissions to ZYNC
from within maya:
    * extensive preflight checking possible
    * less context switching between the browser and maya

Usage:
    import zync_maya
    zync_maya.submit_dialog()

"""

from functools import partial
import hashlib
import re
import os
import platform
import sys
import time

__author__ = 'Alex Schworer'
__copyright__ = 'Copyright 2011, Atomic Fiction, Inc.'

config_path = '%s/config_maya.py' % ( os.path.dirname(__file__), )
if not os.path.exists( config_path ):
    raise Exception('Could not locate config_maya.py, please create.')
from config_maya import *

required_config = ['API_DIR', 'API_KEY']

for key in required_config:
    if not key in globals():
        raise Exception('config_maya.py must define a value for %s.' % (key,))

sys.path.append(API_DIR)
import zync
ZYNC = zync.Zync('maya_plugin', API_KEY)

UI_FILE = '%s/resources/submit_dialog.ui' % (os.path.dirname(__file__),)

import maya.cmds as cmds
import maya.mel

def generate_scene_path(extra_name=None):
    """
    Returns a hash-embedded scene path with /cloud_submit/ at the end
    of the path, for separation from user scenes.

    TODO: factor out into zync python module
    """
    scene_path = cmds.file(q=True, loc=True)

    scene_dir = os.path.dirname(scene_path)
    cloud_dir = '%s/cloud_submit' % ( scene_dir, ) 

    if not os.path.exists(cloud_dir):
        os.makedirs(cloud_dir)

    scene_name = os.path.basename(scene_path)

    local_time = time.localtime()

    times = [local_time.tm_mon, local_time.tm_mday, local_time.tm_year,
             local_time.tm_hour, local_time.tm_min, local_time.tm_sec]
    timecode = ''.join(['%02d' % x for x in times])

    old_filename = re.split('.ma', scene_name)[0]
    if extra_name:
        old_filename = '_'.join([old_filename, extra_name])
    to_hash = '_'.join([old_filename, timecode])
    hash = hashlib.md5(to_hash).hexdigest()[-6:]

    # filename will be something like: shotName_comp_v094_37aa20.nk
    new_filename = '_'.join([old_filename, hash]) + '.ma'

    return '%s/%s' % ( cloud_dir, new_filename )

def label_ui(label, ui, *args, **kwargs):
    """
    Helper function that creates an UI element with a text label next to it.
    """
    cmds.text(label=label)
    return getattr(cmds, ui)(*args, **kwargs)

def eval_ui(path, type='textField', **kwargs):
    """
    Returns the value from the given ui element
    """
    return getattr(cmds, type)(path, query=True, **kwargs)

def proj_dir():
    """
    Returns the project dir in the current scene
    """
    return cmds.workspace(q=True, rd=True)

def proj_name():
    """
    Returns the name of the project
    """
    tokens = proj_dir().split(os.path.sep)
    if 'show' in tokens:
        index = tokens.index('show')
        return tokens[index+1]
    else:
        return 'alex_test'

def frame_range():
    """
    Returns the frame-range of the maya scene as a string, like:
        1001-1350
    """
    start = str(int(cmds.getAttr('defaultRenderGlobals.startFrame')))
    end = str(int(cmds.getAttr('defaultRenderGlobals.endFrame')))
    return '%s-%s' % (start, end)

def seq_to_glob(in_path):
    head = os.path.dirname(in_path)
    base = os.path.basename(in_path)
    match = list(re.finditer('\d+', base))[-1]
    new_base = '%s*%s' % (base[:match.start()], base[match.end():])
    return '%s/%s' % (head, new_base)

def _file_handler(node):
    """Returns the file referenced by the given node"""
    texture_path = cmds.getAttr('%s.fileTextureName' % (node,))
    try:
        if cmds.getAttr('%s.useFrameExtension' % (node,)) == True:
            out_path = seq_to_glob(texture_path)
        elif texture_path.find('<UDIM>') != -1:
            out_path = texture_path.replace('<UDIM>', '*')
        else:
            out_path = texture_path
        yield (out_path,)
        arnold_use_tx = False
        try:
            arnold_use_tx = cmds.getAttr('defaultArnoldRenderOptions.use_existing_tiled_textures')
        except:
            arnold_use_tx = False
        if arnold_use_tx:
            head, ext = os.path.splitext(out_path)
            tx_path = '%s.tx' % (head,)
            if os.path.exists(tx_path):
                yield (tx_path,)
    except:
        yield (texture_path,)

def _cache_file_handler(node):
    """Returns the files references by the given cacheFile node"""
    path = cmds.getAttr('%s.cachePath' % node)
    cache_name = cmds.getAttr('%s.cacheName' % node)

    yield ('%s/%s.mc' % (path, cache_name),
           '%s/%s.mcx' % (path, cache_name),
           '%s/%s.xml' % (path, cache_name),)

def _diskCache_handler(node):
    """Returns disk caches"""
    yield (cmds.getAttr('%s.cacheName' % node),)

def _vrmesh_handler(node):
    """Handles vray meshes"""
    yield (cmds.getAttr('%s.fileName' % node),)

def _mrtex_handler(node):
    """Handles mentalrayTexutre nodes"""
    yield (cmds.getAttr('%s.fileTextureName' % node),)

def _gpu_handler(node):
    """Handles gpuCache nodes"""
    yield (cmds.getAttr('%s.cacheFileName' % node),)

def _mrOptions_handler(node):
    """Handles mentalrayOptions nodes, for Final Gather"""
    mapName = cmds.getAttr('%s.finalGatherFilename' % node).strip()
    if mapName != "":
        path = cmds.workspace(q=True, rd=True)
        if path[-1] != "/":
            path += "/"
        path += "renderData/mentalray/finalgMap/"
        path += mapName
        #if not mapName.endswith( ".fgmap" ):
        #    path += ".fgmap"
        path += "*"
        yield (path,)

def _mrIbl_handler(node):
    """Handles mentalrayIblShape nodes"""
    yield (cmds.getAttr('%s.texture' % node),)

def _abc_handler(node):
    """Handles AlembicNode nodes"""
    yield (cmds.getAttr('%s.abc_File' % node),)

def _vrSettings_handler(node):
    """Handles VRaySettingsNode nodes, for irradiance map"""
    irmap = cmds.getAttr('%s.ifile' % node)
    if cmds.getAttr('%s.imode' % node) == 7:
        if irmap.find('.') == -1:
            irmap += '*'
        else:
            last_dot = irmap.rfind('.')
            irmap = '%s*%s' % (irmap[:last_dot], irmap[last_dot:])
    yield (irmap,
           cmds.getAttr('%s.fnm' % node),)

def _particle_handler(node):
    project_dir = cmds.workspace(q=True, rd=True)
    if project_dir[-1] == '/':
        project_dir = project_dir[:-1]
    if node.find('|') == -1:
        node_base = node
    else:
        node_base = node.split('|')[-1]
    path = None
    try:
        startup_cache = cmds.getAttr('%s.scp' % (node,)).strip()
        if startup_cache in (None, ''):
            path = None
        else:
            path = '%s/particles/%s/%s*' % (project_dir, startup_cache, node_base)
    except:
        path = None
    if path == None:
        scene_base, ext = os.path.splitext(os.path.basename(cmds.file(q=True, loc=True)))
        path = '%s/particles/%s/%s*' % (project_dir, scene_base, node_base)
    yield (path,)

def _ies_handler(node):
    """Handles VRayLightIESShape nodes, for IES lighting files"""
    yield (cmds.getAttr('%s.iesFile' % node),)

def _fur_handler(node):
    """Handles FurDescription nodes"""
    #
    #   Find all "Map" attributes and see if they have stored file paths.
    #
    for attr in cmds.listAttr(node):
        if attr.find('Map') != -1 and cmds.attributeQuery(attr, node=node, at=True) == 'typed':
            index_list = ['0', '1']
            for index in index_list:
                try:
                    map_path = cmds.getAttr('%s.%s[%s]' % (node, attr, index))
                    if map_path != None and map_path != '':
                        yield (map_path,)
                except:
                    pass

def _ptex_handler(node):
    """Handles Mental Ray ptex nodes"""
    yield(cmds.getAttr('%s.S00' % node),)

def _substance_handler(node):
    """Handles Vray Substance nodes"""
    yield(cmds.getAttr('%s.p' % node),)

def _imagePlane_handler(node):
    """Handles Image Planes"""
    texture_path = cmds.getAttr('%s.imageName' % (node,))
    try:
        if cmds.getAttr('%s.useFrameExtension' % (node,)) == True:
            yield (seq_to_glob(texture_path),)
        else:
            yield (texture_path,)
    except:
        yield (texture_path,)

def _mesh_handler(node):
    """Handles Mesh nodes, in case they are using MR Proxies"""
    try:
        proxy_path = cmds.getAttr('%s.miProxyFile' % (node,))
        if proxy_path != None:
            yield (proxy_path,)
    except:
        pass

def _dynGlobals_handler(node):
    """Handles dynGlobals nodes"""
    project_dir = cmds.workspace(q=True, rd=True)
    if project_dir[-1] == '/':
        project_dir = project_dir[:-1]
    cache_dir = cmds.getAttr('%s.cd' % (node,))
    if cache_dir not in (None, ''):
        path = '%s/particles/%s/*' % (project_dir, cache_dir.strip())
        yield (path,)

def _aiStandIn_handler(node):
    """Handles aiStandIn nodes"""
    yield (cmds.getAttr('%s.dso' % (node,)),)

def get_scene_files():
    """Returns all of the files being used by the scene"""
    file_types = {'file': _file_handler,
                  'cacheFile': _cache_file_handler,
                  'diskCache': _diskCache_handler,
                  'VRayMesh': _vrmesh_handler,
                  'mentalrayTexture': _mrtex_handler,
                  'gpuCache': _gpu_handler,
                  'mentalrayOptions': _mrOptions_handler,
                  'mentalrayIblShape': _mrIbl_handler,
                  'AlembicNode': _abc_handler,
                  'VRaySettingsNode': _vrSettings_handler,
                  'particle': _particle_handler,
                  'VRayLightIESShape': _ies_handler,
                  'FurDescription': _fur_handler,
                  'mib_ptex_lookup': _ptex_handler,
                  'substance': _substance_handler,
                  'imagePlane': _imagePlane_handler,
                  'mesh': _mesh_handler,
                  'dynGlobals': _dynGlobals_handler,
                  'aiStandIn': _aiStandIn_handler}

    for file_type in file_types:
        handler = file_types.get(file_type)
        nodes = cmds.ls(type=file_type)
        for node in nodes:
            for files in handler(node):
                for scene_file in files:
                    if scene_file != None:
                        yield scene_file.replace('\\', '/')

def get_default_extension(renderer):
    """Returns the filename prefix for the given renderer, either mental ray 
       or maya software.
    """
    if renderer == "sw":
        menu_grp = 'imageMenuMayaSW'
    elif renderer == "mr":
        menu_grp = 'imageMenuMentalRay'
    else:
        raise Exception('Invalid Renderer: %s' % renderer)
    try:
        val = cmds.optionMenuGrp(menu_grp, q=True, v=True)
    except RuntimeError:
        msg = 'Please open the Maya Render globals before submitting.'
        raise Exception(msg)
    else:
        return val.split()[-1][1:-1]

LAYER_INFO = {}
def collect_layer_info(layer, renderer):
    cur_layer = cmds.editRenderLayerGlobals(q=True, currentRenderLayer=True)
    cmds.editRenderLayerGlobals(currentRenderLayer=layer)

    layer_info = {}

    # get list of active render passes
    layer_info['render_passes'] = []
    if renderer == "vray" and cmds.getAttr('vraySettings.imageFormatStr') != 'exr (multichannel)' and cmds.getAttr('vraySettings.relements_enableall') != False: 
        pass_list = cmds.ls(type='VRayRenderElement')
        pass_list += cmds.ls(type='VRayRenderElementSet')
        for r_pass in pass_list:
            if cmds.getAttr('%s.enabled' % (r_pass,)) == True:
                layer_info['render_passes'].append(r_pass)

    # get prefix information
    if renderer == 'vray':
        node = 'vraySettings'
        attribute = 'fileNamePrefix'
    elif renderer in ("sw", "mr"):
        node = 'defaultRenderGlobals'
        attribute = 'imageFilePrefix'
    try:
        layer_prefix = cmds.getAttr('%s.%s' % (node, attribute))
        layer_info['prefix'] = layer_prefix
    except Exception:
        layer_info['prefix'] = ''

    cmds.editRenderLayerGlobals(currentRenderLayer=cur_layer)
    return layer_info

def clear_layer_info():
    global LAYER_INFO
    LAYER_INFO = {}

def get_layer_override(layer, renderer, field):
    global LAYER_INFO
    if layer not in LAYER_INFO:
        LAYER_INFO[layer] = collect_layer_info(layer, renderer)
    return LAYER_INFO[layer][field]

def get_maya_version():
    api_version = maya.mel.eval("about -api")
    maya_version = 2013 # default
    # 2012
    if api_version in range( 201215, 201299 ):
        maya_version = 2012
    # 2013
    elif api_version in range( 201300, 201349 ):
        maya_version = 2013
    # 2013.5
    elif api_version in range( 201350, 201399 ):
        maya_version = 2013.5
    # 2014
    elif api_version in range( 201400, 201499 ):
        maya_version = 2014
    else:
        version_split = str(cmds.fileInfo( "version", query=True )[0]).split(" ")
        if len(version_split) > 1:
            maya_version = " ".join(version_split[:-1]).strip()
        else:
            maya_version = " ".join(version_split).strip()
    return str(maya_version)

class MayaZyncException(Exception):
    """
    This exception issues a Maya warning.
    """
    def __init__(self, msg, *args, **kwargs):
        cmds.warning(msg)
        super(MayaZyncException, self).__init__(msg, *args, **kwargs)

class SubmitWindow(object):
    """
    A Maya UI window for submitting to ZYNC
    """
    def __init__(self, title='ZYNC Submit'):
        """
        Constructs the window.
        You must call show() to display the window.

        """
        self.title = title

        scene_name = cmds.file(q=True, loc=True)
        if scene_name == 'unknown':
            cmds.error( 'Please save your script before launching a job.' ) 

        project_response = ZYNC.get_project_name( scene_name )
        if project_response["code"] != 0:
            cmds.error( project_response["response"] )
        self.new_project_name = project_response["response"]

        self.num_instances = 1
        self.priority = 50
        self.parent_id = None

        self.project = proj_dir()
        if self.project[-1] == "/":
            self.project = self.project[:-1]
			
        # set output directory. if the workspace has a mapping for "images", use that.
        # otherwise default to the images/ folder.
        self.output_dir = cmds.workspace(q=True, rd=True)
        if self.output_dir[-1] != '/':
            self.output_dir += '/'
        images_rule = cmds.workspace(fileRuleEntry='images')
        if images_rule != None and images_rule.strip() != '':
            if images_rule[0] == '/' or images_rule[1] == ':':
                self.output_dir = images_rule
            else:
                self.output_dir += images_rule
        else:
            self.output_dir += 'images'

        self.frange = frame_range()
        self.frame_step = cmds.getAttr('defaultRenderGlobals.byFrameStep')
        self.chunk_size = 10
        self.upload_only = 0
        self.start_new_slots = 0
        self.skip_check = 0
        self.notify_complete = 0
        self.vray_nightly = 0
        self.use_vrscene = 0
        self.distributed = 0
        self.use_mi = 1
        self.ignore_plugin_errors = 0

        mi_setting = ZYNC.get_config( var="USE_MI" )
        if mi_setting in ( None, "", 1, "1" ):
            self.force_mi = True
        else:
            self.force_mi = False

        self.init_layers()

        self.x_res = cmds.getAttr('defaultResolution.width')
        self.y_res = cmds.getAttr('defaultResolution.height')

        self.username = ''
        self.password = ''

        self.name = self.loadUI(UI_FILE)

        self.check_references()

    def loadUI(self, ui_file):
        """
        Loads the UI and does an post-load commands
        """

        # monkey patch the cmds module for use when the UI gets loaded
        cmds.submit_callb = partial(self.get_initial_value, self)
        cmds.do_submit_callb = partial(self.submit, self)

        if cmds.window('SubmitDialog', q=True, ex=True):
            cmds.deleteUI('SubmitDialog')
        name = cmds.loadUI(f=ui_file)

        cmds.textScrollList('layers', e=True, append=self.layers)

        # check for existing projects to determine how project selection should
        # be displayed
        num_existing_projs = cmds.optionMenu('existing_project_name', q=True, ni=True)
        if num_existing_projs == 0:
            cmds.radioButton('existing_project', e=True, en=False)
        else:
            cmds.radioButton('existing_project', e=True, en=True)

        # callbacks
        cmds.checkBox('upload_only', e=True, changeCommand=self.upload_only_toggle)
        cmds.checkBox('distributed', e=True, changeCommand=self.distributed_toggle)
        cmds.optionMenu('renderer', e=True, changeCommand=self.change_renderer)
        cmds.radioButton('new_project', e=True, onCommand=self.select_new_project)
        cmds.radioButton('existing_project', e=True, onCommand=self.select_existing_project)
        self.change_renderer( self.renderer )
        self.select_new_project( True )

        return name

    def upload_only_toggle( self, checked ):
        if checked:
            cmds.textField('num_instances', e=True, en=False)
            cmds.optionMenu('instance_type', e=True, en=False)
            cmds.checkBox('start_new_slots', e=True, en=False)
            cmds.checkBox('skip_check', e=True, en=False)
            cmds.checkBox('distributed', e=True, en=False)
            cmds.textField('output_dir', e=True, en=False)
            cmds.optionMenu('renderer', e=True, en=False)
            cmds.checkBox('vray_nightly', e=True, en=False)
            cmds.checkBox('use_vrscene', e=True, en=False)
            cmds.checkBox('use_mi', e=True, en=False)
            cmds.textField('frange', e=True, en=False)
            cmds.textField('frame_step', e=True, en=False)
            cmds.textField('chunk_size', e=True, en=False)
            cmds.optionMenu('camera', e=True, en=False)
            cmds.textScrollList('layers', e=True, en=False)
            cmds.textField('x_res', e=True, en=False)
            cmds.textField('y_res', e=True, en=False)
        else:
            cmds.textField('num_instances', e=True, en=True)
            cmds.optionMenu('instance_type', e=True, en=True)
            cmds.checkBox('start_new_slots', e=True, en=True)
            cmds.checkBox('skip_check', e=True, en=True)
            cmds.textField('output_dir', e=True, en=True)
            cmds.optionMenu('renderer', e=True, en=True)
            if eval_ui('renderer', type='optionMenu', v=True) in ("vray", "V-Ray"):
                cmds.checkBox('vray_nightly', e=True, en=True)
                cmds.checkBox('use_vrscene', e=True, en=True)
                cmds.checkBox('distributed', e=True, en=True)
            else:
                cmds.checkBox('vray_nightly', e=True, en=False)
                cmds.checkBox('use_vrscene', e=True, en=False)
                cmds.checkBox('distributed', e=True, en=False)
            if eval_ui('renderer', type='optionMenu', v=True) in ("mr", "Mental Ray") and not self.force_mi:
                cmds.checkBox('use_mi', e=True, en=True)
            else:
                cmds.checkBox('use_mi', e=True, en=False)
            cmds.textField('frange', e=True, en=True)
            cmds.textField('frame_step', e=True, en=True)
            cmds.textField('chunk_size', e=True, en=True)
            cmds.optionMenu('camera', e=True, en=True)
            cmds.textScrollList('layers', e=True, en=True)
            cmds.textField('x_res', e=True, en=True)
            cmds.textField('y_res', e=True, en=True)

    def distributed_toggle( self, checked ):
        if checked:
            cmds.checkBox('use_vrscene', e=True, en=False)
        else:
            cmds.checkBox('use_vrscene', e=True, en=True)

    def change_renderer( self, renderer ):
        if renderer in ("vray", "V-Ray"):
            cmds.checkBox('vray_nightly', e=True, en=True)
            cmds.checkBox('use_vrscene', e=True, en=True)
            cmds.checkBox('distributed', e=True, en=True)
        else:
            cmds.checkBox('vray_nightly', e=True, en=False)
            cmds.checkBox('use_vrscene', e=True, en=False)
            cmds.checkBox('distributed', e=True, en=False)
        if renderer in ("mr", "Mental Ray"):
            if self.force_mi:
                cmds.checkBox('use_mi', e=True, en=False)
            else:
                cmds.checkBox('use_mi', e=True, en=True)
            cmds.checkBox('use_mi', e=True, v=True)
        else:
            cmds.checkBox('use_mi', e=True, en=False)
            cmds.checkBox('use_mi', e=True, v=False)

    def select_new_project(self, selected):
        if selected:
            cmds.textField('new_project_name', e=True, en=True)
            cmds.optionMenu('existing_project_name', e=True, en=False)

    def select_existing_project(self, selected):
        if selected:
            cmds.textField('new_project_name', e=True, en=False)
            cmds.optionMenu('existing_project_name', e=True, en=True)

    def check_references(self):
        """
        Run any checks to ensure all reference files are accurate. If not,
        raise an Exception to halt the submit process.

        This function currently does nothing. Before Maya Binary was supported
        it checked to ensure no .mb files were being used.
        """

        #for ref in cmds.file(q=True, r=True):
        #    if check_failed:
        #        raise Exception(msg)
        pass

    def get_render_params(self):
        """
        Returns a dict of all the render parameters set on the UI
       """
        params = dict()

        if cmds.radioButton('existing_project', q=True, sl=True) == True:
            proj_name = eval_ui('existing_project_name', 'optionMenu', v=True)
            if proj_name == None or proj_name.strip() == '':
                cmds.error('Your project name cannot be blank. Please select New Project and enter a name.')
        else:
            proj_name = eval_ui('new_project_name', text=True)
        params['proj_name'] = proj_name

        parent = eval_ui('parent_id', text=True).strip()
        if parent != None and parent != "":
            params['parent_id'] = parent
        params['upload_only'] = int(eval_ui('upload_only', 'checkBox', v=True))
        params['start_new_slots'] = int( not eval_ui('start_new_slots', 'checkBox', v=True) )
        params['skip_check'] = int(eval_ui('skip_check', 'checkBox', v=True))
        params['notify_complete'] = int(eval_ui('notify_complete', 'checkBox', v=True))
        params['project'] = eval_ui('project', text=True)
        params['out_path'] = eval_ui('output_dir', text=True)
        params['ignore_plugin_errors'] = int(eval_ui('ignore_plugin_errors', 'checkBox', v=True))

        render = eval_ui('renderer', type='optionMenu', v=True)
        for k in ZYNC.MAYA_RENDERERS:
            if ZYNC.MAYA_RENDERERS[k] == render:
                params['renderer'] = k
                break
        else:
            params['renderer'] = zync.MAYA_DEFAULT_RENDERER

        params['priority'] = int(eval_ui('priority', text=True))
        params['num_instances'] = int(eval_ui('num_instances', text=True))

        selected_type = eval_ui('instance_type', 'optionMenu', v=True)
        for inst_type in ZYNC.INSTANCE_TYPES:
            if selected_type.split(' ')[0] == inst_type:
                params['instance_type'] = ZYNC.INSTANCE_TYPES[inst_type]['csp_label']
                break
        else:
            params['instance_type'] = zync.DEFAULT_INSTANCE_TYPE

        params['frange'] = eval_ui('frange', text=True)
        params['step'] = int(eval_ui('frame_step', text=True))
        params['chunk_size'] = int(eval_ui('chunk_size', text=True))
        params['camera'] = eval_ui('camera', 'optionMenu', v=True)
        params['xres'] = int(eval_ui('x_res', text=True))
        params['yres'] = int(eval_ui('y_res', text=True))

        if params['upload_only'] == 0 and params['renderer'] == 'vray':
            params['vray_nightly'] = int(eval_ui('vray_nightly', 'checkBox', v=True))
            params['use_vrscene'] = int(eval_ui('use_vrscene', 'checkBox', v=True))
            params['distributed'] = int(eval_ui('distributed', 'checkBox', v=True))
            params['use_mi'] = 0
        elif params['upload_only'] == 0 and params['renderer'] == 'mr':
            params['vray_nightly'] = 0
            params['use_vrscene'] = 0
            params['distributed'] = 0
            params['use_mi'] = int(eval_ui('use_mi', 'checkBox', v=True))
        else:
            params['vray_nightly'] = 0
            params['use_vrscene'] = 0
            params['distributed'] = 0
            params['use_mi'] = 0

        return params

    def show(self):
        """
        Displays the window.
        """
        cmds.showWindow(self.name)

    def init_layers(self):
        self.layers = []
        try:
            all_layers = cmds.ls(type='renderLayer',showNamespace=True)
            for i in range( 0, len(all_layers), 2 ):
                if all_layers[i+1] == ':':
                    self.layers.append( all_layers[i] )
        except Exception:
            self.layers = cmds.ls(type='renderLayer')

    #
    #   These init_* functions get run automatcially when the UI file is loaded.
    #   The function names must match the name of the UI element e.g. init_camera()
    #   will be run when the "camera" UI element is initialized.
    #

    def init_existing_project_name(self):
        project_response = ZYNC.get_project_list()
        if project_response["code"] != 0:
            cmds.error( project_response["response"] )
        self.projects = project_response["response"]
        project_found = False
        for project_name in self.projects:
            cmds.menuItem(parent='existing_project_name', label=project_name)
            if project_name == self.new_project_name:
                project_found = True
        if project_found:
            cmds.optionMenu('existing_project_name', e=True, v=self.new_project_name)

    def init_instance_type(self):
        non_default = []
        for inst_type in ZYNC.INSTANCE_TYPES:
            if inst_type == zync.DEFAULT_INSTANCE_TYPE:
                cmds.menuItem( parent='instance_type', label='%s (%s)' % ( inst_type, ZYNC.INSTANCE_TYPES[inst_type]["description"] ) )
            else:
                non_default.append( '%s (%s)' % ( inst_type, ZYNC.INSTANCE_TYPES[inst_type]["description"] ) ) 
        for label in non_default:
            cmds.menuItem( parent='instance_type', label=label )

    def init_renderer(self):
        #
        #   Try to detect the currently selected renderer, so it will be selected
        #   when the form appears. If we can't, fall back to the default set in zync.py.
        #
        try:
            current_renderer = cmds.getAttr("defaultRenderGlobals.currentRenderer")
            if current_renderer == "mentalRay":
                default_renderer_name = ZYNC.MAYA_RENDERERS["mr"]
                self.renderer = "mr"
            elif current_renderer == "mayaSoftware":
                default_renderer_name = ZYNC.MAYA_RENDERERS["sw"]
                self.renderer = "sw"
            elif current_renderer == "vray":
                default_renderer_name = ZYNC.MAYA_RENDERERS["vray"]
                self.renderer = zync.VRAY_RENDERER
            elif current_renderer == "arnold":
                if "arnold" in ZYNC.MAYA_RENDERERS:
                    default_renderer_name = ZYNC.MAYA_RENDERERS["arnold"]
                    self.renderer = "arnold"
                else:
                    raise Exception( "Arnold not supported for this site, using default ZYNC renderer." )
            else:
                default_renderer_name = ZYNC.MAYA_RENDERERS[zync.MAYA_DEFAULT_RENDERER]
                self.renderer = zync.MAYA_DEFAULT_RENDERER
        except:
            default_renderer_name = ZYNC.MAYA_RENDERERS[zync.MAYA_DEFAULT_RENDERER]
            self.renderer = zync.MAYA_DEFAULT_RENDERER

        #
        #   Add the list of renderers to UI element.
        #
        rend_found = False
        for item in ZYNC.MAYA_RENDERERS.values():
            cmds.menuItem(parent='renderer', label=item)
            if item == default_renderer_name:
                rend_found = True
        if rend_found:
            cmds.optionMenu('renderer', e=True, v=default_renderer_name)

    def init_camera(self):
        cam_parents = [cmds.listRelatives(x, ap=True)[-1] for x in cmds.ls(cameras=True)]
        for cam in cam_parents:
            if ( cmds.getAttr( cam + '.renderable') ) == True:
                cmds.menuItem( parent='camera', label=cam )

    def get_scene_info(self, renderer):
        """
        Returns scene info for the current scene.
        We use this to allow ZYNC to skip the file checks.

        """

        clear_layer_info()

        layers = [x for x in cmds.ls(type='renderLayer') \
                       if x != 'defaultRenderLayer' and not ':' in x]

        selected_layers = eval_ui('layers', 'textScrollList', ai=True, si=True)
        if selected_layers == None:
            selected_layers = []

        #
        #   Detect a list of referenced files. We must use ls() instead of file(q=True, r=True)
        #   because the latter will only detect references one level down, not nested references.
        #
        references = []
        unresolved_references = []
        for ref_node in cmds.ls(type='reference'):
            try:
                ref_file = cmds.referenceQuery(ref_node, filename=True)
                references.append(ref_file)

                un_ref_file = cmds.referenceQuery(ref_node, filename=True, unresolvedName=True)
                unresolved_references.append(un_ref_file)
            except:
                pass

        render_passes = {}
        multiple_folders = False
        element_separator = "."
        if renderer == "vray" and cmds.getAttr('vraySettings.imageFormatStr') != 'exr (multichannel)':
            pass_list = cmds.ls(type='VRayRenderElement')
            pass_list += cmds.ls(type='VRayRenderElementSet')
            if len(pass_list) > 0:
                multiple_folders = True if cmds.getAttr('vraySettings.relements_separateFolders') == 1 else False
                element_separator = cmds.getAttr('vraySettings.fnes')
                for layer in selected_layers:
                    render_passes[layer] = []
                    enabled_passes = get_layer_override(layer, renderer, 'render_passes')
                    for r_pass in pass_list:
                        if r_pass in enabled_passes:
                            vray_name = None
                            vray_explicit_name = None
                            vray_file_name = None
                            for attr_name in cmds.listAttr(r_pass):
                                if attr_name.startswith('vray_filename'):
                                    vray_file_name = cmds.getAttr('%s.%s' % (r_pass, attr_name))
                                elif attr_name.startswith('vray_name'):
                                    vray_name = cmds.getAttr('%s.%s' % (r_pass, attr_name))
                                elif attr_name.startswith('vray_explicit_name'):
                                    vray_explicit_name = cmds.getAttr('%s.%s' % (r_pass, attr_name))
                            if vray_file_name != None and vray_file_name != "":
                                final_name = vray_file_name
                            elif vray_explicit_name != None and vray_explicit_name != "":
                                final_name = vray_explicit_name
                            elif vray_name != None and vray_name != "":
                                final_name = vray_name
                            else:
                                continue
                            # special case for Material Select elements - these are named based on the material
                            # they are connected to.
                            if "vray_mtl_mtlselect" in cmds.listAttr( r_pass ):
                                connections = cmds.listConnections( "%s.vray_mtl_mtlselect" % ( r_pass, ) )
                                if connections:
                                    final_name += "_%s" % ( str(connections[0]), )
                            render_passes[layer].append(final_name)

        layer_prefixes = dict()
        for layer in selected_layers:
            layer_prefix = get_layer_override(layer, renderer, 'prefix')
            if layer_prefix != None:
                layer_prefixes[layer] = layer_prefix

        if renderer == "vray":
            extension = cmds.getAttr('vraySettings.imageFormatStr')
            if extension == None:
                extension = 'png'
            padding = int(cmds.getAttr('vraySettings.fileNamePadding'))
        elif renderer in ("sw", "mr"):
            extension = cmds.getAttr('defaultRenderGlobals.imfPluginKey')
            if not extension:
                extension = get_default_extension(renderer)
            padding = int(cmds.getAttr('defaultRenderGlobals.extensionPadding'))
        elif renderer == "arnold":
            extension = cmds.getAttr('defaultRenderGlobals.imfPluginKey')
            padding = int(cmds.getAttr('defaultRenderGlobals.extensionPadding'))
        global_prefix = get_layer_override('defaultRenderLayer', renderer, 'prefix')

        extension = extension[:3]

        file_prefix = [global_prefix]
        file_prefix.append(layer_prefixes)
        files = list(set(get_scene_files()))

        plugins = []
        plugin_list = cmds.pluginInfo( query=True, pluginsInUse=True )
        for i in range( 0, len(plugin_list), 2): 
            plugins.append( str(plugin_list[i]) )

        # detect MentalCore
        mentalcore_used = False
        try:
            mc_nodes = cmds.ls(type='core_globals')
            if len(mc_nodes) == 0:
                mentalcore_used = False
            else:
                mc_node = mc_nodes[0]
                if cmds.getAttr('%s.ec' % (mc_node,)) == True:
                    mentalcore_used = True
                else:
                    mentalcore_used = False
        except:
            mentalcore_used = False
        if mentalcore_used:
            plugins.append('mentalcore')

        # detect use of cache files
        if len(cmds.ls(type='cacheFile')) > 0:
            plugins.append('cache')

        version = get_maya_version() 

        vray_version = ''
        if renderer == 'vray':
            try:
                vray_version = str(cmds.pluginInfo('vrayformaya', query=True, version=True)) 
            except:
                raise Exception('Could not detect Vray version. This is required to render Vray jobs. Do you have the Vray plugin loaded?')

        arnold_version = ''
        if renderer == 'arnold':
            try:
                arnold_version = str(cmds.pluginInfo('mtoa', query=True, version=True)) 
            except:
                raise Exception('Could not detect Arnold version. This is required to render Arnold jobs. Do you have the Arnold plugin loaded?')

        scene_info = {'files': files,
                      'render_layers': self.layers,
                      'render_passes': render_passes,
                      'multiple_folders': multiple_folders,
                      'element_separator': element_separator,
                      'references': references,
                      'unresolved_references': unresolved_references,
                      'file_prefix': file_prefix,
                      'padding': padding,
                      'extension': extension,
                      'plugins': plugins,
                      'version': version,
                      'arnold_version': arnold_version,
                      'vray_version': vray_version}
        return scene_info

    @staticmethod
    def get_initial_value(window, name):
        """
        Returns the initial value for a given attribute
        """
        init_name = '_'.join(('init', name))
        if hasattr(window, init_name):
            return getattr(window, init_name)()
        elif hasattr(window, name):
            return getattr(window, name)
        else:
            return 'Undefined'

    @staticmethod
    def submit(window):
        """
        Submits to zync
        """
        params = window.get_render_params()

        scene_path = cmds.file(q=True, loc=True)
        # Comment out the line above and uncomment this section if you want to
        # save a unique copy of the scene file each time your submit a job.
        '''
        original_path = cmds.file(q=True, loc=True)
        original_modified = cmds.file(q=True, modified=True)
        scene_path = generate_scene_path()
        cmds.file( rename=scene_path )
        cmds.file( save=True, type='mayaAscii' )
        cmds.file( rename=original_path )
        cmds.file( modified=original_modified )
        '''

        if params["upload_only"] == 1:
            layers = None
        else:
            layers = eval_ui('layers', 'textScrollList', ai=True, si=True)
            if not layers:
                msg = 'Please select layer(s) to render.'
                raise MayaZyncException(msg)
            layers = ','.join(layers)

        username = eval_ui('username', text=True)
        password = eval_ui('password', text=True)
        if username=='' or password=='':
            msg = 'Please enter a ZYNC username and password.'
            raise MayaZyncException(msg)

        try:
            ZYNC.login( username=username, password=password )
        except zync.ZyncAuthenticationError as e:
            msg = 'ZYNC Username Authentication Failed'
            raise MayaZyncException(msg)

        scene_info = window.get_scene_info(params['renderer'])
        params['scene_info'] = scene_info

        try:
            ZYNC.submit_job("maya", scene_path, layers, params=params)
            cmds.confirmDialog(title='Success',
                               message='Job submitted to ZYNC.',
                               button='OK',
                               defaultButton='OK')
        except zync.ZyncPreflightError as e:
            cmds.confirmDialog(title='Preflight Check Failed',
                               message=str(e),
                               button='OK',
                               defaultButton='OK')
            

def submit_dialog():
    submit_window = SubmitWindow()
    submit_window.show()

