#!/usr/bin/python
# Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved

"""
Loads OneBlock analysis pipeline
Uses output from there to generate charts and graphs and dumps to current directory
Adds key metrics to database(not implemented yet)
"""

__version__ = filter(str.isdigit, "$Revision: 17459 $")

# First we need to bootstrap the analysis to start correctly from the command
# line or as the child process of a web server. We import a few things we
# need to make that happen before we import the modules needed for the actual
# analysis.
import os
import tempfile

# matplotlib/numpy compatibility
os.environ['HOME'] = tempfile.mkdtemp()
from matplotlib import use
use("Agg")

import datetime
import shutil
import socket
import subprocess
import sys
import time
from collections import deque
from urlparse import urlunsplit
import glob

# Import analysis-specific packages. We try to follow the from A import B
# convention when B is a module in package A, or import A when
# A is a module.
#from ion.analysis import cafie,sigproc
#from ion.fileformats import sff
#from ion.reports import tfGraphs, parseTFstats
from ion.reports import blast_to_ionogram, plotKey, \
    parseBeadfind, parseProcessParams, beadDensityPlot, \
    libGraphs, beadHistogram, plotRawRegions, trimmedReadLenHisto

from ion.utils import TFPipeline

from ion.reports.plotters import *
from ion.utils.aggregate_alignment import *
from ion.utils.align_full_chip import *

sys.path.append('/opt/ion/')

import math
from scipy import cluster, signal, linalg
import traceback
import json

import dateutil.parser

import zipfile
try:
    compression = zipfile.ZIP_DEFLATED
except:
    compression = zipfile.ZIP_STORED

modes = { zipfile.ZIP_DEFLATED: 'deflated',
          zipfile.ZIP_STORED:   'stored',
          }

#####################################################################
#
# Analysis implementation details
#
#####################################################################

def printtime(message, *args):
    if args:
        message = message % args
    print "[ " + time.strftime('%X') + " ] " + message

def write_version():
    a = subprocess.Popen('/opt/ion/iondb/bin/lversionChk.sh --ion', shell=True, stdout=subprocess.PIPE)
    ret = a.stdout.readlines()
    f = open('version.txt','w')
    for i in ret:
        f.write(i)
    f.close()

def initreports():
    """Performs initialization for both report writing and background
    report generation."""
    printtime("INIT REPORTS")
    #
    # Begin report writing
    #
    os.umask(0002)
    TMPL_DIR = '/usr/lib/python2.6/dist-packages/ion/web/db/writers'
    shutil.copy("%s/report_layout.json" % TMPL_DIR, "report_layout.json")
    #TODO, temporary commented out
    #shutil.copy("%s/parsefiles.php" % TMPL_DIR, "parsefiles.php")
    shutil.copy("%s/log.html" % TMPL_DIR, 'log.html')
    shutil.copy("%s/alignment_summary.html" % TMPL_DIR, os.path.join(ALIGNMENT_RESULTS,"alignment_summary.html"))
    #shutil.copy("%s/format_whole.php" % TMPL_DIR, "Default_Report.php")
    shutil.copy("%s/csa.php" % TMPL_DIR, "csa.php")
    #shutil.copy("%s/ziparc.php" % TMPL_DIR, "ziparc.php")
    #shutil.copy("%s/format_whole_debug.php" % TMPL_DIR, "Detailed_Report.php")
    # create analysis progress bar file
    f = open('progress.txt','w')
    f.write('wellfinding = yellow\n')
    f.write('signalprocessing = grey\n')
    f.write('basecalling = grey\n')
    f.write('sffread = grey\n')
    f.write('alignment = grey')
    f.close()


