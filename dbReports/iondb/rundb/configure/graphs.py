#!/usr/bin/env python
# Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved
import datetime
import httplib
import os 
from os import path
import random
import re
import shutil
import socket
import StringIO
import subprocess
import sys
import threading
import time
from urlparse import urlparse
import urllib
import xmlrpclib
import math
import numpy
import Image
import json

from django import http, shortcuts, template
from django.conf import settings
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.core import urlresolvers
from django import http

os.environ['MPLCONFIGDIR'] = '/tmp'
import matplotlib
import matplotlib.cbook as cbook
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter
import matplotlib.pylab
import matplotlib.image
from pylab import *

from iondb.anaserve import client
from iondb.rundb import forms
from iondb.rundb import models
from iondb.utils import tables
from iondb.backup import devices
from iondb.rundb import views
from twisted.internet import reactor
from twisted.web import xmlrpc,server

def disk_attributes(path):
    '''returns disk attributes'''
    resDir = os.statvfs(path)
    totalSpace = resDir.f_blocks
    freeSpace = resDir.f_bavail
    blocksize = resDir.f_bsize
    return (path,totalSpace,freeSpace,blocksize)
def get_folder_size(folder):
    ''' Walks a folder, and adds up the size of all
    files contained inside'''
    dir_size = 0
    for (path, dirs, files) in os.walk(folder):
        for file in files:
            filename = os.path.join(folder, file)
            if os.path.exists(filename):
                dir_size += os.path.getsize(filename)
    return dir_size
def get_total_freespace(fileserver):
    '''returns the sum of the free space for all file
    servers stored in the database'''
    ret  = 0
    fs = models.FileServer.objects.all()
    if fileserver is not None:
        fs = fs.filter(pk=fileserver.pk)
    for f in fs:
        try:
            path,totalSpace,freeSpace,blocksize = disk_attributes(f.filesPrefix)
            ret += (freeSpace*blocksize)
        except OSError:
            continue

    return float(ret)

def archive_graph(request):
    ''' Generates a pie graph to display the number of runs
    that belong to each storage option.'''
    # create figure
    figwidth = 3   # inches
    figheight = 3   # inches
    matplotlib.rcParams['font.size'] = 10.0
    matplotlib.rcParams['axes.titlesize'] = 14.0
    matplotlib.rcParams['xtick.labelsize'] = 10.0
    matplotlib.rcParams['legend.fontsize'] = 10.0
    explode=(0.05, 0.0)
    #colors=('b','g')
    fig = Figure(figsize=(figwidth,figheight))
    ax = fig.add_subplot(1,1,1)
    runs = models.Experiment.objects.all()
    # Get only Experiments that are still on fileserver: not deleted or archived.
    runs = runs.exclude(expName__in = models.Backup.objects.all().values('backupName'))
    num_arch = len(runs.filter(storage_options='A'))
    num_del = len(runs.filter(storage_options='D'))
    num_keep = len(runs.filter(storage_options='KI'))
    total = sum([num_arch,num_del,num_keep])
    frac_arch = (float(num_arch)/float(total))*100
    frac_del = (float(num_del)/float(total))*100
    frac_keep = (float(num_keep)/float(total))*100
    frac = [frac_arch,frac_del,frac_keep]
    ax.pie(frac,
           autopct='%1.f%%',
           labels=['Archive\n%s' % num_arch,'Delete\n%s' % num_del,'Keep\n%s' % num_keep]) 
    ax.set_title('Storage Option Breakdown')
    canvas = FigureCanvas(fig)
    response = http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response

