#!/usr/bin/env python
# Copyright (C) 2011 Ion Torrent Systems, Inc. All Rights Reserved
import os
import traceback
import json

DEBUG = False

def get_runinfo(env,plugin,primary_key,basefolder,plugin_out,url_root):
    # Compat shim for new 2.2 values
    if 'report_root_dir' not in env:
        env['report_root_dir']=env['analysis_dir']
    if 'analysis_dir' not in env:
        env['analysis_dir']=env['report_root_dir']

    sigproc_dir = os.path.join(env['report_root_dir'],env['SIGPROC_RESULTS'])
    basecaller_dir = os.path.join(env['report_root_dir'],env['BASECALLER_RESULTS'])
    alignment_dir = os.path.join(env['report_root_dir'],env['ALIGNMENT_RESULTS'])
    
    # Fallback to 2.2 single folder layout
    if not os.path.exists(sigproc_dir):
        sigproc_dir = env['report_root_dir']
    if not os.path.exists(basecaller_dir):
        basecaller_dir = env['report_root_dir']
    if not os.path.exists(alignment_dir):
        alignment_dir = env['report_root_dir']

    # replace with Proton block folders for plugins running at blocklevel
    raw_data_dir = env['pathToRaw']
    if 'runlevel' in env.keys() and env['runlevel'] == 'block':
        if 'blockId' in env.keys() and env['blockId']:
            sigproc_dir = os.path.join(sigproc_dir, 'block_'+env['blockId'])
            basecaller_dir = os.path.join(basecaller_dir, 'block_'+env['blockId'])
            alignment_dir = os.path.join(alignment_dir, 'block_'+env['blockId'])
            raw_data_dir = os.path.join(env['pathToRaw'], 'block_'+env['blockId'])

    dict={
            "raw_data_dir":raw_data_dir,
            "report_root_dir":env['report_root_dir'],
            "analysis_dir":env['analysis_dir'],
            "sigproc_dir":sigproc_dir,
            "basecaller_dir":basecaller_dir,
            "alignment_dir":alignment_dir,
            "library_key":env['libraryKey'],
            "testfrag_key":env['tfKey'],
            "results_dir":os.path.join(env['report_root_dir'],basefolder,plugin_out),
            "net_location":env['net_location'],
            "url_root":url_root,
            "api_url": 'http://%s/rundb/api' % env['master_node'],
            "plugin_dir":plugin['path'], # compat
            "plugin_name":plugin['name'], # compat
            "plugin": plugin, # name,version,id,pluginresult_id,path
            "pk":primary_key,
            "tmap_version":env['tmap_version'],
            "chipType": env.get('chipType',''),
            "barcodeId": env.get('barcodeId','')
        }
    return dict
    
def get_runplugin(env):
    d = {
        "run_type": env.get('report_type','unknown'),
        "runlevel": env.get('runlevel', ''),
        "blockId":  env.get('blockId', '') if env.get('runlevel', 'none') == 'block' else '',
        "block_dirs": env.get('block_dirs', ["."]),
        "numBlocks": len(env.get('block_dirs', ["."]))
    }             
    return d  
      

def get_pluginconfig(plugin):    
    d = plugin.get('pluginconfig',{})
    if d:
      return json.loads(d)
    else:    
      # 2.2 Compat
      pluginjson = os.path.join(plugin['path'],'pluginconfig.json')
      if not os.path.exists( pluginjson ):
          return {}
      with open(pluginjson, 'r') as f:
         d = json.load(f)
      return d

def get_globalconfig():
    dict={
        "debug":0,
        "MEM_MAX":"15G"
    }
    return dict

def make_plugin_json(env,plugin,primary_key,basefolder,url_root):
    json_obj={
        "runinfo":get_runinfo(env,plugin,primary_key,basefolder,plugin['name']+"_out",url_root),
        "runplugin":get_runplugin(env),
        "pluginconfig":get_pluginconfig(plugin),
        "globalconfig":get_globalconfig(),
        "plan":{},
    }
    if "plan" in env:
        json_obj["plan"] = env["plan"]
        if plugin.get("userInput","") and "Workflow" in plugin["userInput"][0].keys():
            json_obj["plan"]["irworkflow"] = plugin["userInput"][0]["Workflow"]
        
    if DEBUG:
        print json.dumps(json_obj,indent=2)
    return json_obj

if __name__ == '__main__':
    '''Library of functions to handle json structures used in Plugin launching'''
    print 'python/ion/utils/plugin_json.py'
    sigproc_results = "sigproc_results"
    basecaller_results = "basecaller_results"
    alignment_results = "./"#"alignment_results"
    env={}
    env['pathToRaw']='/results/PGM_test/cropped_CB1-42'
    env['libraryKey']='TCAG'
    env['report_root_dir']=os.getcwd()
    env['analysis_dir']=os.getcwd()
    env['sigproc_dir']=os.path.join(env['report_root_dir'],sigproc_results)
    env['basecaller_dir']=os.path.join(env['report_root_dir'],basecaller_results)
    env['alignment_dir']=os.path.join(env['report_root_dir'],alignment_results)
    env['testfrag_key']='ATCG'

    #todo
    env['net_location']='http://localhost/' # Constructing internal URLS for plugin communication. Absolute hostname, resolvable by compute
    url_root = "/" # Externally Resolvable URL. Preferably without hardcoded hostnames

    plugin={'name': 'test_plugin',
            'path': '/results/plugins/test_plugin',
            'version': '0.1-pre',
           }
    pk=7
    jsonobj=make_plugin_json(env,plugin,pk,'plugin_out',url_root)