def runBlock(env):
    STATUS = None
    basefolder = 'plugin_out'
    if not os.path.isdir(basefolder):
        os.umask(0000)   #grant write permission to plugin user
        os.mkdir(basefolder)
        os.umask(0002)
    pathprefix = env["prefix"]
    libsff_filename = "rawlib.sff"
    tfsff_filename = "rawtf.sff"
    fastq_filename = "raw.fastq"
    bctrimmed_libsff_filename = "bctrimmed_rawlib.sff"

    fastq_path = os.path.join(BASECALLER_RESULTS, fastq_filename)
    libsff_path = os.path.join(BASECALLER_RESULTS, libsff_filename)
    tfsff_path = os.path.join(BASECALLER_RESULTS, tfsff_filename)
    bctrimmed_libsff_path =  os.path.join(BASECALLER_RESULTS,bctrimmed_libsff_filename)
    tfmapperstats_path = os.path.join(BASECALLER_RESULTS,"TFMapper.stats")

    libKeyArg = "--libraryKey=%s" % env["libraryKey"]

    write_version()

    #-------------------------------------------------------------
    # Single Block data processing
    #-------------------------------------------------------------
    if runFromRaw:
        printtime("RUNNING SINGLE BLOCK ANALYSIS")
        command = "%s >> ReportLog.html 2>&1" % (env['analysisArgs'])
        printtime("Analysis command: " + command)
        sys.stdout.flush()
        sys.stderr.flush()
        status = subprocess.call(command,shell=True)
        #status = 2
        STATUS = None
        if int(status) == 2:
            STATUS = 'Checksum Error'
        elif int(status) == 3:
            STATUS = 'No Live Beads'
        elif int(status) != 0:
            STATUS = 'ERROR'

        if STATUS != None:
            printtime("Analysis finished with status '%s'" % STATUS)
            #TODO - maybe create file
            # uploadMetrics.updateStatus(STATUS)

        #TODO
        '''
        csp = os.path.join(env['pathToRaw'],'checksum_status.txt')
        if not os.path.exists(csp) and not env['skipchecksum'] and STATUS==None:
            try:
                os.umask(0002)
                f = open(csp, 'w')
                f.write(str(status))
                f.close()
            except:
                traceback.print_exc()
        '''
        printtime("Finished single block analysis")
    else:
        printtime('Skipping single block analysis')

    if runFromWells:
        tfKey = "ATCG"
        libKey = env['libraryKey']
        floworder = env['flowOrder']
        printtime("Using flow order: %s" % floworder)
        printtime("Using library key: %s" % libKey)

        if "block_" in mycwd:

            # Fix SFFTrim
            basecallerjson = os.path.join(BASECALLER_RESULTS, 'BaseCaller.json')
            r = subprocess.call(["ln", "-s", basecallerjson])
            if r:
                printtime("couldn't create symbolic link")

            # Fix SFFMerge
            r = subprocess.call(["ln", "-s", os.path.join('..', SIGPROC_RESULTS, 'processParameters.txt'), os.path.join(BASECALLER_RESULTS, 'processParameters.txt')])
            if r:
                printtime("couldn't create symbolic link")


        sys.stdout.flush()
        sys.stderr.flush()

        if not os.path.exists(libsff_path):
            printtime("ERROR: %s does not exist" % libsff_path)
            open('badblock.txt', 'w').close() 

        ##################################################
        # Unfiltered SFF
        ##################################################

        unfiltered_dir = "unfiltered"
        if os.path.exists(unfiltered_dir):

            top_dir = os.getcwd()

            #change to the unfiltered dir
            os.chdir(os.path.join(top_dir,unfiltered_dir))

            #grab the first file named untrimmed.sff
            try:
                untrimmed_sff = glob.glob("*.untrimmed.sff")[0]
            except IndexError:
                printtime("Error, unable to find the untrimmed sff file")

            #rename untrimmed to trimmed
            trimmed_sff = untrimmed_sff.replace("untrimmed.sff","trimmed.sff")

            # 3' adapter details
            qual_cutoff = env['reverse_primer_dict']['qual_cutoff']
            qual_window = env['reverse_primer_dict']['qual_window']
            adapter_cutoff = env['reverse_primer_dict']['adapter_cutoff']
            adapter = env['reverse_primer_dict']['sequence']

            # If flow order is missing, assume classic flow order:
            if floworder == "0":
                floworder = "TACG"
                printtime("warning: floworder redefine required.  set to TACG")

            printtime("Unfiltered SFFTrim")
            try:
                com = "SFFTrim"
                com += " --in-sff %s --out-sff %s" % (untrimmed_sff,trimmed_sff)
                com += " --flow-order %s" % (floworder)
                com += " --key %s" % (libKey)
                com += " --qual-cutoff %s" % (qual_cutoff)
                com += " --qual-window-size %s" % (qual_window)
                com += " --adapter-cutoff %s" % (adapter_cutoff)
                com += " --adapter %s" % (adapter)
                com += " --min-read-len 5"
                printtime("DEBUG: Calling '%s'" % com)
                ret = subprocess.call(com,shell=True)
                if int(ret)!=0 and STATUS==None:
                    STATUS='ERROR'
            except:
                printtime('Failed Unfiltered SFFTrim')

            sffs = glob.glob("*.sff")
            for sff in sffs:
                try:
                    com = "SFFRead"
                    com += " -q %s" % sff.replace(".sff",".fastq")
                    com += " %s" % sff
                    printtime("DEBUG: Calling '%s'" % com)
                    ret = subprocess.call(com,shell=True)
                    if int(ret)!=0 and STATUS==None:
                        STATUS='ERROR'
                except:
                    printtime('Failed to convert SFF' + str(sff) + ' to fastq')

            #trim status
            for status in ["untrimmed","trimmed"]:
                os.chdir(os.path.join(top_dir,unfiltered_dir))
                if not os.path.exists(status):
                    os.makedirs(status)
                os.chdir(os.path.join(top_dir,unfiltered_dir,status))

                try:
                    printtime("Trim Status",)
                    align_full_chip_core("../*." + status + ".sff", libKey, tfKey, floworder, fastq_path, env['align_full'], -1, False, False, True, DIR_BC_FILES, env, ALIGNMENT_RESULTS)
                except OSError:
                    printtime('Trim Status Alignment Failed to start')
                    alignError = open("alignment.error", "w")
                    alignError.write(str(traceback.format_exc()))
                    alignError.close()
                    traceback.print_exc()

            os.chdir(top_dir)
        else:
            printtime("Directory unfiltered does not exist")

        sys.stdout.flush()
        sys.stderr.flush()

        ##################################################
        # Trim the SFF file if it has been requested     #
        ##################################################

        #only trim if SFF is false
        if not env['sfftrim']:
            printtime("Attempting to trim the SFF file")

            if not os.path.exists(libsff_path):
                printtime("ERROR: %s does not exist" % libsff_path)

            (head,tail) = os.path.split(libsff_path)
            libsff_trimmed_path = os.path.join(head,tail[:4] + "trimmed.sff")

            #we will always need the input and output files
            trimArgs = "--in-sff %s --out-sff %s" % (libsff_path,libsff_trimmed_path)

            qual_cutoff = env['reverse_primer_dict']['qual_cutoff']
            qual_window = env['reverse_primer_dict']['qual_window']
            adapter_cutoff = env['reverse_primer_dict']['adapter_cutoff']
            adapter = env['reverse_primer_dict']['sequence']

            if not env['sfftrim_args']:
                printtime("no args found, using default args")
                trimArgs += " --flow-order %s --key %s" % (floworder, libKey)
                trimArgs += " --qual-cutoff %d --qual-window-size %d --adapter-cutoff %d --adapter %s" % (qual_cutoff,qual_window,adapter_cutoff,adapter)
                trimArgs += " --min-read-len 5 "
            else:
                printtime("using non default args" , env['sfftrim_args'])
                trimArgs += " " + env['sfftrim_args']

            try:
                com = "SFFTrim %s " % (trimArgs)
                printtime("DEBUG: call '%s':" % com)
                ret = subprocess.call(com,shell=True)
                if int(ret)!=0 and STATUS==None:
                    STATUS='ERROR'
            except:
                printtime('Failed SFFTrim')

            #if the trim did not fail then move the untrimmed file to untrimmed.expname.sff
            #and move trimmed to expname.sff to ensure backwards compatability