def archive_graph_bar(request):
    ''' Generates a pie graph to display the number of runs
    that belong to each storage option.'''
    # create figure
    figwidth = 9   # inches
    figheight = 1.5   # inches
    matplotlib.rcParams['font.size'] = 10.0
    matplotlib.rcParams['axes.titlesize'] = 14.0
    matplotlib.rcParams['xtick.labelsize'] = 10.0
    matplotlib.rcParams['legend.fontsize'] = 10.0
    explode=(0.05, 0.0)
    #colors=('b','g')
    fig = Figure(figsize=(figwidth,figheight))
    ax = fig.add_subplot(1,1,1)
    ax.set_yticks([])
    runs = models.Experiment.objects.all()
    # Get only Experiments that are still on fileserver: not deleted or archived.
    runs = runs.exclude(expName__in = models.Backup.objects.all().values('backupName'))
    num_arch = len(runs.filter(storage_options='A'))
    num_del = len(runs.filter(storage_options='D'))
    num_keep = len(runs.filter(storage_options='KI'))
    total = sum([num_arch,num_del,num_keep])
    frac_arch = (float(num_arch)/float(total))*100
    frac_del = (float(num_del)/float(total))*100
    frac_keep = (float(num_keep)/float(total))*100
    frac = [frac_arch,frac_del,frac_keep]
    if float(frac[0]+frac[1]+frac[2]) > 100.0:
            frac[2] = frac[2] - (float(frac[0]+frac[1]+frac[2])-100.0)
    i = 0
    c = [0.5, 0.1, 1]
    for fr in frac:
        ax.barh(bottom = 0, width = fr, left = i, height = 1, color = c)
        c = [0.5, 0.1, c[2]-0.3]
        i = i + fr
    ax.set_title('Storage Option Breakdown')
    ax.set_xlabel('% of runs')
    if frac[0] >= 15:
        ax.text(float(frac[0])/200, 0.5, 'Archive', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
    if frac[1] >= 15:
        ax.text(float(frac[1])/200+float(frac[0])/100, 0.5, 'Delete', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
    if frac[2] >= 10:
        ax.text(float(frac[0])/100 + float(frac[1])/100 + float(frac[2])/200, 0.5, 'Keep', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
    fig.subplots_adjust(bottom = 0.3, top = 0.75)
    canvas = FigureCanvas(fig)
    response = http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response

def fs_statusbar(request, percentFull):
    full = float(percentFull)
    threshold = float(models.BackupConfig.objects.all().order_by('pk').reverse()[0].backup_threshold)
    if threshold == 0:
        threshold = float(0.01)
    '''Using args instead of the fileserver objects; should be faster.'''
    figwidth = 9
    figheight = 1.5
    matplotlib.rcParams['font.size'] = 10.0
    matplotlib.rcParams['axes.titlesize'] = 12.0
    matplotlib.rcParams['xtick.labelsize'] = 10.0
    matplotlib.rcParams['legend.fontsize'] = 10.0
    explode=(0.05, 0.0)
    Ncols = 3
    plotheight = figwidth/Ncols
    H = plotheight/figheight
    W = 1.0 / Ncols
    margin = 0.1
    left = [W*margin, W*(1+margin), W*(2+margin)]
    bottom = H*margin
    width = W*(1-2*margin)
    height = H*(1-2*margin)
    fig = Figure(figsize=(figwidth,figheight))
    ax = fig.add_subplot(1,1,1)
    ax.set_yticks([])
    frac = [full, 100-full]
    i = 0
    if full <= threshold*0.7:
        r = 0.0
        g = 0.8
        b = 0.3
    elif full <= threshold * 0.85:
        r = 1.0
        g = 0.85
        b = 0.0
    elif full < threshold:
        r = 1.0
        g = 0.6
        b = 0.0
    else:
        r = 0.85
        g = 0.1
        b = 0.1
    c = [r, g, b]
    for fr in frac:
        ax.barh(bottom = 0, width = fr, height = 0.2, left = i, color = c)
        i += fr
        r = 0.0
        g = 0.4375
        b = 0.9375
        c = [r, g, b]
    ax.set_xlabel('% Capacity')
    if threshold >= 88:
        textHeight = 1.2
    else:
        textHeight = 0.5
    
    '''ax2 = fig.add_subplot(111)
    ax2.patch.set_alpha(0.0)
    ax2.set_yticks([])
    ax2.set_xticks([])
    img = imread('/var/www/site_media/images/serverFull.png')
    ax2.imshow(img)'''
    
    ax.axvline(threshold, 0, 1, color='#000000', linewidth=3, marker='d', markersize=14)
    ax.text(float(threshold)/100 + 0.02, textHeight, 'Threshold', transform=ax.transAxes, fontsize=10, verticalalignment='center')
    if full > threshold and int(full) >= 10:
        ax.text(float(full)/200, 0.25, 'Over\nThreshold', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
    elif int(full) >= 10:
        ax.text(float(full)/200, 0.25, 'Used', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
    if int(full) >= 10:
        ax.text((100-float(full))/200+float(full)/100, 0.25, 'Free', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
    ax.set_title('File Server Space')
    fig.subplots_adjust(bottom = 0.3, top = 0.75)
    canvas = FigureCanvas(fig)
    response = http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response
    
def archive_drivespace_bar(request):
    '''Displays as a horizontal bar chart, the free vs used space
    on the archive drive.  Will only display if it is mounted'''
    try:
        bk = models.BackupConfig.objects.all()[0] # assume only one configuration possible
        figwidth = 9   # inches
        figheight = 1.5   # inches
        matplotlib.rcParams['font.size'] = 10.0
        matplotlib.rcParams['axes.titlesize'] = 14.0
        matplotlib.rcParams['xtick.labelsize'] = 10.0
        matplotlib.rcParams['legend.fontsize'] = 10.0
        explode=(0.05, 0.0)
        c = '#ff8800'
        
        if bk.backup_directory == 'None':
            #return http.HttpResponse()
            used_frac = 0
            free_frac = 0
            title = "<Archive not Configured>"
            subtitle = ''
            labels = ['','']
        else:
            path,totalSpace,freeSpace,blocksize = disk_attributes(bk.backup_directory)
            used_frac = (float(totalSpace-freeSpace)/float(totalSpace))
            free_frac = 1-used_frac
            title = 'Archive space'
            subtitle = '%s'%bk.name 
            labels = ['Used','Free']
            
        frac = [used_frac*100,free_frac*100]
        
        if frac[0] >= 90:
            tHeight = 1.2
        else:
            tHeight = 0.5
        
        fig = Figure(figsize=(figwidth,figheight))
        ax = fig.add_subplot(1,1,1)
        ax.set_yticks([])
        #fig.subplots_adjust(wspace=0.5,hspace=0.5,top=0.84)
        if float(frac[0]+frac[1]) > 100.0:
            frac[1] = frac[1] - (float(frac[0]+frac[1])-100.0)
        i = 0
        for fr in frac:
            ax.barh(bottom=0, left=i, width=fr, color = c)
            c = '#0077ee'
            i += fr
        #ax.text(frac[0]/100 + 0.02, tHeight, '%s'%('%00.2f'%frac[0]+'%'), transform=ax.transAxes, fontsize=10, verticalalignment='center')
        if int(frac[0]) >= 10:
            ax.text(float(frac[0])/200, 0.5, 'Used\nSpace', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
        if int(frac[1]) >= 10:
            ax.text((100-float(frac[0]))/200+float(frac[0])/100, 0.5, 'Free\nSpace', transform=ax.transAxes, fontsize=10, verticalalignment='center', horizontalalignment='center')
        ax.set_title('%s\n%s'%(title, subtitle))
        ax.set_xlabel('% Capacity')
        fig.subplots_adjust(bottom = 0.27, top = 0.62)
        canvas = FigureCanvas(fig)
        response = http.HttpResponse(content_type='image/png')
        canvas.print_png(response)
        return response
    except Exception as inst:
        open('/tmp/graphProblemLog.txt', 'w').write('problem: %s\n%s'%(inst, bk))

def file_server_status(request):    
    '''Displays as a pie chart the sum total of all the
    drivespace on all the fileservers in the database
    as well as showing what percent of the total space
    is used by each fileserver'''
    fileservers = models.FileServer.objects.all()
    total_space = 0.0
    used_space = []
    labels = []
    for fs in fileservers:
        try:
            att = disk_attributes(fs.filesPrefix)
        except OSError:
            continue
        total_space += att[1]
        used_space.append(att[1]-att[2])
        labels.append(att[0])
    frac = [float(us)/total_space for us in used_space]
    free = (total_space - sum(used_space))/total_space
    frac.append(float(free))
    labels.append('Free')
    # create figure
    figwidth = 3   # inches
    figheight = 3   # inches
    matplotlib.rcParams['font.size'] = 10.0
    matplotlib.rcParams['axes.titlesize'] = 14.0
    matplotlib.rcParams['xtick.labelsize'] = 10.0
    matplotlib.rcParams['legend.fontsize'] = 10.0
    explode=(0.05, 0.0)
    #colors=('b','g')
    Ncols = 3
    plotheight = figwidth/Ncols
    H = plotheight/figheight
    W = 1.0 / Ncols
    margin = 0.1
    left = [W*margin, W*(1+margin), W*(2+margin)]
    bottom = H*margin
    width = W*(1-2*margin)
    height = H*(1-2*margin)
    fig = Figure(figsize=(figwidth,figheight))
    ax = fig.add_subplot(1,1,1)
    ax.pie(frac,
           autopct='%1.f%%',
           labels=labels) 
    ax.set_title('File Server Space')
    canvas = FigureCanvas(fig)
    response = http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response

def per_file_server_status(request):
    '''Displays as separate individual pie charts the 
    free vs used space for each file server.  If there is 
    only one file server this graph will not be rendered
    as it will be identical to the other graphs already shown'''
    fileservers = models.FileServer.objects.all()
    if len(fileservers)>1:
        free_space = []
        used_space = []
        total_space = []
        titles = []
        frac = []
        for fs in fileservers:
            try:
                att = disk_attributes(fs.filesPrefix)
            except OSError:
                continue
            total_space.append(att[1])
            used_space.append(att[1]-att[2])
            free_space.append(att[2])
            titles.append(fs.name)
        frac = [(float(us)/float(ts),float(fs)/float(ts)) for us,fs,ts in zip(used_space,free_space,total_space)]
        labels = ['Used','Free']
        numGraphs = math.ceil(math.sqrt(len(frac)))
        # create figure
        figwidth = 3   # inches
        figheight = 3   # inches
        matplotlib.rcParams['font.size'] = 10.0-math.sqrt(float(numGraphs))
        matplotlib.rcParams['axes.titlesize'] = 14.0-math.sqrt(float(numGraphs))
        matplotlib.rcParams['xtick.labelsize'] = 10.0-math.sqrt(float(numGraphs))
        matplotlib.rcParams['legend.fontsize'] = 10.0-math.sqrt(float(numGraphs))
        explode=(0.05, 0.0)
        colors=('b','g')
        fig = Figure(figsize=(figwidth,figheight))
        for n,(f,t) in enumerate(zip(frac,titles)):
            n = n+1
            ax = fig.add_subplot(numGraphs,numGraphs,n)
            fig.subplots_adjust(wspace=0.5,hspace=0.5,top=0.84)
            ax.pie(f,
                   autopct='%1.f%%',
                   labels=labels)
            ax.set_title('%s' % t)
        fig.suptitle('Free Space/Fileserver',fontsize=15)
        canvas = FigureCanvas(fig)
        response = http.HttpResponse(content_type='image/png')
        canvas.print_png(response)
        return response
    else:
        return http.HttpResponse()

def archive_drivespace(request):
    '''Displays as a pie chart, the free vs used space
    on the archive drive.  Will only display if it is mounted'''
    bk = models.BackupConfig.objects.all()[0] # assume only one configuration possible
    figwidth = 3   # inches
    figheight = 3   # inches
    matplotlib.rcParams['font.size'] = 10.0
    matplotlib.rcParams['axes.titlesize'] = 14.0
    matplotlib.rcParams['xtick.labelsize'] = 10.0
    matplotlib.rcParams['legend.fontsize'] = 10.0
    explode=(0.05, 0.0)
    colors=('b','g')
    
    if bk.backup_directory == 'None':
        #return http.HttpResponse()
        used_frac = 0
        free_frac = 0
        title = "<Archive not Configured>"
        labels = ['','']
    else:
        path,totalSpace,freeSpace,blocksize = disk_attributes(bk.backup_directory)
        used_frac = (float(totalSpace-freeSpace)/float(totalSpace))
        free_frac = 1-used_frac
        title = '%s Space' % bk.name
        labels = ['Used','Free']
        
    frac = [used_frac,free_frac]
    
    fig = Figure(figsize=(figwidth,figheight))
    ax = fig.add_subplot(1,1,1)
    #fig.subplots_adjust(wspace=0.5,hspace=0.5,top=0.84)
    ax.pie(frac,
           autopct='%1.f%%',
           labels=labels) 
    ax.set_title(title)
    canvas = FigureCanvas(fig)
    response = http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response

def residence_time(request):
    '''Attempts to estimate how long a file will remain on 
    any given fileserver.  It looks at archived and deleted runs
    individually and creates separate bars for each of them.  The 
    method used to calculate residence time is to look at the 
    average time the last 20 were on the file server before being 
    archived or deleted.  A simple difference in time is used. '''
    fileservers = models.FileServer.objects.all()
    numGraphs = math.ceil(math.sqrt(len(fileservers)))
    # create figure
    figwidth = 4   # inches
    figheight = 3   # inches
    numGraphs = math.ceil(math.sqrt(len(fileservers)))
    matplotlib.rcParams['font.size'] = 10.0-math.sqrt(float(numGraphs))
    matplotlib.rcParams['axes.titlesize'] = 14.0-math.sqrt(float(numGraphs))
    matplotlib.rcParams['xtick.labelsize'] = 10.0-math.sqrt(float(numGraphs))
    matplotlib.rcParams['legend.fontsize'] = 10.0-math.sqrt(float(numGraphs))
    fig = Figure(figsize=(figwidth,figheight))
    ax = fig.add_subplot(1,1,1)
    count = 0
    max_scale = 0
    xticknames = []
    xtickpositions = []
    arch = models.Backup.objects.all().order_by('-backupDate')
    for n,fs in enumerate(fileservers):
        last_archived = arch.filter(experiment__expDir__icontains=fs.filesPrefix).filter(isBackedUp=True)[:20]
        last_deleted = arch.filter(experiment__expDir__icontains=fs.filesPrefix).filter(isBackedUp=False)[:20]
        bars = []  
        time_before_arch = [(la.backupDate-la.experiment.date) for la in last_archived]
        time_before_delete = [(ld.backupDate-ld.experiment.date) for ld in last_deleted]
        if time_before_arch:
            ave_a = float(sum([d.days for d in time_before_arch]))/float(len(time_before_arch))
            bars.append(ave_a)
        else:
            bars.append(0.1)
        if time_before_delete:
            ave_d = float(sum([d.days for d in time_before_delete]))/float(len(time_before_delete))
            bars.append(ave_d)
        else:
            bars.append(0.1)
        if not bars:
            continue
        xticklabels = ['Archive','Delete']
        width = .2
        basepos = [count,count+width+.03]
        middlepos = float(sum(basepos))/2.0
        color = ('b','g')
        value = []
        for b in bars:
            if b != 0.1:
                value.append('%.f' % b)
            else:
                value.append('No Data')
        for i,b in enumerate(bars):
            ax.bar(basepos[i],bars[i],align='center',width=width,label=xticklabels[i],color=color[i])
            ax.text(basepos[i],bars[i],str(value[i]),horizontalalignment='center')
        ax.set_title('Average Days on Fileserver')
        xticknames.append(str(fs.filesPrefix))
        xtickpositions.append(middlepos)
        ax.yaxis.set_ticks_position("none")
        ax.set_yticklabels('')
        if max(bars)>max_scale:
            max_scale = max(bars)
        count+=1
    ax.set_xticklabels(xticknames)
    ax.set_xticks(xtickpositions)
    ax.legend(xticklabels)
    ax.set_ybound(0,max_scale*1.50)
    canvas = FigureCanvas(fig)
    response = http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response