# don't rename, result will be useless for --fromsff runs

#            if os.path.exists(libsff_path):
#                try:
#                    os.rename(libsff_path, "untrimmed." + libsff_path) #todo
#                except:
#                    printtime("ERROR: renaming %s" % libsff_path)

#            if os.path.exists(libsff_trimmed_path):
#                try:
#                    os.rename(libsff_trimmed_path, libsff_path)
#                except:
#                    printtime("ERROR: renaming %s" % libsff_trimmed_path)
        else:
            printtime("Not attempting to trim the SFF")


        #####################################################
        # Barcode trim SFF if barcodes have been specified  #
        # Creates one fastq per barcode, plus unknown reads #
        #####################################################

        if env['barcodeId'] is not '':
            try:
                com = "barcodeSplit"
                com += " -s"
                com += " -i %s" % libsff_path
                com += " -b barcodeList.txt"
                com += " -c barcodeMask.bin"
                com += " -f %s" % floworder

                printtime("DEBUG: Calling '%s'" % com)
                ret = subprocess.call(com,shell=True)
                if int(ret) != 0 and STATUS==None:
                    STATUS='ERROR'
                else:
                    # Rename bc trimmed sff
                    if os.path.exists(bctrimmed_libsff_path):
                        os.rename(bctrimmed_libsff_path, libsff_path)
            except:
                printtime("Failed barcodeSplit")


        ##################################################
        # Once we have the new SFF, run SFFSummary
        # to get the predicted quality scores
        ##################################################

        try:
            com = "SFFSummary"
            com += " -o %s" % os.path.join(BASECALLER_RESULTS, 'quality.summary')
            com += " --sff-file %s" % libsff_path
            com += " --read-length 50,100,150"
            com += " --min-length 0,0,0"
            com += " --qual 0,17,20"
            com += " -d %s" % os.path.join(BASECALLER_RESULTS, 'readLen.txt')

            printtime("DEBUG: Calling '%s'" % com)
            ret = subprocess.call(com,shell=True)
            if int(ret)!=0 and STATUS==None:
                STATUS='ERROR'
        except:
            printtime('Failed SFFSummary')

        ##################################################
        #make keypass.fastq file -c(cut key) -k(key flows)#
        ##################################################
        # create analysis progress bar file
        f = open('progress.txt','w')
        f.write('wellfinding = green\n')
        f.write('signalprocessing = green\n')
        f.write('basecalling = green\n')
        f.write('sffread = yellow\n')
        f.write('alignment = grey')
        f.close()

        try:
            com = "SFFRead"
            com += " -q %s" % fastq_path
            com += " %s" % libsff_path
            com += " > %s" % os.path.join(BASECALLER_RESULTS, 'keypass.summary')

            printtime("DEBUG: Calling '%s'" % com)
            ret = subprocess.call(com,shell=True)
            if int(ret)!=0 and STATUS==None:
                STATUS='ERROR'
        except:
            printtime('Failed SFFRead')


        ##################################################
        #generate TF Metrics                             #
        ##################################################
        
        printtime("Calling TFPipeline.processBlock")
        TFPipeline.processBlock(tfsff_filename, BASECALLER_RESULTS, SIGPROC_RESULTS, tfKey, floworder)
        printtime("Completed TFPipeline.processBlock")

        #printtime("Calling TFMapper")
        #try:
        #    com = "TFMapper"
        #    com += " --logfile TFMapper.log"
        #    com += " --output-dir=%s" % (BASECALLER_RESULTS)
        #    com += " --wells-dir=%s" % (SIGPROC_RESULTS)
        #    com += " --sff-dir=%s" % (BASECALLER_RESULTS)
        #    com += " --tfkey=%s" % (tfKey)
        #    com += " %s" % (tfsff_filename)
        #    com += " ./"
        #    com += " > %s" % (tfmapperstats_path)
        #    printtime("DEBUG: Calling '%s'" % com)
        #    ret = subprocess.call(com,shell=True)
        #    if int(ret)!=0 and STATUS==None:
        #        STATUS='ERROR'
        #except:
        #    printtime("ERROR: TFMapper failed")

        ########################################################
        #generate the TF Metrics including plots               #
        ########################################################
        #printtime("generate the TF Metrics including plots")

        #if os.path.exists(tfmapperstats_path):
        #    try:
        #        # Q17 TF Read Length Plot
        #        tfMetrics = parseTFstats.generateMetricsData(tfmapperstats_path)
        #        tfGraphs.Q17(tfMetrics)
        #        tfGraphs.genCafieIonograms(tfMetrics,floworder)
        #    except Exception:
        #        printtime("ERROR: Metrics Gen Failed")
        #        traceback.print_exc()
        #else:
        #    printtime("ERROR: %s doesn't exist" % tfmapperstats_path)

        ########################################################
        #Generate Raw Data Traces for lib and TF keys          #
        ########################################################
        printtime("Generate Raw Data Traces for lib and TF keys(iontrace_Test_Fragment.png, iontrace_Library.png)")

        tfRawPath = 'avgNukeTrace_%s.txt' % tfKey
        libRawPath = 'avgNukeTrace_%s.txt' % libKey
        peakOut = 'raw_peak_signal'

        if os.path.exists(tfRawPath):
            try:
                kp = plotKey.KeyPlot(tfKey, floworder, 'Test Fragment')
                kp.parse(tfRawPath)
                kp.dump_max(peakOut)
                kp.plot()
            except:
                printtime("TF key graph didn't render")
                traceback.print_exc()

        if os.path.exists(libRawPath):
            try:
                kp = plotKey.KeyPlot(libKey, floworder, 'Library')
                kp.parse(libRawPath)
                kp.dump_max(peakOut)
                kp.plot()
            except:
                printtime("Lib key graph didn't render")
                traceback.print_exc()

        ########################################################
        #Make Bead Density Plots                               #
        ########################################################
        printtime("Make Bead Density Plots")
        bfmaskPath = os.path.join(SIGPROC_RESULTS,"bfmask.bin")
        maskpath = os.path.join(SIGPROC_RESULTS,"MaskBead.mask")

        if os.path.isfile(bfmaskPath):
            com = "BeadmaskParse"
            com += " -m MaskBead"
            com += " %s" % bfmaskPath
            ret = subprocess.call(com,shell=True)
            if int(ret)!=0 and STATUS==None:
                STATUS='ERROR'
            #TODO
            try:
                shutil.move('MaskBead.mask', maskpath)
            except:
                printtime("ERROR: MaskBead.mask already moved")
        else:
            printtime("Warning: no bfmask.bin file exists.")

        if os.path.exists(maskpath):
            try:
                # Makes Bead_density_contour.png
                beadDensityPlot.genHeatmap(maskpath, BASECALLER_RESULTS)
    #            os.remove(maskpath)
            except:
                traceback.print_exc()
        else:
            printtime("Warning: no MaskBead.mask file exists.")

        sys.stdout.flush()
        sys.stderr.flush()

        ########################################################
        # Make per region key incorporation traces             #
        ########################################################
        printtime("Make per region key incorporation traces")
        perRegionTF = "averagedKeyTraces_TF.txt"
        perRegionLib = "averagedKeyTraces_Lib.txt"
        if os.path.exists(perRegionTF):
            pr = plotRawRegions.PerRegionKey(tfKey, floworder,'TFTracePerRegion.png')
            pr.parse(perRegionTF)
            pr.plot()

        if os.path.exists(perRegionLib):
            pr = plotRawRegions.PerRegionKey(libKey, floworder,'LibTracePerRegion.png')
            pr.parse(perRegionLib)
            pr.plot()


        sys.stdout.flush()
        sys.stderr.flush()
    else:
        printtime('Skipping SFF Processing')

    if runFromSFF:
        ########################################################
        #Attempt to align                                      #
        ########################################################
        printtime("Attempt to align")

        # create analysis progress bar file
        f = open('progress.txt','w')
        f.write('wellfinding = green\n')
        f.write('signalprocessing = green\n')
        f.write('basecalling = green\n')
        f.write('sffread = green\n')
        f.write('alignment = yellow')
        f.close()

        try:
            align_full_chip(libsff_path, libKey, tfKey, floworder, fastq_path, env['align_full'], DIR_BC_FILES, env, ALIGNMENT_RESULTS)
        except Exception:
            printtime("ERROR: Alignment Failed")
            traceback.print_exc()

        printtime("make the read length histogram")
        try:
            filepath_readLenHistogram = os.path.join(ALIGNMENT_RESULTS,'readLenHisto.png')
            trimmedReadLenHisto.trimmedReadLenHisto('readLen.txt',filepath_readLenHistogram)
        except:
            printtime("Failed to create %s" % filepath_readLenHistogram)

        ########################################################
        #ParseFiles                                            #
        ########################################################
        printtime('ParseFiles')

        # create analysis progress bar file
        f = open('progress.txt','w')
        f.write('wellfinding = green\n')
        f.write('signalprocessing = green\n')
        f.write('basecalling = green\n')
        f.write('sffread = green\n')
        f.write('alignment = green')
        f.close()

    else:
        printtime('Skipping TMAP Processing')

if __name__=="__main__":
    ########################################################
    # Print nice header information                        #
    ########################################################
    printtime("BlockTLScript.py: " + os.getcwd())
    sys.stdout.flush()
    sys.stderr.flush()

    python_data = [sys.executable, sys.version, sys.platform, socket.gethostname(),
               str(os.getpid()), os.getcwd(),
               os.environ.get("JOB_ID", '[Stand-alone]'),
               os.environ.get("JOB_NAME", '[Stand-alone]'),
               datetime.datetime.now().strftime("%H:%M:%S %b/%d/%Y")
               ]
    python_data_labels = ["Python Executable", "Python Version", "Platform",
                      "Hostname", "PID", "Working Directory", "SGE Job ID",
                      "SGE Job Name", "Analysis Start Time"]
    _MARGINS = 4
    _TABSIZE = 4
    _max_sum = max(map(lambda (a,b): len(a) + len(b), zip(python_data,python_data_labels)))
    _info_width = _max_sum + _MARGINS + _TABSIZE
    print('*'*_info_width)
    for d,l in zip(python_data, python_data_labels):
        spacer = ' '*(_max_sum - (len(l) + len(d)) + _TABSIZE)
        print('* %s%s%s *' % (str(l),spacer,str(d).replace('\n',' ')))
    print('*'*_info_width)

    sys.stdout.flush()
    sys.stderr.flush()

    # Sub directory to contain fastq files for barcode enabled runs
    DIR_BC_FILES = 'bc_files'

    #####################################################################
    # Load the analysis parameters and metadata from a json file passed in on the
    # command line with --params=<json file name>
    # we expect this loop to iterate only once. This is more elegant than
    # trying to index into ARGUMENTS.
    #####################################################################
    EXTERNAL_PARAMS = {}
    env = {}
    if len(sys.argv) > 1:
        env["params_file"] = sys.argv[1]
    else:
        env["params_file"] = 'ion_params_00.json'
    afile = open(env["params_file"], 'r')
    EXTERNAL_PARAMS = json.loads(afile.read())
    afile.close()
    for k,v in EXTERNAL_PARAMS.iteritems():
        if isinstance(v, unicode):
            EXTERNAL_PARAMS[k] = str(v)

    # Where the raw data lives (generally some path on the network)
    pathprefix = str(EXTERNAL_PARAMS['pathToData'])
    env['prefix'] = pathprefix
    # this is the library name for the run taken from the library field in the database
    env["libraryName"] = EXTERNAL_PARAMS.get("libraryName", "none")
    if env["libraryName"] == "":
        env["libraryName"] = "none"
    #todo, workaround for thumbnails, to test tmap
    if env["libraryName"] == "none":
        env["libraryName"] = "e_coli_dh10b"
    dtnow = datetime.datetime.now()
    # the time at which the analysis was started, mostly for debugging purposes
    env["report_start_time"] = dtnow.strftime("%c")
    # get command line args
    env['analysisArgs'] = EXTERNAL_PARAMS.get("analysisArgs")
    # name of current analysis
    env['resultsName'] = EXTERNAL_PARAMS.get("resultsName")
    # name of current experiment
    env['expName'] = EXTERNAL_PARAMS.get("expName")
    #library key input
    env['libraryKey'] = EXTERNAL_PARAMS.get("libraryKey")
    #path to the raw data
    env['pathToRaw'] = EXTERNAL_PARAMS.get("pathToData")
    #plugins
    env['plugins'] = EXTERNAL_PARAMS.get("plugins")
    # skipChecksum?
    env['skipchecksum'] = EXTERNAL_PARAMS.get('skipchecksum',False)
    # Do Full Align?
    env['align_full'] = EXTERNAL_PARAMS.get('align_full')
    # Check to see if a SFFTrim should be done
    env['sfftrim'] = EXTERNAL_PARAMS.get('sfftrim')
    # Get SFFTrim args
    env['sfftrim_args'] = EXTERNAL_PARAMS.get('sfftrim_args')
    env['flowOrder'] = EXTERNAL_PARAMS.get('flowOrder').strip()
    env['project'] = EXTERNAL_PARAMS.get('project')
    env['sample'] = EXTERNAL_PARAMS.get('sample')
    env['chipType'] = EXTERNAL_PARAMS.get('chiptype')
    env['barcodeId'] = EXTERNAL_PARAMS.get('barcodeId','')
    env['reverse_primer_dict'] = EXTERNAL_PARAMS.get('reverse_primer_dict')
    env['rawdatastyle'] = EXTERNAL_PARAMS.get('rawdatastyle', 'single')
    env['blockArgs'] = EXTERNAL_PARAMS.get('blockArgs')

    #extra JSON
    env['extra'] = EXTERNAL_PARAMS.get('extra', '{}')
    # Aligner options
    env['aligner_opts_extra'] = EXTERNAL_PARAMS.get('aligner_opts_extra', '{}')

    master_node = "localhost"

    env['master_node'] = master_node
    env['net_location'] = EXTERNAL_PARAMS.get('net_location','http://' + master_node )
    env['url_path'] = EXTERNAL_PARAMS.get('url_path','output/Home')

    # define entry point
    if env['blockArgs'] == "fromRaw":
        runFromRaw = True
        runFromWells = True
        runFromSFF = True
    elif env['blockArgs'] == "fromWells":
        runFromRaw = False
        runFromWells = True
        runFromSFF = True
    elif env['blockArgs'] == "fromSFF":
        runFromRaw = False
        runFromWells = False
        runFromSFF = True
    else:
        runFromRaw = True
        runFromWells = True
        runFromSFF = True

    # assemble the URL path for this analysis result
    # http://<servername>/<output dir>/<Location name>/<analysis dir>
    url_scheme = 'http'
    url_location = env['net_location'].replace('http://','')
    url_path = os.path.join(env['url_path'],os.path.basename(os.getcwd()))
    url_root = urlunsplit([url_scheme,url_location,url_path,"",""])
    printtime("URL string %s" % url_root)

    #get the experiment json data
    env['exp_json'] = EXTERNAL_PARAMS.get('exp_json')
    #get the name of the site
    env['site_name'] = EXTERNAL_PARAMS.get('site_name')

    #############################################################
    # Code to start one block analysis                           #
    #############################################################

    mycwd=os.path.basename(os.getcwd())

    SIGPROC_RESULTS = "sigproc_results"
    BASECALLER_RESULTS = "basecaller_results"
    ALIGNMENT_RESULTS = "alignment_results"
    SIGPROC_RESULTS = "./"
    BASECALLER_RESULTS = "./"
    ALIGNMENT_RESULTS = "./"

    try:
        os.mkdir(SIGPROC_RESULTS)
    except:
        traceback.print_exc()

    try:
        os.mkdir(BASECALLER_RESULTS)
    except:
        traceback.print_exc()

    try:
        os.mkdir(ALIGNMENT_RESULTS)
    except:
        traceback.print_exc()

    # create symbolic links for merge process
    if "block_" in mycwd:

        _SIGPROC_RESULTS = os.path.join('..', SIGPROC_RESULTS, mycwd)
        _BASECALLER_RESULTS = os.path.join('..', BASECALLER_RESULTS, mycwd)
        _ALIGNMENT_RESULTS = os.path.join('..', ALIGNMENT_RESULTS, mycwd)

        r = subprocess.call(["ln", "-s", os.path.join('..', mycwd, SIGPROC_RESULTS), _SIGPROC_RESULTS])
        r = subprocess.call(["ln", "-s", os.path.join('..', mycwd, BASECALLER_RESULTS), _BASECALLER_RESULTS])
        r = subprocess.call(["ln", "-s", os.path.join('..', mycwd, ALIGNMENT_RESULTS), _ALIGNMENT_RESULTS])

    os.umask(0002)
    initreports()
    logout = open("ReportLog.html", "w")
    logout.close()

    sys.stdout.flush()
    sys.stderr.flush()

    runBlock(env)
    printtime("Run Complete")
    sys.exit(0)
