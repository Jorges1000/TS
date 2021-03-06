# Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved

"""
Models
======

Django database models for the Torrent Analysis Suite.

``models`` defines the way the frontend database stores information about
Personal Genome Machine experiments. This information includes...

* The location of experiment data (the ``Experiment`` class)
* Analysis statistics generated from experiment data (the ``Results`` class)
* Test fragment templates  (the ``Template`` class).

``models`` also contains information about infrastructure that supports
the data gathering and analysis.
"""
from os import path
import datetime
import re
import os
import os.path
import traceback
import xmlrpclib
from twisted.web.xmlrpc import Proxy
import time

from django.core.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist

import iondb.settings

from django import forms

from django.conf import settings
from django.contrib import admin
from django.db import models
from django.db.models.query import QuerySet
from iondb.backup import devices
import json

from iondb.rundb import json_field

import shutil
import uuid
import hmac
import random
import string
import logging
from iondb.rundb import tasks

try:
    from hashlib import sha1
except ImportError:
    import sha
    sha1 = sha.sha

logger = logging.getLogger(__name__)

from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.utils.encoding import force_unicode
from django.core import urlresolvers
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from distutils.version import LooseVersion


import copy

# Auto generate tastypie API key for users
from tastypie.models import create_api_key
models.signals.post_save.connect(create_api_key, sender=User)

# Create your models here.

class Project(models.Model):
    #TODO The name should not be uniq because there can be a public one
    #and a private one with the same name and that would not work
    name = models.CharField(max_length=32, unique = True)
    creator = models.ForeignKey(User)
    public = models.BooleanField(default=True)
    # This will be set to the time a new record is created
    created = models.DateTimeField(auto_now_add=True)
    # This will be set to the current time every time the model is updated
    modified = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.name

#    def save(self, force_insert=False, force_update=False, using=None):
#        logger.error(self.pk)
#        if self.pk:
#            current = Project.objects.get(self.pk)
#            logger.error( current.creator.username, self.creator.username)
#            if current and current.creator.pk != self.creator.pk: 
#                raise ValidationError('creator is readonly')
#        models.Model.save(self, force_insert=force_insert, force_update=force_update, using=using)

    @classmethod
    def bulk_get_or_create(cls, projects, user=None):
        """projects is either a string specifying a single project name or
        a list of strings for such.  Each project name is queried and a project
        with that name is created if necessary and all named projects are
        returned in a list.
         """
        if not user:
            user = User.objects.order_by('pk')[0]
        if isinstance(projects, basestring):
            projects = [projects]
        return [Project.objects.get_or_create(name__iexact=name, defaults={'name':name,'creator':user})[0] for name in projects]

class KitInfoManager(models.Manager):
    def get_by_natural_key(self, kitType, kitName):
        return self.get(kitType = kitType, name = kitName)
    

class KitInfo(models.Model):
    
    ALLOWED_KIT_TYPES = (
        ('SequencingKit', 'SequencingKit'),
        ('LibraryKit', 'LibraryKit'),
        ('TemplatingKit', 'TemplatingKit'),
        ('AdapterKit', "AdapterKit"),
        ('ControlSequenceKit', "ControlSequenceKit"),
        ('SamplePrepKit', "SamplePrepKit")
    )
    
    kitType = models.CharField(max_length=20, choices=ALLOWED_KIT_TYPES)
    name = models.CharField(max_length=512, blank=False, unique=True)
    description = models.CharField(max_length=3024, blank=True)
    flowCount = models.PositiveIntegerField()

    ALLOWED_NUCLEOTIDE_TYPES = (
        ('', 'Any'),
        ('dna', 'DNA'),
        ('rna', 'RNA')
    )

    nucleotideType = models.CharField(max_length=64, choices=ALLOWED_NUCLEOTIDE_TYPES, default='', blank=True)

    ALLOWED_RUN_MODES = (
        ('', 'Undefined'),                         
        ('single', 'SingleRead'),
        ('pe', 'PairedEnd')
    )

    #run mode
    runMode = models.CharField(max_length=64, choices=ALLOWED_RUN_MODES, default='', blank=True)

    isActive = models.BooleanField(default = True)

    ALLOWED_INSTRUMENT_TYPES = (
        ('', 'Any'),                         
        ('pgm', 'PGM'),
        ('proton', 'Proton')
    )
    #compatible instrument type
    instrumentType = models.CharField(max_length=64, choices=ALLOWED_INSTRUMENT_TYPES, default='', blank=True)

    objects = KitInfoManager()
            
    def __unicode__(self):
        return u'%s' % self.name
    
    def natural_key(self):
        return (self.kitType, self.name)       

    class Meta:
        unique_together = (('kitType', 'name'),)


class KitPartManager(models.Manager):
    def get_by_natural_key(self, kitBarcode):
        return self.get(barcode = kitBarcode)


class KitPart(models.Model):
    kit = models.ForeignKey(KitInfo, null=False)
    barcode = models.CharField(max_length=7, unique=True, blank=False)
    
    objects = KitPartManager()

    def __unicode__(self):
        return u'%s' % self.barcode

    def natural_key(self):
        return (self.barcode)  
         
    class Meta:
        unique_together = (('barcode'),)    

class RunType(models.Model):
    runType = models.CharField(max_length=512)
    barcode = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    meta = json_field.JSONField(blank=True, null=True, default = "")

    ALLOWED_NUCLEOTIDE_TYPES = (
        ('', 'Any'),
        ('dna', 'DNA'),
        ('rna', 'RNA')
    )

    nucleotideType = models.CharField(max_length=64, choices=ALLOWED_NUCLEOTIDE_TYPES, default='dna', blank=True)
    
    def __unicode__(self):
        return self.runType
    


class ApplProduct(models.Model):
    #application with no product will have a default product pre-loaded to db to hang all the
    #application-specific settings
    productCode = models.CharField(max_length = 64, unique=True, default='any', blank=False)
    productName = models.CharField(max_length = 128, blank=False)
    description = models.CharField(max_length = 1024, blank=True)
    applType = models.ForeignKey(RunType)
    isActive = models.BooleanField(default = True)
    #if isVisible is false, it will not be shown as a choice in UI
    isVisible = models.BooleanField(default = False)
    defaultSequencingKit = models.ForeignKey(KitInfo, related_name='seqKit_applProduct_set', null=True)
    defaultLibraryKit = models.ForeignKey(KitInfo, related_name='libKit_applProduct_set', null=True)
    defaultPairedEndSequencingKit = models.ForeignKey(KitInfo, related_name='peSeqKit_applProduct_set', null=True)
    defaultPairedEndLibraryKit = models.ForeignKey(KitInfo, related_name='peLibKit_applProduct_set', null=True)
    defaultGenomeRefName = models.CharField(max_length = 1024, blank=True, null=True)
    #this is analogous to bedFile in PlannedExperiment 
    defaultTargetRegionBedFileName = models.CharField(max_length = 1024, blank=True, null=True) 
    #this is analogous to regionFile in PlannedExperiment
    defaultHotSpotRegionBedFileName = models.CharField(max_length = 1024, blank=True, null=True)

    ##20120608-to-be-replaced-by-json-clob-according-to-josh compatiblePlugins = models.ManyToManyField(Plugin, related_name='applProduct_set')
    ##20120608-to-be-replaced-by-json-clob-according-to-josh defaultPlugins = models.ManyToManyField(Plugin, related_name='defaultApplProduct_set')

    defaultChipType = models.CharField(max_length=128, blank=True, null=True)
    isDefault = models.BooleanField(default = False)
    isPairedEndSupported = models.BooleanField(default = True)
    isDefaultPairedEnd = models.BooleanField(default = False)
    defaultVariantFrequency = models.CharField(max_length = 512, blank=True, null=True)
    
    defaultFlowCount = models.PositiveIntegerField(default = 0)
    defaultPairedEndAdapterKit = models.ForeignKey(KitInfo, related_name='peAdapterKit_applProduct_set', null=True)
    defaultTemplateKit = models.ForeignKey(KitInfo, related_name='templateKit_applProduct_set', null=True)
    defaultControlSeqKit = models.ForeignKey(KitInfo, related_name='controlSeqKit_applProduct_set', null=True)
    
    #sample preparation kit
    defaultSamplePrepKit = models.ForeignKey(KitInfo, related_name='samplePrepKit_applProduct_set', null=True)
    

    def __unicode__(self):
        return u'%s' % self.productName  


class QCType(models.Model):
    qcName = models.CharField(max_length=512, blank=False, unique=True)
    description = models.CharField(max_length=1024, blank=True)
    minThreshold = models.PositiveIntegerField(default=0)
    maxThreshold = models.PositiveIntegerField(default=100)
    defaultThreshold = models.PositiveIntegerField(default=0)
    
    def __unicode__(self):
        return u'%s' % self.qcName     
    

        
class PlannedExperiment(models.Model):
    """
    Create a planned run to ease the pain on manually entry on the PGM
    """

    #plan name
    planName = models.CharField(max_length=512,blank=True,null=True)

    #Global uniq id for planned run
    planGUID = models.CharField(max_length=512,blank=True,null=True)

    #make a id for easy entry
    planShortID = models.CharField(max_length=5,blank=True,null=True,db_index=True)

    #was the plan already executed?
    planExecuted = models.BooleanField(default=False)

    ALLOWED_PLAN_STATUS = (
        ('', 'None'),
        ('voided', 'Voided'),
        ('reserved', 'Reserved')
    )

    #planStatus - Did the plan work?
    planStatus = models.CharField(max_length=512, blank=True)

    #who ran this
    username = models.CharField(max_length=128, blank=True, null=True)

    #what PGM started this
    planPGM = models.CharField(max_length=128, blank=True, null=True)

    #when was this added to the plans
    date = models.DateTimeField(blank=True,null=True)

    #When was the plan executed?
    planExecutedDate = models.DateTimeField(blank=True,null=True)

    #add metadata grab bag
    metaData = json_field.JSONField(blank=True)

    chipType = models.CharField(max_length=32,blank=True,null=True)
    chipBarcode = models.CharField(max_length=64, blank=True,null=True)
    
    #we now persist the sequencing kit name instead of its part number. to be phased out
    seqKitBarcode = models.CharField(max_length=64, blank=True,null=True)

    #name of the experiment
    expName = models.CharField(max_length=128,blank=True)

    #Pre-Run/Beadfind
    usePreBeadfind = models.BooleanField()

    #Post-Run/Beadfind
    usePostBeadfind = models.BooleanField()

    #cycles
    cycles = models.IntegerField(blank=True,null=True)

    #flow vs cycles ? do we need this?
    flows = models.IntegerField(blank=True,null=True)

    #AutoAnalysis - autoName string
    autoAnalyze = models.BooleanField()
    autoName = models.CharField(max_length=512, blank=True, null=True)

    preAnalysis = models.BooleanField()

    #RunType -- this is from a list of possible types (aka application)
    runType = models.CharField(max_length=512, blank=True, null=True)

    #Library - should this be a text field?
    library = models.CharField(max_length=512, blank=True, null=True)

    #barcode
    barcodeId = models.CharField(max_length=256, blank=True, null=True)

    #adapter (20120313: this was probably for forward 3' adapter but was never used.  Consider this column obsolete)
    adapter = models.CharField(max_length=256, blank=True, null=True)

    #Project
    projects = models.ManyToManyField(Project, related_name='plans', blank=True)

    #runname - name of the raw data directory
    runname = models.CharField(max_length=255, blank=True, null=True)


    #Sample
    sample = models.CharField(max_length=127, blank=True, null=True)

    #usernotes
    notes = models.CharField(max_length=1024, blank=True, null=True)

    flowsInOrder = models.CharField(max_length=512, blank=True, null=True)
    #library key for forward run
    libraryKey = models.CharField(max_length=64, blank=True,null=True)
    storageHost = models.CharField(max_length=128, blank=True, null=True)
    reverse_primer = models.CharField(max_length=128, blank=True, null=True)

    #bed file
    #Target Regions BED File: bedfile
    #Hotspot Regions BED File: regionfile
    bedfile = models.CharField(max_length=1024,blank=True)
    regionfile = models.CharField(max_length=1024,blank=True)

    #add field for ion reporter upload plugin workflow
    irworkflow = models.CharField(max_length=1024,blank=True)

    #we now persist the sequencing kit name instead of its part number. to be phased out
    libkit = models.CharField(max_length=512, blank=True, null=True)

    variantfrequency = models.CharField(max_length=512, blank=True, null=True)

    STORAGE_CHOICES = (
        ('KI', 'Keep'),
        ('A', 'Archive Raw'),

        ('D', 'Delete Raw'),
        )

    storage_options = models.CharField(max_length=200, choices=STORAGE_CHOICES,
                                       default='A')

    #for paired-end reverse run, separate library key and 3' adapter needed
    reverselibrarykey = models.CharField("library key for reverse run", max_length=64, blank=True, null=True)
    reverse3primeadapter = models.CharField("3' adapter for reverse run", max_length=512, blank=True, null=True)


    #for forward run, 3' adapter specific to this plan
    forward3primeadapter = models.CharField("3' adapter for forward run", max_length=512, blank=True, null=True)
    
    isReverseRun = models.BooleanField(default=False)
    
    #we now persist the kit names instead of their part number
    librarykitname = models.CharField(max_length=512, blank=True, null=True)
    sequencekitname = models.CharField(max_length=512, blank=True, null=True)
    
    #plan displayed name allows embedded blanks. 
    #planName is the display name with embedded blanks converted to underscores
    
    planDisplayedName = models.CharField(max_length=512,blank=True,null=True)
    
    ALLOWED_RUN_MODES = (
        ('', 'Undefined'),                         
        ('single', 'SingleRead'),
        ('pe', 'PairedEnd')
    )

    #run mode
    runMode = models.CharField(max_length=64, choices=ALLOWED_RUN_MODES, default='', blank=True)
    
    #whether this is a plan template
    isReusable = models.BooleanField(default=False)
    isFavorite = models.BooleanField(default=False)

    #whether this is a pre-defined plan template
    isSystem = models.BooleanField(default=False)

    #if instrument user does not select a plan for the run, 
    #crawler will use the properties from the system default plan or template 
    #for the run
    isSystemDefault = models.BooleanField(default=False)
    
    #used for paired-end plan & plan template
    #for PE plan template, there will only be 1 template in db
    #for PE plan, there will be 1 parent plan and 2 children (1 forward and 1 reverse) 

    isPlanGroup = models.BooleanField(default=False)
    parentPlan = models.ForeignKey('self', related_name='childPlan_set', null=True, blank=True)

    qcValues = models.ManyToManyField(QCType, through="PlannedExperimentQC", null=True)
     
    #allow spaces in sampleDisplayedName
    sampleDisplayedName = models.CharField(max_length=127, blank=True, null=True)
    
    barcodedSamples = json_field.JSONField(blank=True, null=True)
        
    #we now persist the kit names instead of their part number
    templatingKitName = models.CharField(max_length=512, blank=True, null=True)
    controlSequencekitname = models.CharField(max_length=512, blank=True, null=True)

    #pairedEnd library adapter name
    pairedEndLibraryAdapterName = models.CharField(max_length=512, blank=True, null=True)
    
    #sample preparation kit name
    samplePrepKitName = models.CharField(max_length=512, blank=True, null=True)

    selectedPlugins = json_field.JSONField(blank=True, null=True)
    
    def __unicode__(self):
        if self.planName:
            return self.planName
        return "Plan_%s" % self.planShortID

    def findShortID(self):
        """Search for a plan short ID that has not been used"""

        planShortID = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(5))

        if PlannedExperiment.objects.filter(planShortID=planShortID, planExecuted=False):
            self.findShortID()

        return planShortID


    def getSeqKitBarcodeForSave(self):
        #we now save the sequencing kit name in addition to the kit's part number in a plan but
        #csv upload, for backward compatibility, will continue to ask user to include seqKitBarcode only.
        #when saving (or updating a pre-existing plan, we want to populate the new field 
        #with the info if not provided
        if (self.seqKitBarcode and not self.sequencekitname):
            try:
                selectedSeqKitPart = KitPart.objects.get(barcode=self.seqKitBarcode)
                if (selectedSeqKitPart):
                    selectedSeqKit = selectedSeqKitPart.kit
                    if (selectedSeqKit):
                        return selectedSeqKit.name

            except KitPart.DoesNotExist:
                #if we can't determine the seq kit name, leave it as is
                #do not fail the save()               
                logger.info("NO kit part found at plan for sequencingKitBarcode=%s" % self.seqKitBarcode)
                return None
        else:
            return self.sequencekitname
        

    def getLibraryKitForSave(self):
        #we now save the library kit name instead of the kit's part number to PlannedExperiment
        #when updating a pre-existing plan, we want to populate the new field with the info
        if (self.libkit and not self.librarykitname):
            try:
                selectedLibKitPart = KitPart.objects.get(barcode=self.libkit)
                if (selectedLibKitPart):
                    selectedLibKit = selectedLibKitPart.kit
                    if (selectedLibKit):
                        return selectedLibKit.name
            except KitPart.DoesNotExist:
                #if we can't determine the library kit name, leave it as is
                #do not fail the save()               
                logger.info("NO kit part found at PlannedExperiment for libraryKitBarcode=%s" % self.libkit)                    
                return None
        else:
            return self.librarykitname
        
        

    def getForward3primeAdapterForSave(self):
        #For paired-end forward run, if 3' adapter is missing, programmatically set it here 
        #since the preferred 3' adapter is not the default.                                                 
        if not self.forward3primeadapter:
            try:
                forwardPEAdapter = ThreePrimeadapter.objects.filter(direction="Forward", runMode="pe", name__contains="Ion")[0]
                return forwardPEAdapter.sequence
            except ThreePrimeadapter.DoesNotExist:
                logger.info("No preferred paired-end forward 3 prime adapter found at PlannedExperiment")  
            except:
                logger.info("Error: Preferred paired-end forward 3 prime adapters at PlannedExperiment")
                return None
        else:
            return self.forward3primeadapter
        
                        

    def getReverseLibraryKeyForSave(self):
        if self.reverselibrarykey:
            newReverseLibraryKey = ''.join(self.reverselibrarykey)
        else:
            newReverseLibraryKey = None
        return newReverseLibraryKey
                  

    def getReverse3primeAdapterForSave(self):
        if self.reverse3primeadapter:
            newReverse3PrimeAdapter = ''.join(self.reverse3primeadapter)
        else:
            newReverse3PrimeAdapter = None
        return newReverse3PrimeAdapter        

        
    def save(self):
        #if runMode = 'pe', 1 paired-end plan for template and 3 paired-end plans for plan run (1 parent, 2 children)
        #20120609-TODO
        #after the pre3.0 plan creation ui is gone, it would be nice to refactor TS for child plans to
        #have minimum data, and retrieve missing values from the parent plan instead.
        #for now, we're pushing parent plan values to child plana for attributes that already pre-exist in db 
        #prior to v3.0.  However, for projects, qc thresholds and plugins, since they are new to v3.0,
        #they will stay with the parent plan and won't be replicated in the child plan
         
        #if user uses the old ui to save a plan directly, planDisplayedName will have no user input
        if not self.planDisplayedName:
            self.planDisplayedName = self.planName;

        #likewise for sampleDisplayedName
        if not self.sampleDisplayedName:
            self.sampleDisplayedName = self.sample;
            
        if not self.notes:
            self.notes = ""

        self.date = datetime.datetime.now()
        if not self.planShortID:
            self.planShortID = self.findShortID()
        if not self.planGUID:
            self.planGUID = str(uuid.uuid4())

        self.sequencekitname = self.getSeqKitBarcodeForSave()      
              
        #If user is CREATING a new plan or CHANGING a forward to a plan that is marked for paired-end run,
        #behind the scene, we'll create 2 plans; one for forward and one reverse with
        #_rev appended to the user input plan name for the "reverse" plan.
        #
        isToCreate2Plans = False
        isToCreateChildPlans = False
        isToUpdateAndCreatePlan = False
        isToUpdateChildPlans = False
        isToDeleteChildPlans = False
        isToSkipPlanUpdate = False
        
        parentOid = 0
        
        #for backward and non-gui compatibility if user is not using the v3.0 plan/template wizard to create a plan
        if (self.isReverseRun == True):
            self.runMode = "pe"
            
        if (self.id):
            dbPlan = PlannedExperiment.objects.get(pk=self.id)
 
            #last modified date
            self.date = datetime.datetime.now()

            self.librarykitname = self.getLibraryKitForSave() 
                                                
            #scenario: change from PE to PE or non-PE to PE
            if (self.runMode == "pe"):
                if (dbPlan.runMode == "pe"):                    
                    super(PlannedExperiment, self).save() 
                    if (not self.isReusable):
                        isToUpdateChildPlans = True                    
                else:
                    super(PlannedExperiment, self).save()
                    if (not self.isReusable):
                        isToCreateChildPlans = True      
            else:
                #scenario: change from PE to non-PE
                if (dbPlan.runMode == "pe"):
                    #this should have been caught in views.editplanexperiment. but just in case...
                    childPlans = self.childPlan_set.all()
                    for childPlan in childPlans:         
                        if (childPlan.planExecuted):

                            logger.info("models.PlannedExperiment.save() Cannot change the run mode of a paired-end plan that has already been used")
                            logger.info("models.PlannedExperiment.save() plan.oid=%s; planDisplayedName=%s; childPlan.oid=%s;" % (str(self.id), self.planDisplayedName, str(childPlan.id)))
                            isToSkipPlanUpdate = True

                            raise ValidationError("Error: Cannot change the run mode of paired-end plan: %s that has already been used." % self.planDisplayedName)
        
                    if not isToSkipPlanUpdate:
                        isToDeleteChildPlans = True
                        super(PlannedExperiment, self).save()                    
                else:  
                    #scenario: change from non-PE to non-PE (for plans created from old ui, runMode will be single
                    #if user has not clicked on the isPairedEnd checkbox
                    if (dbPlan.isReverseRun == self.isReverseRun):
                        #logger.info('Going to call super.save() to UPDATE PlannedExperiment id=%s' % self.id)
                    
                        if (self.isReverseRun):
                            self.libraryKey = None
                            self.forward3primeadapter = None                
                        else:
                            self.reverselibrarykey = None
                            self.reverse3primeadapter = None   
                    
                        super(PlannedExperiment, self).save()                 
                    else:
                        #scenario: change from isPairedEnd checkbox checked to unchecked
                        #for the old PE, forward and reverse are 2 separate plans with no parents
                        if (self.isReverseRun == False):
                            self.reverselibrarykey = None
                            self.reverse3primeadapter = None
                    
                            super(PlannedExperiment, self).save()
                        else:
                            #scenario: change from isPairedEnd checkbox unchecked 
                            #user has clicked the isPairedEnd checkbox, update the current record and create a counterpart                
                            isToUpdateAndCreatePlan = True                

        else:                
            #if user creates a new forward plan
            if (self.isReverseRun == False):
                #if pairedEnd runMode
                if (self.runMode == "pe"):
                    if (not self.isReusable):    
                        isToCreateChildPlans = True
                else:
                    #do not blank out the reverse info for a PE plan template               
                    self.reverselibrarykey = None
                    self.reverse3primeadapter = None
                             
                if PlannedExperiment.objects.filter(planShortID=self.planShortID, planExecuted=False):
                    self.planShortID = self.findShortID()

                             
                #logger.info('Going to CREATE the 1 UNTOUCHED plan with name=%s' % self.planName) 
                super(PlannedExperiment, self).save() 
                parentOid = self.id
                
                ##logger.debug("models.plannedExperiment CREATE parentOid=%s" % str(parentOid))               
            else:

                isToCreate2Plans = True
        
        #backward compatible with old ui 
        if isToCreate2Plans or isToCreateChildPlans or isToUpdateAndCreatePlan:         
            #prepare for the FORWARD plan
            selfForward = copy.copy(self)
            
            if not isToUpdateAndCreatePlan:
                selfForward.pk = None
                selfForward.isPlanGroup = False
            else:
                selfForward.isReverseRun = False
                
            if (selfForward.isReverseRun or selfForward.runMode == "pe"):
                origPlanName = copy.copy(selfForward.planName)

                #planName's db max length is 512. User is not likely to create such a long name, but just in case...
                name = selfForward.planName
                if len(selfForward.planName) > 504:
                    name = selfForward.planName[:503]
                
                #if either one of the constructed plan names already exists, insert a 3-char random code to the plan name                                 
                pairedEndForwardPlanName = ''.join([name, '_fwd'])
                pairedEndReversePlanName = ''.join([name, '_rev'])
            
                if (PlannedExperiment.objects.filter(planName = pairedEndForwardPlanName).count() > 0) or (PlannedExperiment.objects.filter(planName = pairedEndReversePlanName).count() > 0):                    
                    uniqueCode = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(3))      
                    pairedEndForwardPlanName = ''.join([name, '_', uniqueCode, '_fwd'])
                    pairedEndReversePlanName = ''.join([name, '_', uniqueCode,'_rev'])
                                                
                selfForward.isReverseRun = False

                selfForward.forward3primeadapter = selfForward.getForward3primeAdapterForSave()
                newReverseLibraryKey = selfForward.getReverseLibraryKeyForSave()
                newReverse3PrimeAdapter = selfForward.getReverse3primeAdapterForSave()
                
                selfForward.reverselibrarykey = None
                selfForward.reverse3primeadapter = None
                
                selfForward.planName = pairedEndForwardPlanName
                
                if isToCreateChildPlans:
                    selfForward.parentPlan = self
                    selfForward.planShortID = selfForward.findShortID()
                    selfForward.planGUID = str(uuid.uuid4()) 
                else:
                    if not isToUpdateAndCreatePlan:
                        #avoid plan short id collision: for users using the old ui with no parent PE plan concept
                        if PlannedExperiment.objects.filter(planShortID=selfForward.planShortID, planExecuted=False):
                            selfForward.planShortID = selfForward.findShortID()
              
                #logger.info('Going to CREATE the FORWARD plan with name=%s' % self.planName)                
                super(PlannedExperiment, selfForward).save()

                selfForward.projects = self.projects.all()
                                
                ##logger.debug("models.plannedExperiment CREATE/UPDATE child.forward.oid=%s" % str(selfForward.id))       
                
                
                #prepare for the REVERSE plan
                selfReverse = copy.copy(selfForward)
                selfReverse.pk = None
                selfReverse.planGUID = None
                selfReverse.planShortID = None
                
                selfReverse.libraryKey = None
                selfReverse.forward3primeadapter = None                        
                selfReverse.reverselibrarykey = newReverseLibraryKey
                selfReverse.reverse3primeadapter = newReverse3PrimeAdapter
                 
                #logger.info('CREATING the REVERSE plan with reverse adapter=%s' % selfReverse.reverse3primeadapter)   
                
                selfReverse.planName = pairedEndReversePlanName                         
                selfReverse.isReverseRun = True
                
                selfReverse.date = datetime.datetime.now()
                if not selfReverse.planShortID:
                    selfReverse.planShortID = selfReverse.findShortID()
                if not selfReverse.planGUID:
                    selfReverse.planGUID = str(uuid.uuid4()) 
                

                if isToCreateChildPlans:
                    selfReverse.parentPlan = self
                                        
                #logger.info('Going to CREATE the REVERSE plan with name=%s' % selfReverse.planName)                 
                super(PlannedExperiment, selfReverse).save()                    
                selfReverse.projects = self.projects.all()

                ##logger.debug("models.plannedExperiment CREATE/UPDATE child.reverse.oid=%s" % str(selfReverse.id)) 


        if isToUpdateChildPlans:
            childPlans = self.childPlan_set.all()
            for childPlan in childPlans:
                #for partially completed PE plan, its executed child plan should stay frozen
                if (childPlan.planExecuted):
                    continue
                else:                                         
                    parentDisplayedName = copy.copy(self.planDisplayedName)
                    
                    parentPlanName = copy.copy(self.planName)               
                                    
                    #planName's db max length is 512. User is not likely to create such a long name, but just in case...
                    name = parentPlanName
                    
                    if len(parentPlanName) > 504:
                        name = parentPlanName[:503]
                
                    #if either one of the constructed plan names already exists, insert a 3-char random code to the plan name
                    childPlanName = name
                    if (childPlan.isReverseRun):                               
                        childPlanName = ''.join([name, '_rev'])
                    else:
                        childPlanName = ''.join([name, '_rev'])
                                
                    if (PlannedExperiment.objects.filter(planName = childPlanName).count() > 0):                    
                        uniqueCode = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(3))     
                        if (childPlan.isReverseRun):  
                            childPlanName = ''.join([name, '_', uniqueCode,'_rev'])
                        else:
                            childPlanName = ''.join([name, '_', uniqueCode, '_fwd'])
                    
                    childPlan.planDisplayedName = parentDisplayedName
                    childPlan.planName = childPlanName
                    childPlan.chipType = self.chipType
                    childPlan.usePreBeadfind = self.usePostBeadfind
                    childPlan.usePostBeadfind = self.usePostBeadfind
                    childPlan.flows = self.flows
                    childPlan.autoAnalyze = self.autoAnalyze
                    childPlan.preAnalyze = self.preAnalysis
                    childPlan.runType = self.runType
                    childPlan.library = self.library
                    childPlan.notes = self.notes
                    childPlan.bedfile = self.bedfile
                    childPlan.regionfile = self.regionfile
                    childPlan.variantfrequency = self.variantfrequency
                    childPlan.librarykitname = self.librarykitname
                    childPlan.sequencekitname = self.sequencekitname
                    childPlan.barcodeId = self.barcodeId                    
                                                                                                         
                    childPlan.runMode = self.runMode
                    childPlan.isSystem = self.isSystem
                    childPlan.isReusable = self.isReusable
                    childPlan.sample = self.sample
                    childPlan.sampleDisplayedName = self.sampleDisplayedName
                    childPlan.username = self.username
                    childPlan.templatingKitName = self.templatingKitName 
                    childPlan.controlSequencekitname = self.controlSequencekitname
                    childPlan.barcodedSamples = self.barcodedSamples                              
                    childPlan.libraryKey = self.libraryKey
                    childPlan.forward3primeadapter = self.forward3primeadapter
                    childPlan.reverselibrarykey = self.reverselibrarykey
                    childPlan.reverse3primeadapter = self.reverse3primeadapter
                    childPlan.pairedEndLibraryAdapterName = self.pairedEndLibraryAdapterName 

                    #20120703-TODO-Until we have implemented capability for user to input library key & 3' adapter,
                    #don't bother to try to update here

                    childPlan.save()    
                    childPlan.projects = self.projects.all()

                    logger.debug("models.plannedExperiment UPDATED self.oid=%s; child.oid=%s" % (str(self.id), str(childPlan.id)))

                
        #partially executed parent PE plan will have been blocked upstream
        if isToDeleteChildPlans:
            childPlans = self.childPlan_set.all()
            for childPlan in childPlans:             
                logger.debug("models.plannedExperiment DELETE child plan.oid=%s; planName=%s" % (str(childPlan.id), childPlan.planName))
                
                childPlan.delete()


    class Meta:
        ordering = [ '-id' ]


class PlannedExperimentQC(models.Model):
    plannedExperiment = models.ForeignKey(PlannedExperiment)
    qcType = models.ForeignKey(QCType)
    threshold = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ( ('plannedExperiment', 'qcType'), )

class Experiment(models.Model):
    _CSV_METRICS = (('Sample', 'sample'),
                    #('Project', 'project'),
                    ('Library', 'library'),
                    ('Notes', 'notes'),
                    ('Run Name', 'expName'),
                    ('PGM Name', 'pgmName'),
                    ('Run Date', 'date'),
                    ('Run Directory', 'expDir'),
                    )
    STORAGE_CHOICES = (
        ('KI', 'Keep'),
        ('A', 'Archive Raw'),
        ('D', 'Delete Raw'),
    )
    # Archive action states
    ACK_CHOICES = (
        ('U', 'Unset'),          # (1) No action is pending
        ('S', 'Selected'),      # (2) Selected for action
        ('N', 'Notified'),      # (3) user has been notified of action pending
        ('A', 'Acknowledged'),  # (4) user acknowledges to proceed with action
        ('D', 'Disposed'),      # (5) Action has been completed
    )
    PRETTY_PRINT_RE = re.compile(r'R_(\d{4})_(\d{2})_(\d{2})_(\d{2})'
                                 '_(\d{2})_(\d{2})_')
    # raw data lives here absolute path prefix
    expDir = models.CharField(max_length=512)
    expName = models.CharField(max_length=128,db_index=True)
    displayName = models.CharField(max_length=128,default="")
    pgmName = models.CharField(max_length=64)
    log = json_field.JSONField(blank=True)
    unique = models.CharField(max_length=512, unique=True)
    date = models.DateTimeField(db_index=True)
    resultDate = models.DateTimeField(auto_now_add=True, db_index=True, blank=True, null=True)
    storage_options = models.CharField(max_length=200, choices=STORAGE_CHOICES,
                                       default='A')
    user_ack = models.CharField(max_length=24, choices=ACK_CHOICES,default='U')
    sample = models.CharField(max_length=64, blank=True, null=True)
    library = models.CharField(max_length=64, blank=True, null=True)
    notes = models.CharField(max_length=1024, blank=True, null=True)
    chipBarcode = models.CharField(max_length=64, blank=True)
    seqKitBarcode = models.CharField(max_length=64, blank=True)
    reagentBarcode = models.CharField(max_length=64, blank=True)
    autoAnalyze = models.BooleanField()
    usePreBeadfind = models.BooleanField()
    chipType = models.CharField(max_length=32)
    cycles = models.IntegerField()
    flows = models.IntegerField()
    expCompInfo = models.TextField(blank=True)
    baselineRun = models.BooleanField()
    flowsInOrder = models.CharField(max_length=512)
    star = models.BooleanField()
    ftpStatus = models.CharField(max_length=512, blank=True)
    #library key for forward run
    libraryKey = models.CharField(max_length=64, blank=True)
    storageHost = models.CharField(max_length=128, blank=True, null=True)
    barcodeId = models.CharField(max_length=128, blank=True, null=True)
    reverse_primer = models.CharField(max_length=128, blank=True, null=True)
    rawdatastyle = models.CharField(max_length=24, blank=True, null=True, default='single')

    sequencekitname = models.CharField(max_length=512, blank=True, null=True)
    sequencekitbarcode = models.CharField(max_length=512, blank=True, null=True)
    librarykitname = models.CharField(max_length=512, blank=True, null=True)
    librarykitbarcode = models.CharField(max_length=512, blank=True, null=True)
    
    #for paired-end reverse run, separate library key and 3' adapter needed
    reverselibrarykey = models.CharField("library key for reverse run", max_length=64, blank=True, null=True)
    reverse3primeadapter = models.CharField("3' adapter for reverse run", max_length=512, blank=True, null=True)
    #for forward run, 3' adapter specific to this plan
    forward3primeadapter = models.CharField("3' adapter for forward run", max_length=512, blank=True, null=True)
    isReverseRun = models.BooleanField(default=False)
    
    #progress_flows = models.IntegerField(default=0)
    #progress_status = 

    #add metadata
    metaData = json_field.JSONField(blank=True)
   
    ALLOWED_RUN_MODES = (
        ('', 'Undefined'),                         
        ('single', 'SingleRead'),
        ('pe', 'PairedEnd')
    )

    #run mode
    runMode = models.CharField(max_length=64, choices=ALLOWED_RUN_MODES, default='', blank=True)
    
    #selected plan info
    selectedPlanGUID = models.CharField(max_length=512,blank=True,null=True)
    selectedPlanShortID = models.CharField(max_length=5,blank=True,null=True)

    # plan may be null because Experiments do not Have to have a plan
    # and it may be blank for the same reason.
    plan = models.ForeignKey(PlannedExperiment, blank=True, null=True)
    
    def __unicode__(self): return self.expName

    def runtype(self):
        return self.log.get("runtype","")

    def pretty_print(self):
        nodate = self.PRETTY_PRINT_RE.sub("", self.expName)
        ret = " ".join(nodate.split('_')).strip()
        if not ret:
            return nodate
        return ret

    def pretty_print_no_space(self):
        return self.pretty_print().replace(" ","_")

    def sorted_results(self):
        try:
            ret = self.results_set.all().order_by('-timeStamp')
        except IndexError:
            ret = None
        return ret
    def sorted_results_with_reports(self):
        """returns only results that have valid reports, in inverse time order"""
        try:
            ret = [r for r in self.results_set.all().order_by('-timeStamp') if r.report_exist()]
        except IndexError:
            ret = None
        return ret
    def get_storage_choices(self):
        return self.STORAGE_CHOICES
    def best_result(self, metric):
        try:
            rset = self.results_set.all()
            rset = rset.exclude(libmetrics__i50Q17_reads=0)
            rset = rset.exclude(libmetrics=None)
            rset = rset.order_by('-libmetrics__%s' % metric)[0]
        except IndexError:
            rset = None
        return rset
    def best_aq17(self):
        """best 100bp aq17 score"""
        rset = self.results_set.all()
        rset = rset.exclude(libmetrics=None)

        best_report = rset.order_by('-libmetrics__i100Q17_reads')
        sampled_best_report = rset.order_by('-libmetrics__extrapolated_100q17_reads')

        if not best_report and not sampled_best_report:
            return False

        best_report = best_report[0].libmetrics_set.all()[0].i100Q17_reads
        sampled_best_report = sampled_best_report[0].libmetrics_set.all()[0].extrapolated_100q17_reads

        if best_report > sampled_best_report:
            return rset.order_by('-libmetrics__i100Q17_reads')
        else:
            return rset.order_by('-libmetrics__extrapolated_100q17_reads')

    def available(self):
        try:
            backup = Backup.objects.get(backupName=self.expName)
        except:
            return False
        if backup.backupPath == 'DELETED':
            return 'Deleted'
        if backup.isBackedUp:
            return 'Archived'

    def save(self):
        """on save we need to sync up the log JSON and the other values that might have been set
        this was put in place primarily for the runtype field"""

        #Make sure that that pretty print name is saved as the display name for the experiment
        self.displayName = self.pretty_print()

        #we now save the library kit name instead of the kit's part number to Experiment
        #when updating a pre-existing run from TS, we want to populate the new field with the info
        if (self.librarykitbarcode and not self.librarykitname):
            try:
                selectedLibKitPart = KitPart.objects.get(barcode=self.librarykitbarcode)
                if (selectedLibKitPart):
                    selectedLibKit = selectedLibKitPart.kit
                    if (selectedLibKit):
                        self.librarykitname = selectedLibKit.name
            except KitPart.DoesNotExist:
                #If we can't determine the library kit name, leave it as is
                #do not fail the save()
                logger.info("NO kit part found at Experiment for libraryKitBarcode=%s" % self.librarykitbarcode)
                
        #we now save the sequencing kit name instead of the kit's part number to Experiment
        #when updating a pre-existing run from TS, we want to populate the new field with the info
        if ((self.sequencekitbarcode or self.seqKitBarcode) and not self.sequencekitname):
            try:
                kitBarcode = self.sequencekitbarcode
                if (not kitBarcode):
                    kitBarcode = self.seqKitBarcode

                selectedSeqKitPart = KitPart.objects.get(barcode=kitBarcode)
                if (selectedSeqKitPart):
                    selectedSeqKit = selectedSeqKitPart.kit
                    if (selectedSeqKit):
                        self.sequencekitname = selectedSeqKit.name
            except KitPart.DoesNotExist:
                #if we can't determine the seq kit name, leave it as is
                #do not fail the save()               
                logger.info("NO kit part found at Experiment for sequencingKitBarcode=%s" % kitBarcode)

        if self.isReverseRun:
            self.libraryKey = ""
            self.forward3primeadapter = ""
        else:
            self.reverselibrarykey = ""
            self.reverse3primeadapter = ""
        
        super(Experiment, self).save()


@receiver(post_delete, sender=Experiment, dispatch_uid="delete_experiment")
def on_experiment_delete(sender, instance, **kwargs):
    """Log the deletion of the Experiment.
    """
    logger.info("Deleting Experiment %d" % (instance.id))


class Lookup(object):
    _ALIASES = {}
    def lookup(self, path):
        def alias(e):
            key = e.lower().replace(' ', '')
            if key in self._ALIASES:
                return self._ALIASES[key]
            return e
        def down(obj, name):
            if not hasattr(obj, name):
                return None
            else:
                return getattr(obj, name)
        elements = path.split('.')
        curr = self
        for e in elements:
            if curr is None:
                break
            key = alias(e)
            curr = down(curr, key)
        return curr
    def tabulate(self, fields=None):
        if fields is None:
            fields = self.TABLE_FIELDS
        return [self.lookup(f) for f in fields]
    @classmethod
    def to_table(cls, qset):
        rows = [cls.TABLE_FIELDS]
        empty = ''
        for res in qset:
            rows.append([ele or empty for ele in res.tabulate()])
        return rows

class Results(models.Model, Lookup):
    _CSV_METRICS = (("Report", "resultsName"),
                    ("Status", 'status'),
                    ("Flows", 'processedflows'),
                    #("Plugin Data", 'pluginStore')
                    )
    _ALIASES = {
        "report":"resultsName",
        #"experiment":"experiment",
        "date":"timeStamp",
        "status":"status",
        "Flows":"processedflows",
        "q17mean":"best_metrics.Q17Mean",
        "q17mode":"best_metrics.Q17Mode",
        "systemsnr":"best_metrics.SysSNR",
        "q17reads":"best_metrics.Q17ReadCount",
        "keypass":"best_metrics.keypass",
        "cf":"best_metrics.CF"
        }
    TABLE_FIELDS = ("Report", "Status", "Flows",
                    "Lib Key Signal",
                     "Q20 Bases", "100 bp AQ20 Reads", "AQ20 Bases")
    PRETTY_FIELDS = TABLE_FIELDS
    experiment = models.ForeignKey(Experiment, related_name='results_set')
    representative = models.BooleanField(default=False)
    resultsName = models.CharField(max_length=512)
    timeStamp = models.DateTimeField(auto_now_add=True, db_index=True)
    sffLink = models.CharField(max_length=512)    #absolute paths
    fastqLink = models.CharField(max_length=512)  #absolute paths
    reportLink = models.CharField(max_length=512)  #absolute paths
    status = models.CharField(max_length=64)
    tfSffLink = models.CharField(max_length=512)    #absolute paths
    tfFastq = models.CharField(max_length=512)    #absolute paths
    log = models.TextField(blank=True)
    analysisVersion = models.CharField(max_length=256)
    processedCycles = models.IntegerField()
    processedflows = models.IntegerField()
    framesProcessed = models.IntegerField()
    timeToComplete = models.CharField(max_length=64)
    reportstorage = models.ForeignKey("ReportStorage", related_name="storage", blank=True, null=True)
    runid = models.CharField(max_length=10,blank=True)
    reportStatus = models.CharField(max_length=64, null=True, default="Nothing")
    autoExempt = models.BooleanField(default=False)
    
    projects = models.ManyToManyField(Project, related_name='results')
    # reference genome for alignment
    reference = models.CharField(max_length=64, blank=True, null=True)
    # a way to make Multi-Reports:
    resultsType = models.CharField(max_length=512, blank=True)
    #ids of parent reports separated by colon (e.g :1:32:3:)
    parentIDs = models.CharField(max_length=512, blank=True)
    
    #metaData
    metaData = json_field.JSONField(blank=True)


    def isProton(self):
        #protons
        proton = ["900"]
        if self.experiment.chipType in proton:
            return True
        else:
            return False

    #a place for plugins to store information
    # NB: These two functions facilitate compatibility with earlier model, 
    # which had pluginStore and pluginState as members
    #pluginStore = json_field.JSONField(blank=True)
    def getPluginStore(self):
        pluginDict = {}
        for p in self.pluginresult_set.all():
            pluginDict[p.plugin.name] = p.store
        #if not pluginDict:
        #    return None
        return pluginDict
    #pluginState = json_field.JSONField(blank=True)
    def getPluginState(self):
        pluginDict = {}
        for p in self.pluginresult_set.all():
            pluginDict[p.plugin.name] = p.state
        #if not pluginDict:
        #    return None
        return pluginDict

    def planShortID(self):
        expLog = self.experiment.log
        try:
            plan = expLog["planned_run_short_id"]
        except KeyError:
            plan = expLog.get("pending_run_short_id","")
        return plan

    def experimentReference(self):
        return self.experiment.library

    def projectNames(self):
      names = [p.name for p in self.projects.all().order_by('-modified')]      
      return ','.join(names)   

    def sffLinkPatch(self):
        return self.fastqLink.replace("fastq","sff")
        
    def sffTFLinkPatch(self):
        return self.fastqLink.replace("fastq","tf.sff")

    def bamLink(self):
        """a method to used by the API to provide a link to the bam file"""
        reportStorage = self._findReportStorage()
        location = self.server_and_location()

        if reportStorage is not None and location is not False:
            logging.info(reportStorage)
            logging.info(location)
            bamFile = self.experiment.expName + "_" + self.resultsName + ".bam"
            webPath = self.web_path(location)
            if not webPath:
                logging.error("webpath missing for " + bamFile)
                return False
            return os.path.join(webPath , bamFile)
        else:
            return False

    def reportWebLink(self):
        """a method to used get the web url with no fuss"""
        reportStorage = self._findReportStorage()
        location = self.server_and_location()

        if reportStorage is not None and location is not False:
            logging.info(reportStorage)
            logging.info(location)
            webPath = self.web_path(location)
            if not webPath:
                return False
            return webPath
        else:
            return False


    def verboseStatus(self):
        if self.status.lower() == "completed":
            return "The run analysis has completed"
        elif self.status.lower() == "error":
            return "The run analysis failed, Please check run log for specific error"
        elif self.status.lower() == "terminated":
            return "User terminated analysis job"
        elif self.status.lower() == "started":
            return "The analysis is currently processing"
        elif self.status.lower() == "checksum":
            return "One of the raw signal files (DAT) is corrupt. Try re-transferring the data from the PGM"
        elif self.status.lower() == "pgm operation error":
            return "Unexpected raw data values. Please check PGM for clogs or problems with chip"
        else:
            return self.status

    def _basename(self):
        return "%s_%03d" % (self.resultsName, self.pk)

    def server_and_location(self):
        try:
            loc = Rig.objects.get(name=self.experiment.pgmName).location
        except Rig.DoesNotExist:
            loc = Location.objects.filter(defaultlocation=True)
            if not loc:
                #if there is not a default, just take the first one
                loc = Location.objects.all().order_by('pk')
            if loc:
                loc = loc[0]
            else:
                return false    
        return loc

    def _findReportStorage(self):
        """
        Tries to determine the correct ReportStorage object by testing for
        a valid filesystem path using the reportLink path with the ReportStorage
        dirPath value.

        Algorithm for determining path from report link:
        strip off the first directory from report link and prepend the dirPath
        """
        storages = ReportStorage.objects.all()
        for storage in storages:
            tmpPath = self.reportLink.split('/')
            index = len(tmpPath) - 4
            linkstub = self.reportLink.split('/' + tmpPath[index])
            new_path = storage.dirPath + linkstub[1]
            if os.path.exists(new_path):
                return storage
        return None

    def web_root_path(self, location):
        """Returns filesystem path to Results directory"""
        basename = self._basename()
        if self.reportstorage == None:
            storage = self._findReportStorage()
            if storage is not None:
                self.reportstorage = storage
                self.save()
        if self.reportstorage is not None:
            return path.join(self.reportstorage.dirPath, location.name, basename)
        else:
            return None

    def report_exist(self):
        """check to see if a report exists inside of the report path"""
        fs_path = self.get_report_path()
        #TODO: is this operation slowing down page loading?  on thousands of reports?
        return os.path.exists(fs_path)

    def get_report_storage(self):
        """Returns reportstorage object"""
        if self.reportstorage == None:
            storage = self._findReportStorage()
            if storage is not None:
                self.reportstorage = storage
                self.save()
        return self.reportstorage

    def get_report_path(self):
        """Returns filesystem path to report file"""
        if self.reportstorage == None:
            storage = self._findReportStorage()
            if storage is not None:
                self.reportstorage = storage
                self.save()
        tmpPath = self.reportLink.split('/')
        index = len(tmpPath) - 4
        linkstub = self.reportLink.split('/' + tmpPath[index])
        if self.reportstorage is not None:
            return self.reportstorage.dirPath + linkstub[1]
        else:
            return None

    def get_report_dir(self):
        """Returns filesystem path to results directory"""
        fs_path = self.get_report_path()
        fs_path = path.split(fs_path)[0]
        return fs_path

    def web_path(self, location):
        basename = self._basename()
        if self.reportstorage == None:
            storage = self._findReportStorage()
            if storage is not None:
                self.reportstorage = storage
                self.save()
        webServerPath = path.join(self.reportstorage.webServerPath, location.name, basename)

        #TODO: the webpath is not the same as the path of the filesystem. Check the webpath somehow.
        return webServerPath

    def __unicode__(self):
        return self.resultsName

    def updateMetaData(self, status, info, size, comment, logger = None):
        retLog = logger
        self.reportStatus = status
        self.save()
        
        if retLog:
            retLog.info(self.resultsName+": Status: "+status+" | Info: "+info + " | Comments: %s"%comment)
            # This string is parsed when calculating disk space saved:
            if size > 0: retLog.info(self.resultsName+": Size saved:* %7.2f KB"%(float(size/1024)))
        
        self.metaData["Status"] = status
        self.metaData["Date"] = "%s"%datetime.datetime.now()
        self.metaData["Info"] = info
        self.metaData["Comment"] = comment
        
        # Try to read the Log entry, if it does not exist, create it
        if len(self.metaData.get("Log",[])) == 0:
            self.metaData["Log"] = []
        self.metaData["Log"].append({"Status":self.metaData.get("Status"), "Date":self.metaData.get("Date"), "Info":self.metaData.get("Info"), "Comment":comment})
        self.save()
         
    # TODO: Cycles -> flows hack, very temporary.
    @property
    def processedFlowsorCycles(self):
        """This is an extremely intermediate hack, holding down the fort until
        cycles are removed from the model.
        """
        if self.processedflows:
            return self.processedflows
        else:
            return self.processedCycles * 4

    @property
    def best_metrics(self):
        try:
            ret = self.tfmetrics_set.all().order_by('-Q17Mean')[0]
        except IndexError:
            ret = None
        return ret
    @property
    def best_lib_metrics(self):
        try:
            ret = self.libmetrics_set.all().order_by('-i50Q17_reads')[0]
        except IndexError:
            ret = None
        return ret
    def best_lib_by_value(self, metric):
        try:
            ret = self.libmetrics_set.all().order_by('-%s' % metric)[0]
        except IndexError:
            ret = None
        return ret
    def pretty_tabulate(self):
        try:
            frags = self.tfmetrics_set.all().exclude(CF=0, IE=0, DR=0).order_by('name')
            return frags
        except:
            import traceback
            traceback.print_exc()
    def best_metrics_tabulate(self):
        return [self.lookup(f) for f in self.best_metrics_headings()]
    @classmethod
    def best_metrics_headings(cls):
        return cls.TABLE_FIELDS

    @classmethod
    def get_lib_metrics(cls, obj, metrics):
        q = obj.libmetrics_set.all()
        ret = []
        if len(q) > 0:
            for i in q:
                for metric in metrics:
                    ret.append(getattr(i, metric))
        else:
            for metrics in metrics:
                ret.append(' ')
        return tuple(ret)

    @classmethod
    def get_exp_metrics(cls, obj, metrics):
        q = obj.experiment
        ret = []
        for metric in metrics:
            ret.append(getattr(q, metric))
        return ret

    @classmethod
    def get_analysis_metrics(cls, obj, metrics):
        q = obj.analysismetrics_set.all()
        ret = []
        if len(q) > 0:
            for i in q:
                for metric in metrics:
                    ret.append(getattr(i, metric))
        else:
            for metrics in metrics:
                ret.append(' ')
        return tuple(ret)
    @classmethod
    def get_tf_metrics(cls, obj, metrics):
        q = obj.tfmetrics_set.all()
        ret = []
        if len(q) > 0:
            for i in q:
                s = cls.get_result_metrics(obj, cls.get_values(cls._CSV_METRICS))
                for metric in metrics:
                    s.append(getattr(i, metric))
                ret.append(s)
        else:
            s = cls.get_result_metrics(obj, cls.get_values(cls._CSV_METRICS))
            for metric in metrics:
                s.append(' ')
            ret.append(s)
        return ret
    @classmethod
    def get_result_metrics(cls, obj, metrics):
        ret = []
        for metric in metrics:
            try:
                ret.append(getattr(obj, metric))
            except:
                ret.append(' ')
        return ret
    @classmethod
    def get_plugin_metrics(cls, obj, metrics):
        q = obj.pluginresult_set.all()
        ret = []
        if len(q) > 0:
            for i in q:
                try:
                    ret.append(json.dumps({i.plugin.name: i.store }))
                except TypeError:
                    #there are some hosts which had bad results.json in the past. Skip pumping that data out
                    pass
        return tuple(ret)

    @classmethod
    def getNameFromTable(cls, metrics):
        ret = []
        for k, v in metrics.iteritems():
            ret.append(k)
        return tuple(ret)
    @classmethod
    def get_values(cls, listotuple):
        values = []
        for ele in listotuple:
            values.append(ele[1])
        return tuple(values)
    @classmethod
    def get_keys(csl, listotuple):
        keys = []
        for ele in listotuple:
            keys.append(ele[0])
        return tuple(keys)
    @classmethod
    def to_pretty_table(cls, qset):
        ret = [cls.get_keys(cls._CSV_METRICS)
               + cls.get_keys(TFMetrics._CSV_METRICS)
               + cls.get_keys(LibMetrics._CSV_METRICS)
               + cls.get_keys(Experiment._CSV_METRICS)
               + cls.get_keys(AnalysisMetrics._CSV_METRICS)
               + cls.get_keys(PluginResult._CSV_METRICS)
               ]
        for obj in qset:
            new = cls.get_tf_metrics(obj, cls.get_values(TFMetrics._CSV_METRICS))
            if len(new) > 0:
                new[0].extend(cls.get_lib_metrics(obj, cls.get_values(LibMetrics._CSV_METRICS)))
                new[0].extend(cls.get_exp_metrics(obj, cls.get_values(Experiment._CSV_METRICS)))
                new[0].extend(cls.get_analysis_metrics(obj, cls.get_values(AnalysisMetrics._CSV_METRICS)))
                new[0].extend(cls.get_plugin_metrics(obj, cls.get_values(PluginResult._CSV_METRICS)))
            ret.extend(new)
        return ret
    class Meta:
        verbose_name_plural = "Results"


@receiver(post_save, sender=Results, dispatch_uid="create_result")
def on_result_created(sender, instance, created, **kwargs):
    if created:
        experiment = instance.experiment
        experiment.resultDate = instance.timeStamp
        experiment.save()


@receiver(post_delete, sender=Results, dispatch_uid="delete_result")
def on_result_delete(sender, instance, **kwargs):
    """Delete all of the files represented by a Experiment object which was
    deleted and all of files derived from that Experiment which are in it's
    folder.
    """
    # Note, this completely sucks: is there a better way of determining this?
    root = instance.reportstorage.dirPath
    prefix = len(instance.reportstorage.webServerPath)
    postfix = os.path.dirname(instance.reportLink[prefix+1:])
    directory = os.path.join(root, postfix)
    logger.info("Deleting Result %d in %s" % (instance.id, directory))
    tasks.delete_that_folder.delay(directory,
                       "Triggered by Results %d deletion" % instance.id)

class TFMetrics(models.Model, Lookup):
    _CSV_METRICS = (
        ("TF Name", "name"),
        ("Q10 Mean", "Q10Mean"),
        ("Q17 Mean", "Q17Mean"),
        ("Q10 Mode", "Q10Mode"),
        ("Q17 Mode", "Q17Mode"),
        ("System SNR", "SysSNR"),
        ("50Q10 Reads", "Q10ReadCount"),
        ("50Q17 Reads", "Q17ReadCount"),
        ("Keypass Reads", "keypass"),
        ("CF", "CF"),
        ("IE", "IE"),
        ("DR", "DR"),
        ("TF Key Peak Counts", 'aveKeyCount'),
        )
    _ALIASES = {
        "tfname":"name",
        "q17mean":"Q17Mean",
        "q17mode":"Q17Mode",
        "systemsnr":"SysSNR",
        "50q17reads":"Q17ReadCount",
        "keypassreads": "keypass",
        "CF":"cf",
        "IE":"ie",
        "DR":"dr",
        "tfkeypeakcounts":'aveKeyCount'
        }
    TABLE_FIELDS = ("TF Name", "Q17 Mean", "Q17 Mode",
                    "System SNR", "50Q17 Reads", "Keypass Reads",
                    "CF", "IE", "DR", " TF Key Peak Counts")
    report = models.ForeignKey(Results, db_index=True, related_name='tfmetrics_set')
    name = models.CharField(max_length=128, db_index=True)
    matchMismatchHisto = models.TextField(blank=True)
    matchMismatchMean = models.FloatField()
    matchMismatchMode = models.FloatField()
    Q10Histo = models.TextField(blank=True)
    Q10Mean = models.FloatField()
    Q10Mode = models.FloatField()
    Q17Histo = models.TextField(blank=True)
    Q17Mean = models.FloatField()
    Q17Mode = models.FloatField()
    SysSNR = models.FloatField()
    HPSNR = models.TextField(blank=True)
    corrHPSNR = models.TextField(blank=True)
    HPAccuracy = models.TextField(blank=True)
    rawOverlap = models.TextField(blank=True)
    corOverlap = models.TextField(blank=True)
    hqReadCount = models.FloatField()
    aveHqReadCount = models.FloatField()
    Q10ReadCount = models.FloatField()
    aveQ10ReadCount = models.FloatField()
    Q17ReadCount = models.FloatField()
    aveQ17ReadCount = models.FloatField()
    sequence = models.CharField(max_length=512)#ambitious
    keypass = models.FloatField()
    preCorrSNR = models.FloatField()
    postCorrSNR = models.FloatField()
    ####CAFIE#####
    rawIonogram = models.TextField(blank=True)
    corrIonogram = models.TextField(blank=True)
    CF = models.FloatField()
    IE = models.FloatField()
    DR = models.FloatField()
    error = models.FloatField()
    number = models.FloatField()
    aveKeyCount = models.FloatField()
    def __unicode__(self):
        return "%s/%s" % (self.report, self.name)

    def get_csv_metrics(self):
        ret = []
        for metric in self._CSV_METRICS:
            ret.append((metric[0], getattr(self, metric[1], ' ')))

    class Meta:
        verbose_name_plural = "TF metrics"

class Location(models.Model):
    name = models.CharField(max_length=200)
    comments = models.TextField(blank=True)
    defaultlocation = models.BooleanField("Set as the Default Location",default=False,help_text="Only one location can be the default")

    def __unicode__(self):
        return u'%s' % self.name

    def save(self, *args, **kwargs):
        """make sure only one location is checked."""
        super(Location, self).save(*args, **kwargs)
        if self.defaultlocation:
            # If self is marked as default, mark all others as not default
            others = Location.objects.all().exclude(name=self.name)
            for other in others:
                other.defaultlocation = False
                super(Location, other).save(*args, **kwargs)


class Rig(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    location = models.ForeignKey(Location)
    comments = models.TextField(blank=True)
    ftpserver	 = models.CharField(max_length=128, default="192.168.201.1")
    ftpusername	 = models.CharField(max_length=64, default="ionguest")
    ftppassword	 = models.CharField(max_length=64, default="ionguest")
    ftprootdir	 = models.CharField(max_length=64, default="results")
    updatehome	 = models.CharField(max_length=256, default="192.168.201.1")
    updateflag = models.BooleanField(default=False)
    serial = models.CharField(max_length=24, blank=True, null=True)

    state = models.CharField(max_length=512, blank=True)
    version = json_field.JSONField(blank=True)
    alarms = json_field.JSONField(blank=True)
    last_init_date = models.CharField(max_length=512, blank=True)
    last_clean_date = models.CharField(max_length=512, blank=True)
    last_experiment = models.CharField(max_length=512, blank=True)


    def __unicode__(self): return self.name

class FileServer(models.Model):
    name = models.CharField(max_length=200)
    comments = models.TextField(blank=True)
    filesPrefix = models.CharField(max_length=200)
    location = models.ForeignKey(Location)
    percentfull = models.FloatField(default=0.0,blank=True,null=True)
    def __unicode__(self): return self.name

class ReportStorage(models.Model):
    name = models.CharField(max_length=200)
    #path to webserver as http://localhost/results/
    webServerPath = models.CharField(max_length=200)
    dirPath = models.CharField(max_length=200)
    default=models.BooleanField(default=False)
    def __unicode__(self):
        return "%s (%s)" % (self.name, self.dirPath)

    def save(self, *args, **kwargs):
        """make sure only one object is checked."""
        super(ReportStorage, self).save(*args, **kwargs)
        if self.default:
            # If self is marked as default, mark all others as not default
            others = ReportStorage.objects.all().exclude(name=self.name)
            for other in others:
                other.default = False
                super(ReportStorage, other).save(*args, **kwargs)

class RunScript(models.Model):
    name = models.CharField(max_length=200)
    script = models.TextField(blank=True)
    def __unicode__(self):
        return self.name

class Cruncher(models.Model):
    name = models.CharField(max_length=200)
    prefix = models.CharField(max_length=512)
    location = models.ForeignKey(Location)
    comments = models.TextField(blank=True)
    def __unicode__(self): return self.name

class AnalysisMetrics(models.Model):
    _CSV_METRICS = (('Num_Washouts', 'washout'),
                    ('Num_Dud_Washouts', 'washout_dud'),
                    ('Num_Washout_Ambiguous', 'washout_ambiguous'),
                    ('Num_Washout_Live', 'washout_live'),
                    ('Num_Washout_Test_Fragment', 'washout_test_fragment'),
                    ('Num_Washout_Library', 'washout_library'),
                    ('Library_Pass_Basecalling', 'lib_pass_basecaller'),
                    ('Library_pass_Cafie', 'lib_pass_cafie'),
                    ('Number_Ambiguous', 'amb'),
                    ('Nubmer_Live', 'live'),
                    ('Number_Dud', 'dud'),
                    ('Number_TF', 'tf'),
                    ('Number_Lib', 'lib'),
                    ('Number_Bead', 'bead'),
                    ('Library_Live', 'libLive'),
                    ('Library_Keypass', 'libKp'),
                    ('TF_Live', 'live'),
                    ('TF_Keypass', 'tfKp'),
                    ('Keypass_All_Beads', 'keypass_all_beads'),
                    )
    report = models.ForeignKey(Results, related_name='analysismetrics_set')
    libLive = models.IntegerField()
    libKp = models.IntegerField()
    libMix = models.IntegerField()
    libFinal = models.IntegerField()
    tfLive = models.IntegerField()
    tfKp = models.IntegerField()
    tfMix = models.IntegerField()
    tfFinal = models.IntegerField()
    empty = models.IntegerField()
    bead = models.IntegerField()
    live = models.IntegerField()
    dud = models.IntegerField()
    amb = models.IntegerField()
    tf = models.IntegerField()
    lib = models.IntegerField()
    pinned = models.IntegerField()
    ignored = models.IntegerField()
    excluded = models.IntegerField()
    washout = models.IntegerField()
    washout_dud = models.IntegerField()
    washout_ambiguous = models.IntegerField()
    washout_live = models.IntegerField()
    washout_test_fragment = models.IntegerField()
    washout_library = models.IntegerField()
    lib_pass_basecaller = models.IntegerField()
    lib_pass_cafie = models.IntegerField()
    keypass_all_beads = models.IntegerField()
    sysCF = models.FloatField()
    sysIE = models.FloatField()
    sysDR = models.FloatField()
    def __unicode__(self):
        return "%s/%d" % (self.report, self.pk)
    class Meta:
        verbose_name_plural = "Analysis metrics"

class LibMetrics(models.Model):
    _CSV_METRICS = (('Total_Num_Reads', 'totalNumReads'),
                    ('Library_50Q10_Reads', 'i50Q10_reads'),
                    ('Library_100Q10_Reads', 'i100Q10_reads'),
                    ('Library_200Q10_Reads', 'i200Q10_reads'),
                    ('Library_Mean_Q10_Length', 'q10_mean_alignment_length'),
                    ('Library_Q10_Coverage', 'q10_coverage_percentage'),
                    ('Library_Q10_Longest_Alignment', 'q10_longest_alignment'),
                    ('Library_Q10_Mapped Bases', 'q10_mapped_bases'),
                    ('Library_Q10_Alignments', 'q10_alignments'),
                    ('Library_50Q17_Reads', 'i50Q17_reads'),
                    ('Library_100Q17_Reads', 'i100Q17_reads'),
                    ('Library_200Q17_Reads', 'i200Q17_reads'),
                    ('Library_Mean_Q17_Length', 'q17_mean_alignment_length'),
                    ('Library_Q17_Coverage', 'q17_coverage_percentage'),
                    ('Library_Q17_Longest_Alignment', 'q17_longest_alignment'),
                    ('Library_Q17_Mapped Bases', 'q17_mapped_bases'),
                    ('Library_Q17_Alignments', 'q17_alignments'),
                    ('Library_50Q20_Reads', 'i50Q20_reads'),
                    ('Library_100Q20_Reads', 'i100Q20_reads'),
                    ('Library_200Q20_Reads', 'i200Q20_reads'),
                    ('Library_Mean_Q20_Length', 'q20_mean_alignment_length'),
                    ('Library_Q20_Coverage', 'q20_coverage_percentage'),
                    ('Library_Q20_Longest_Alignment', 'q20_longest_alignment'),
                    ('Library_Q20_Mapped Bases', 'q20_mapped_bases'),
                    ('Library_Q20_Alignments', 'q20_alignments'),
                    ('Library_Key_Peak_Counts', 'aveKeyCounts'),
                    ('Library_50Q47_Reads', 'i50Q47_reads'),
                    ('Library_100Q47_Reads', 'i100Q47_reads'),
                    ('Library_200Q47_Reads', 'i200Q47_reads'),
                    ('Library_Mean_Q47_Length', 'q47_mean_alignment_length'),
                    ('Library_Q47_Coverage', 'q47_coverage_percentage'),
                    ('Library_Q47_Longest_Alignment', 'q47_longest_alignment'),
                    ('Library_Q47_Mapped Bases', 'q47_mapped_bases'),
                    ('Library_Q47_Alignments', 'q47_alignments'),
                    ('Library_CF', 'cf'),
                    ('Library_IE', 'ie'),
                    ('Library_DR', 'dr'),
                    ('Library_SNR', 'sysSNR'),
                    )
    report = models.ForeignKey(Results, db_index=True, related_name='libmetrics_set')
    sysSNR = models.FloatField()
    aveKeyCounts = models.FloatField()
    totalNumReads = models.IntegerField()
    genomelength = models.IntegerField()
    rNumAlignments = models.IntegerField()
    rMeanAlignLen = models.IntegerField()
    rLongestAlign = models.IntegerField()
    rCoverage = models.FloatField()
    r50Q10 = models.IntegerField()
    r100Q10 = models.IntegerField()
    r200Q10 = models.IntegerField()
    r50Q17 = models.IntegerField()
    r100Q17 = models.IntegerField()
    r200Q17 = models.IntegerField()
    r50Q20 = models.IntegerField()
    r100Q20 = models.IntegerField()
    r200Q20 = models.IntegerField()
    sNumAlignments = models.IntegerField()
    sMeanAlignLen = models.IntegerField()
    sLongestAlign = models.IntegerField()
    sCoverage = models.FloatField()
    s50Q10 = models.IntegerField()
    s100Q10 = models.IntegerField()
    s200Q10 = models.IntegerField()
    s50Q17 = models.IntegerField()
    s100Q17 = models.IntegerField()
    s200Q17 = models.IntegerField()
    s50Q20 = models.IntegerField()
    s100Q20 = models.IntegerField()
    s200Q20 = models.IntegerField()

    q7_coverage_percentage = models.FloatField()
    q7_alignments = models.IntegerField()
    q7_mapped_bases = models.BigIntegerField()
    q7_qscore_bases = models.BigIntegerField()
    q7_mean_alignment_length = models.IntegerField()
    q7_longest_alignment = models.IntegerField()
    i50Q7_reads = models.IntegerField()
    i100Q7_reads = models.IntegerField()
    i150Q7_reads = models.IntegerField()
    i200Q7_reads = models.IntegerField()
    i250Q7_reads = models.IntegerField()
    i300Q7_reads = models.IntegerField()
    i350Q7_reads = models.IntegerField()
    i400Q7_reads = models.IntegerField()
    i450Q7_reads = models.IntegerField()
    i500Q7_reads = models.IntegerField()
    i550Q7_reads = models.IntegerField()
    i600Q7_reads = models.IntegerField()

    q10_coverage_percentage = models.FloatField()
    q10_alignments = models.IntegerField()
    q10_mapped_bases = models.BigIntegerField()
    q10_qscore_bases = models.BigIntegerField()
    q10_mean_alignment_length = models.IntegerField()
    q10_longest_alignment = models.IntegerField()
    i50Q10_reads = models.IntegerField()
    i100Q10_reads = models.IntegerField()
    i150Q10_reads = models.IntegerField()
    i200Q10_reads = models.IntegerField()
    i250Q10_reads = models.IntegerField()
    i300Q10_reads = models.IntegerField()
    i350Q10_reads = models.IntegerField()
    i400Q10_reads = models.IntegerField()
    i450Q10_reads = models.IntegerField()
    i500Q10_reads = models.IntegerField()
    i550Q10_reads = models.IntegerField()
    i600Q10_reads = models.IntegerField()

    q17_coverage_percentage = models.FloatField()
    q17_alignments = models.IntegerField()
    q17_mapped_bases = models.BigIntegerField()
    q17_qscore_bases = models.BigIntegerField()
    q17_mean_alignment_length = models.IntegerField()
    q17_longest_alignment = models.IntegerField()
    i50Q17_reads = models.IntegerField()
    i100Q17_reads = models.IntegerField()
    i150Q17_reads = models.IntegerField()
    i200Q17_reads = models.IntegerField()
    i250Q17_reads = models.IntegerField()
    i300Q17_reads = models.IntegerField()
    i350Q17_reads = models.IntegerField()
    i400Q17_reads = models.IntegerField()
    i450Q17_reads = models.IntegerField()
    i500Q17_reads = models.IntegerField()
    i550Q17_reads = models.IntegerField()
    i600Q17_reads = models.IntegerField()

    q20_coverage_percentage = models.FloatField()
    q20_alignments = models.IntegerField()
    q20_mapped_bases = models.BigIntegerField()
    q20_qscore_bases = models.BigIntegerField()
    q20_mean_alignment_length = models.IntegerField()
    q20_longest_alignment = models.IntegerField()
    i50Q20_reads = models.IntegerField()
    i100Q20_reads = models.IntegerField()
    i150Q20_reads = models.IntegerField()
    i200Q20_reads = models.IntegerField()
    i250Q20_reads = models.IntegerField()
    i300Q20_reads = models.IntegerField()
    i350Q20_reads = models.IntegerField()
    i400Q20_reads = models.IntegerField()
    i450Q20_reads = models.IntegerField()
    i500Q20_reads = models.IntegerField()
    i550Q20_reads = models.IntegerField()
    i600Q20_reads = models.IntegerField()

    q47_coverage_percentage = models.FloatField()
    q47_mapped_bases = models.BigIntegerField()
    q47_qscore_bases = models.BigIntegerField()
    q47_alignments = models.IntegerField()
    q47_mean_alignment_length = models.IntegerField()
    q47_longest_alignment = models.IntegerField()
    i50Q47_reads = models.IntegerField()
    i100Q47_reads = models.IntegerField()
    i150Q47_reads = models.IntegerField()
    i200Q47_reads = models.IntegerField()
    i250Q47_reads = models.IntegerField()
    i300Q47_reads = models.IntegerField()
    i350Q47_reads = models.IntegerField()
    i400Q47_reads = models.IntegerField()
    i450Q47_reads = models.IntegerField()
    i500Q47_reads = models.IntegerField()
    i550Q47_reads = models.IntegerField()
    i600Q47_reads = models.IntegerField()

    cf = models.FloatField()
    ie = models.FloatField()
    dr = models.FloatField()
    Genome_Version = models.CharField(max_length=512)
    Index_Version = models.CharField(max_length=512)
    #lots of additional fields in the case that only a sampled+extrapolated alignment is done
    #first add a int to let me know if it is full of sampled align
    align_sample = models.IntegerField()
    genome = models.CharField(max_length=512)
    genomesize = models.BigIntegerField()
    total_number_of_sampled_reads = models.IntegerField()
    sampled_q7_coverage_percentage = models.FloatField()
    sampled_q7_mean_coverage_depth = models.FloatField()
    sampled_q7_alignments = models.IntegerField()
    sampled_q7_mean_alignment_length = models.IntegerField()
    sampled_mapped_bases_in_q7_alignments = models.BigIntegerField()
    sampled_q7_longest_alignment = models.IntegerField()
    sampled_50q7_reads = models.IntegerField()
    sampled_100q7_reads = models.IntegerField()
    sampled_200q7_reads = models.IntegerField()
    sampled_300q7_reads = models.IntegerField()
    sampled_400q7_reads = models.IntegerField()
    sampled_q10_coverage_percentage = models.FloatField()
    sampled_q10_mean_coverage_depth = models.FloatField()
    sampled_q10_alignments = models.IntegerField()
    sampled_q10_mean_alignment_length = models.IntegerField()
    sampled_mapped_bases_in_q10_alignments = models.BigIntegerField()
    sampled_q10_longest_alignment = models.IntegerField()
    sampled_50q10_reads = models.IntegerField()
    sampled_100q10_reads = models.IntegerField()
    sampled_200q10_reads = models.IntegerField()
    sampled_300q10_reads = models.IntegerField()
    sampled_400q10_reads = models.IntegerField()
    sampled_q17_coverage_percentage = models.FloatField()
    sampled_q17_mean_coverage_depth = models.FloatField()
    sampled_q17_alignments = models.IntegerField()
    sampled_q17_mean_alignment_length = models.IntegerField()
    sampled_mapped_bases_in_q17_alignments = models.BigIntegerField()
    sampled_q17_longest_alignment = models.IntegerField()
    sampled_50q17_reads = models.IntegerField()
    sampled_100q17_reads = models.IntegerField()
    sampled_200q17_reads = models.IntegerField()
    sampled_300q17_reads = models.IntegerField()
    sampled_400q17_reads = models.IntegerField()
    sampled_q20_coverage_percentage = models.FloatField()
    sampled_q20_mean_coverage_depth = models.FloatField()
    sampled_q20_alignments = models.IntegerField()
    sampled_q20_mean_alignment_length = models.IntegerField()
    sampled_mapped_bases_in_q20_alignments = models.BigIntegerField()
    sampled_q20_longest_alignment = models.IntegerField()
    sampled_50q20_reads = models.IntegerField()
    sampled_100q20_reads = models.IntegerField()
    sampled_200q20_reads = models.IntegerField()
    sampled_300q20_reads = models.IntegerField()
    sampled_400q20_reads = models.IntegerField()
    sampled_q47_coverage_percentage = models.FloatField()
    sampled_q47_mean_coverage_depth = models.FloatField()
    sampled_q47_alignments = models.IntegerField()
    sampled_q47_mean_alignment_length = models.IntegerField()
    sampled_mapped_bases_in_q47_alignments = models.BigIntegerField()
    sampled_q47_longest_alignment = models.IntegerField()
    sampled_50q47_reads = models.IntegerField()
    sampled_100q47_reads = models.IntegerField()
    sampled_200q47_reads = models.IntegerField()
    sampled_300q47_reads = models.IntegerField()
    sampled_400q47_reads = models.IntegerField()
    extrapolated_from_number_of_sampled_reads = models.IntegerField()
    extrapolated_q7_coverage_percentage = models.FloatField()
    extrapolated_q7_mean_coverage_depth = models.FloatField()
    extrapolated_q7_alignments = models.IntegerField()
    extrapolated_q7_mean_alignment_length = models.IntegerField()
    extrapolated_mapped_bases_in_q7_alignments = models.BigIntegerField()
    extrapolated_q7_longest_alignment = models.IntegerField()
    extrapolated_50q7_reads = models.IntegerField()
    extrapolated_100q7_reads = models.IntegerField()
    extrapolated_200q7_reads = models.IntegerField()
    extrapolated_300q7_reads = models.IntegerField()
    extrapolated_400q7_reads = models.IntegerField()
    extrapolated_q10_coverage_percentage = models.FloatField()
    extrapolated_q10_mean_coverage_depth = models.FloatField()
    extrapolated_q10_alignments = models.IntegerField()
    extrapolated_q10_mean_alignment_length = models.IntegerField()
    extrapolated_mapped_bases_in_q10_alignments = models.BigIntegerField()
    extrapolated_q10_longest_alignment = models.IntegerField()
    extrapolated_50q10_reads = models.IntegerField()
    extrapolated_100q10_reads = models.IntegerField()
    extrapolated_200q10_reads = models.IntegerField()
    extrapolated_300q10_reads = models.IntegerField()
    extrapolated_400q10_reads = models.IntegerField()
    extrapolated_q17_coverage_percentage = models.FloatField()
    extrapolated_q17_mean_coverage_depth = models.FloatField()
    extrapolated_q17_alignments = models.IntegerField()
    extrapolated_q17_mean_alignment_length = models.IntegerField()
    extrapolated_mapped_bases_in_q17_alignments = models.BigIntegerField()
    extrapolated_q17_longest_alignment = models.IntegerField()
    extrapolated_50q17_reads = models.IntegerField()
    extrapolated_100q17_reads = models.IntegerField()
    extrapolated_200q17_reads = models.IntegerField()
    extrapolated_300q17_reads = models.IntegerField()
    extrapolated_400q17_reads = models.IntegerField()
    extrapolated_q20_coverage_percentage = models.FloatField()
    extrapolated_q20_mean_coverage_depth = models.FloatField()
    extrapolated_q20_alignments = models.IntegerField()
    extrapolated_q20_mean_alignment_length = models.IntegerField()
    extrapolated_mapped_bases_in_q20_alignments = models.BigIntegerField()
    extrapolated_q20_longest_alignment = models.IntegerField()
    extrapolated_50q20_reads = models.IntegerField()
    extrapolated_100q20_reads = models.IntegerField()
    extrapolated_200q20_reads = models.IntegerField()
    extrapolated_300q20_reads = models.IntegerField()
    extrapolated_400q20_reads = models.IntegerField()
    extrapolated_q47_coverage_percentage = models.FloatField()
    extrapolated_q47_mean_coverage_depth = models.FloatField()
    extrapolated_q47_alignments = models.IntegerField()
    extrapolated_q47_mean_alignment_length = models.IntegerField()
    extrapolated_mapped_bases_in_q47_alignments = models.BigIntegerField()
    extrapolated_q47_longest_alignment = models.IntegerField()
    extrapolated_50q47_reads = models.IntegerField()
    extrapolated_100q47_reads = models.IntegerField()
    extrapolated_200q47_reads = models.IntegerField()
    extrapolated_300q47_reads = models.IntegerField()
    extrapolated_400q47_reads = models.IntegerField()

    def __unicode__(self):
        return "%s/%d" % (self.report, self.pk)
    class Meta:
        verbose_name_plural = "Lib Metrics"

class QualityMetrics(models.Model):
    """a place in the database to store the quality metrics from SFFSumary"""
    #make csv metrics lookup here
    report = models.ForeignKey(Results, db_index=True, related_name='qualitymetrics_set')
    q0_bases = models.BigIntegerField()
    q0_reads = models.IntegerField()
    q0_max_read_length = models.IntegerField()
    q0_mean_read_length = models.FloatField()
    q0_50bp_reads = models.IntegerField()
    q0_100bp_reads = models.IntegerField()
    q0_15bp_reads = models.IntegerField()
    q17_bases = models.BigIntegerField()
    q17_reads = models.IntegerField()
    q17_max_read_length = models.IntegerField()
    q17_mean_read_length = models.FloatField()
    q17_50bp_reads = models.IntegerField()
    q17_100bp_reads = models.IntegerField()
    q17_150bp_reads = models.IntegerField()
    q20_bases = models.BigIntegerField()
    q20_reads = models.IntegerField()
    q20_max_read_length = models.FloatField()
    q20_mean_read_length = models.IntegerField()
    q20_50bp_reads = models.IntegerField()
    q20_100bp_reads = models.IntegerField()
    q20_150bp_reads = models.IntegerField()

    def __unicode__(self):
        return "%s/%d" % (self.report, self.pk)
    class Meta:
        verbose_name_plural = "Quality Metrics"

class Template(models.Model):
    name = models.CharField(max_length=64)
    sequence = models.TextField(blank=True)
    key = models.CharField(max_length=64)
    comments = models.TextField(blank=True)
    isofficial = models.BooleanField(default=True)
    def __unicode__(self):
        return self.name

class Backup(models.Model):
    experiment = models.ForeignKey(Experiment)
    backupName = models.CharField(max_length=256, unique=True)
    isBackedUp = models.BooleanField()
    backupDate = models.DateTimeField()
    backupPath = models.CharField(max_length=512)
    def __unicode__(self):
        return u'%s' % self.experiment

class BackupConfig(models.Model):
    name = models.CharField(max_length=64)
    location = models.ForeignKey(Location)
    backup_directory = models.CharField(max_length=256, blank=True, default=None)
    backup_threshold = models.IntegerField(blank=True)
    number_to_backup = models.IntegerField(blank=True)
    grace_period = models.IntegerField(default=72)
    timeout = models.IntegerField(blank=True)
    bandwidth_limit = models.IntegerField(blank=True)
    status = models.CharField(max_length=512, blank=True)
    online = models.BooleanField()
    comments = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    def __unicode__(self):
        return self.name

    def get_free_space(self):
        dev = devices.disk_report()
        for d in dev:
            if self.backup_directory == d.get_path():
                return d.get_free_space()

    def check_if_online(self):
        if path.exists(self.backup_directory):
            return True
        else:
            return False

class dm_reports(models.Model):
    '''This object holds the options for report actions.
    Which level(s) to prune at, what those levels are, how far back to look when recording space saved, etc.'''
    location = models.CharField(max_length=512)
    pruneLevel = models.CharField(max_length=128, default = 'No-op')    #FRAGILE: requires dm_prune_group.name == "No-op"
    autoPrune = models.BooleanField(default = False)
    autoType = models.CharField(max_length=32, default = 'P')
    autoAge = models.IntegerField(default=90)
    class Meta:
        verbose_name_plural = "DM - Configuration"
        
    def __unicode__(self):
        return self.location

class dm_prune_group(models.Model):
    name = models.CharField(max_length=128, default="")
    editable = models.BooleanField(default=True)    # This actually signifies "deletable by customer"
    ruleNums = models.CommaSeparatedIntegerField(max_length=128, default='', blank = True)
    class Meta:
        verbose_name_plural = "DM - Prune Groups"
        
    def __unicode__(self):
        return self.name
    
class dm_prune_field(models.Model):
    rule = models.CharField(max_length=64, default = "")
    class Meta:
        verbose_name_plural = "DM - Prune Rules"

class Chip(models.Model):
    name = models.CharField(max_length=128)
    slots = models.IntegerField()
    args = models.CharField(max_length=512, blank=True)
    description = models.CharField(max_length=128, default="")
    
    def getChipDisplayedName(self):
        if self.description:
            return self.description;
        else:
            return self.name;
        
    
class GlobalConfig(models.Model):
    name = models.CharField(max_length=512)
    selected = models.BooleanField()
    plugin_folder = models.CharField(max_length=512, blank=True)

    #Analysis args
    default_command_line = models.CharField(max_length=512, blank=True, verbose_name="Analysis args")
    #Basecaller args
    basecallerargs = models.CharField(max_length=512, blank=True, verbose_name="Basecaller args")

    #Analysis Thumbnail args
    analysisthumbnailargs= models.CharField(max_length=5000, blank=True, verbose_name="Thumbnail Analysis args")

    #Basecaller Thumbnail args
    basecallerthumbnailargs= models.CharField(max_length=5000, blank=True, verbose_name="Thumbnail Basecaller args")

    fasta_path = models.CharField(max_length=512, blank=True)
    reference_path = models.CharField(max_length=1000, blank=True)
    records_to_display = models.IntegerField(default=20, blank=True)
    default_test_fragment_key = models.CharField(max_length=50, blank=True)
    default_library_key = models.CharField(max_length=50, blank=True)
    default_flow_order = models.CharField(max_length=100, blank=True)
    plugin_output_folder = models.CharField(max_length=500, blank=True)
    default_plugin_script = models.CharField(max_length=500, blank=True)
    web_root = models.CharField(max_length=500, blank=True)
    site_name = models.CharField(max_length=500, blank=True)
    default_storage_options = models.CharField(max_length=500,
                                       choices=Experiment.STORAGE_CHOICES,
                                       default='D', blank=True)
    auto_archive_ack = models.BooleanField("Auto-Acknowledge Archive?", default=False)
    
    barcode_args = json_field.JSONField(blank=True)
    enable_auto_pkg_dl = models.BooleanField("Enable Package Auto Download", default=True)
    ts_update_status = models.CharField(max_length=256,blank=True)
    # Controls analysis pipeline alternate processing path
    base_recalibrate = models.BooleanField(default=True)

    def get_default_command(self):
        return str(self.default_command_line)
        
    def set_TS_update_status(self,inputstr):
        self.ts_update_status = inputstr
        
    def set_enableAutoPkgDL(self,flag):
        if type(flag) is bool:
            self.enableAutoPkgDL = flag
        
    def get_enableAutoPkgDL(self):
        return self.enableAutoPkgDL

    @classmethod
    def get(cls):
        """This represents pretty much the only query on this entire
        table, find the 'canonical' GlobalConfig record.  The primary
        key order is used in all cases as the tie breaker.
        Since there is *always* supposed to be one of these in the DB,
        this call to get will properly raises a DoesNotExist error.
        """
        return cls.objects.order_by('pk')[:1].get()


@receiver(post_save, sender=GlobalConfig, dispatch_uid="save_globalconfig")
def on_save_config_sitename(sender, instance, created, **kwargs):
    """Very sneaky, we open the Default Report base template which the PHP
    file for the report renders itself inside of and find the name, replace it,
    and rewrite the thing.
    """
    try:
        with open("/opt/ion/iondb/templates/rundb/php_base.html", 'r+') as name:
            text = name.read()
            name.seek(0)
            # .*? is a non-greedy qualifier.
            # It will match the minimally satisfying text
            target = '<h1 id="sitename">.*?</h1>'
            replacement = '<h1 id="sitename">%s</h1>' % instance.site_name
            text = re.sub(target, replacement, text)
            target = '<title>.*?</title>'
            replacement = '<title>%s - Torrent Browser</title>' % instance.site_name
            name.write(re.sub(target, replacement, text))
    except IOError as err:
        logger.warning("Problem with /opt/ion/iondb/templates/rundb/php_base.html: %s" % err)


class EmailAddress(models.Model):
    email = models.EmailField(blank=True)
    selected = models.BooleanField()
    class Meta:
        verbose_name_plural = "Email addresses"


class Plugin(models.Model):
    name = models.CharField(max_length=512,db_index=True)
    version = models.CharField(max_length=256)
    date = models.DateTimeField(default=datetime.datetime.now)
    selected = models.BooleanField(default=False)
    path = models.CharField(max_length=512)
    project = models.CharField(max_length=512, blank=True, default="")
    sample = models.CharField(max_length=512, blank=True, default="")
    libraryName = models.CharField(max_length=512, blank=True, default="")
    chipType = models.CharField(max_length=512, blank=True, default="")
    autorun = models.BooleanField(default=False)
    majorBlock = models.BooleanField(default=False)
    config = json_field.JSONField(blank=True, null=True, default = "")
    #status
    status = json_field.JSONField(blank=True, null=True, default = "")

    # Store and mask inactive (uninstalled) plugins
    active = models.BooleanField(default=True)

    # Plugin Feed URL
    url = models.URLField(verify_exists=False, max_length=256, blank=True, default="")

    pluginsettings = json_field.JSONField(blank=True, null=True, default = "") 

    # These were functions, but make more sense to cache in db
    autorunMutable = models.BooleanField(default=True)
    ## file containing plugin definition. launch.sh or PluginName.py
    script = models.CharField(max_length=256, blank=True, default="")

    def addSettings(self, settings_dict):
      # Allow only fixed values for runtype and runlevel
      #TODO: this definition needs to be shared     
      runtypes = dict(COMPOSITE='composite', THUMB='thumbnail', FULLCHIP='wholechip')
      runlevels = dict(PRE='pre', DEFAULT='default', BLOCK='block', POST='post')            
      if 'runtype' in settings_dict.keys():
          self.pluginsettings['runtype'] = [value for value in settings_dict['runtype'] if value in runtypes.values()]
      if 'runlevel' in settings_dict.keys():
          self.pluginsettings['runlevel'] = [value for value in settings_dict['runlevel'] if value in runlevels.values()]

    def isConfig(self):
        try:
            if os.path.exists(os.path.join(self.path, "config.html")):
                #provide a link to load the plugins html
                return "/rundb/plugininput/" + str(self.pk) + "/"
        except OSError:
            pass
        return False

    def hasAbout(self):
        try:
            if os.path.exists(os.path.join(self.path, "about.html")):
                #provide a link to load the plugins html
                return "/rundb/plugininput/" + str(self.pk) + "/"
        except OSError:
            pass
        return False

    def __unicode__(self):
        return self.name

    def versionedName(self):
        return "%s--v%s" % (self.name, self.version)

    # Help for comparing plugins by version number
    def versionGreater(self, other):
        return(LooseVersion(self.version) > LooseVersion(other.version))

    def installStatus(self):
        """this method helps us know if a plugin was installed sucessfully"""
        if self.status.get("result"):
            if self.status["result"] == "queued":
                return "queued"
        return self.status.get("installStatus", "installed" )

    def pluginscript(self):
        # Now cached, join path and script
        if not self.script:
            from iondb.plugins.manager import pluginmanager
            self.script, _ = pluginmanager.find_pluginscript(self.path, self.name)
        if not self.script:
            self.script = '' ## field is not NULL, needs empty string
            return None
        return os.path.join(self.path, self.script)

    def info(self, use_cache=True):
        """ This requires external process call. Can be expensive. Avoid in API calls, only fetch when necessary. """
        context = { 'plugin': self }
        from iondb.plugins.manager import pluginmanager
        return pluginmanager.get_plugininfo(self.name, self.pluginscript(), context, use_cache)

    class Meta:
        unique_together=( ('name','version'), )

@receiver(pre_delete, sender=Plugin, dispatch_uid="delete_plugin")
def on_plugin_delete(sender, instance, **kwargs):
    """ Uninstall plugin on db record removal. 
    Note: DB Delete is a purge and destroys all plugin content. 
    Best to uninstall and leave records / results """
    if instance.path or instance.active:
        from iondb.plugins.manager import pluginmanager
        pluginmanager.uninstall(instance)

class PluginResult(models.Model):
    _CSV_METRICS = (
                    ("Plugin Data", 'store')
    )
    """ Many to Many mapping at the intersection of Results and Plugins """
    plugin = models.ForeignKey(Plugin)
    result = models.ForeignKey(Results, related_name='pluginresult_set')

    ALLOWED_STATES = (
        ('Completed', 'Completed'),
        ('Error', 'Error'),
        ('Started', 'Started'),
        ('Declined', 'Declined'),
        ('Unknown', 'Unknown'),
        ('Queued', 'Queued'), # In SGE queue
        ('Pending', 'Pending'), # Prior to submitting to SGE
        ('Resource', 'Exceeded Resource Limits'), ## SGE Errors
    )
    state = models.CharField(max_length=20, choices=ALLOWED_STATES)
    store = json_field.JSONField(blank=True)

    # Plugin instance config
    config = json_field.JSONField(blank=True, default='')

    jobid = models.IntegerField(null=True, blank=True)
    apikey = models.CharField(max_length=256, blank=True, null=True)

    # Track duration, disk use
    starttime = models.DateTimeField(null=True, blank=True)
    endtime = models.DateTimeField(null=True, blank=True)

    size = models.BigIntegerField(default=-1)

    def path(self):
        return os.path.join(self.result.get_report_dir(),
                            'plugin_out',
                            self.plugin.name + '_out'
                           )

    def calc_size(self):
        d = self.path()
        if not os.path.exists(d):
            return 0

        file_walker = (
            os.path.join(root, f)
            for root, _, files in os.walk( d )
            for f in files
        )
        return sum(os.path.getsize(f) for f in file_walker if os.path.isfile(f))

    # Taken from tastypie apikey generation
    def _generate_key(self):
        # Get a random UUID.
        new_uuid = uuid.uuid4()
        # Hmac that beast.
        return hmac.new(str(new_uuid), digestmod=sha1).hexdigest()

    #  Helpers for maintaining extra fields during status transitions
    def prepare(self, config='', jobid=None):
        self.state = 'Pending'
        # Always overwrite key - possibly invalidating existing key from running instance
        self.apikey = self._generate_key()
        if config:
            self.config = config
        else:
            # Not cleared if empty - reuses config from last invocation.
            pass
        self.starttime = None
        self.endtime = None
        self.jobid = jobid

    def start(self, jobid=None):
        self.state = 'Started'
        self.starttime = datetime.datetime.now()
        if self.jobid:
            if self.jobid != jobid:
                logging.warn("(Re-)started as different queue jobid: '%d' was '%d'", jobid, self.jobid)
            self.jobid = jobid

    def complete(self, state='Completed'):
        """ Call with state = Completed, Error, or other valid state """
        self.endtime = datetime.datetime.now()
        self.state = state
        self.apikey = None
        try:
            self.size = self.calc_size()
        except OSError:
            logger.exception("Failed to compute plugin size: '%s'", self.path())
            self.size = -1

    def duration(self):
        if not (self.starttime and self.endtime):
            return 0
        return (self.endtime - self.starttime)

    def __unicode__(self):
        return "%s/%s" % (self.result, self.plugin)

    class Meta:
        unique_together=( ('plugin', 'result'), )
        ordering = [ '-id' ]

# NB: Fails if not pre-delete, as path() queries linked plugin and result.
@receiver(pre_delete, sender=PluginResult, dispatch_uid="delete_pluginresult")
def on_pluginresult_delete(sender, instance, **kwargs):
    """Delete all of the files for a pluginresult record """
    try:
        directory = instance.path()
    except:
        #if we can't find the result to delete
        return

    if directory and os.path.exists(directory):
        logger.info("Deleting Plugin Result %d in %s" % (instance.id, directory))
        tasks.delete_that_folder.delay(directory,
                       "Triggered by Plugin Results %d deletion" % instance.id)

class dnaBarcode(models.Model):
    """Store a dna barcode"""
    name = models.CharField(max_length=128)     # name of barcode SET
    id_str = models.CharField(max_length=128)   # id of this barcode sequence
    type = models.CharField(max_length=64, blank=True)
    sequence = models.CharField(max_length=128)
    length = models.IntegerField(default=0, blank=True)
    floworder = models.CharField(max_length=128, blank=True, default="")
    index = models.IntegerField()
    annotation = models.CharField(max_length=512,blank=True,default="")
    adapter = models.CharField(max_length=128,blank=True,default="")
    score_mode = models.IntegerField(default=0, blank=True)
    score_cutoff = models.FloatField(default=0)

    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name_plural = "DNA Barcodes"

class ReferenceGenome(models.Model):
    """store info about the reference genome
    This should really hold the real path, it should also have methods for deleting the dirs for the files"""
    #long name
    name = models.CharField(max_length=512)
    #short name , we can change these
    short_name = models.CharField(max_length=512, unique=False)

    enabled = models.BooleanField(default=True)
    reference_path = models.CharField(max_length=1024, blank=True)
    date = models.DateTimeField()
    version = models.CharField(max_length=100, blank=True)
    species = models.CharField(max_length=512, blank=True)
    source = models.CharField(max_length=512, blank=True)
    notes = models.TextField(blank=True)
    #needs a status for index generation process
    status = models.CharField(max_length=512, blank=True)
    index_version = models.CharField(max_length=512, blank=True)
    verbose_error = models.CharField(max_length=3000, blank=True)

    class Meta:
        ordering = ['short_name']

    def delete(self):
        #delete the genome from the filesystem as well as the database

        if os.path.exists(self.reference_path):
            try:
                shutil.rmtree(self.reference_path)
            except OSError:
                return False

        super(ReferenceGenome, self).delete()
        return True

    def enable_genome(self):
        """this should be around to move the genome in a disabled dir or not"""

        #get the new path to move the reference to
        enabled_path = os.path.join(iondb.settings.TMAP_DIR, self.short_name)

        try:
            shutil.move(self.reference_path, enabled_path)
        except:
            return False

        return True

    def disable_genome(self):
        """this should be around to move the genome in a disabled dir or not"""
        #get the new path to move the reference to
        base_path = os.path.split(os.path.split(self.reference_path)[0])[0]
        disabled_path = os.path.join(base_path, "disabled", self.index_version, self.short_name)

        try:
            shutil.move(self.reference_path, disabled_path)
        except:
            return False

        return True

    def info_text(self):
        return os.path.join(self.reference_path , self.short_name + ".info.txt")

    def genome_length(self):
        genome_ini = open(self.info_text()).readlines()
        try:
            length = float([g.split("\t")[1].strip() for g in genome_ini if g.startswith("genome_length")][0])
            return length
        except:
            return -1

    def fastaOrig(self):
        """
        if there was a file named .orig then the fasta was autofixed.
        """
        orig = os.path.join(self.reference_path , self.short_name + ".orig")
        return os.path.exists(orig)

    def __unicode__(self):
        return u'%s' % self.name

class ThreePrimeadapter(models.Model):
    ALLOWED_DIRECTIONS = (
        ('Forward', 'Forward'),
        ('Reverse', 'Reverse')
    )
    
    direction = models.CharField(max_length=20, choices=ALLOWED_DIRECTIONS, default='Forward')
    
    ALLOWED_RUN_MODES = (
        ('', 'Undefined'),                         
        ('single', 'SingleRead'),
        ('pe', 'PairedEnd')
    )

    #run mode
    runMode = models.CharField(max_length=64, choices=ALLOWED_RUN_MODES, default='single', blank=True)

    name = models.CharField(max_length=256, blank=False, unique=True)
    sequence = models.CharField(max_length=512, blank=False)
    description = models.CharField(max_length=1024, blank=True)
    #20120307: actually, qual_cutoff and qual_window have nothing to do with 3' adapter.
    #it is just a convenient place to keep these values
    qual_cutoff = models.IntegerField()
    qual_window = models.IntegerField()
    adapter_cutoff = models.IntegerField()

    isDefault = models.BooleanField("use this by default", default=False)

    class Meta:
        verbose_name_plural = "3' Adapters"

    def __unicode__(self):
        return u'%s' % self.name


    def save(self):
        if (self.isDefault == False and ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True).count() == 1): 
            currentDefaults = ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id == currentDefault.id):          
                    raise ValidationError("Error: Please set another adapter for %s direction to be the default before changing this adapter not to be the default." % self.direction)
                    
        if (self.isDefault == True and ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True).count() > 0):
            currentDefaults = ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id <> currentDefault.id):
                    currentDefault.isDefault = False
                    super(ThreePrimeadapter, currentDefault).save()

        super(ThreePrimeadapter, self).save()

        
   
    def delete(self):
        if (self.isDefault == False and ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True).count() == 1): 
            currentDefaults = ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id == currentDefault.id):          
                    raise ValidationError("Error: Deleting the default adapter is not allowed. Please set another adapter for %s direction to be the default before deleting this adapter." % self.direction)
                    
        if (self.isDefault == True and ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True).count() > 0):
            currentDefaults = ThreePrimeadapter.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id == currentDefault.id):
                    raise ValidationError("Error: Deleting the default adapter is not allowed. Please set another adapter for %s direction to be the default before deleting this adapter." % self.direction)

        super(ThreePrimeadapter, self).delete()


class Publisher(models.Model):
    name = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=256)
    date = models.DateTimeField()
    path = models.CharField(max_length=512)
    global_meta = json_field.JSONField(blank=True)

    def __unicode__(self): return self.name

    def get_editing_scripts(self):
        pub_files = os.listdir(self.path)
        stages = ( ("pre_process", "Pre-processing"),
                   ("validate", "Validating"),
                   ("post_process", "Post-processing"),
                   ("register", "Registering"),
        )
        pub_scripts = []
        for stage, name in stages:
            for pub_file in pub_files:
                if pub_file.startswith(stage):
                    script_path = os.path.join(self.path, pub_file)
                    pub_scripts.append((script_path, name))
                    break
        return pub_scripts


class ContentUpload(models.Model):
    file_path = models.CharField(max_length=255)
    status = models.CharField(max_length=255, blank=True)
    meta = json_field.JSONField(blank=True)
    publisher = models.ForeignKey(Publisher, null=True)

    def __unicode__(self): return u'ContentUpload %d' % self.id


@receiver(post_delete, sender=ContentUpload, dispatch_uid="delete_upload")
def on_contentupload_delete(sender, instance, **kwargs):
    """Delete all of the files represented by a ContentUpload object which was
    deleted and all of files derived from that ContentUpload which are in it's
    folder.
    Note, it is traditional for publishers to store their Content in the folder
    of the ContentUpload from which the Content is derived.
    """
    def delete_error(func, path, info):
        logger.error("Deleting ContentUpload %d: failed to delete %s" %
                     (instance.id, path))
    directory = os.path.dirname(instance.file_path)
    logger.info("Deleting ContentUpload %d in %s" % (instance.id, directory))
    shutil.rmtree(directory, onerror=delete_error)


class Content(models.Model):
    publisher = models.ForeignKey(Publisher, related_name="contents")
    contentupload = models.ForeignKey(ContentUpload, related_name="contents")
    file = models.CharField(max_length=255)
    path = models.CharField(max_length=255)
    meta = json_field.JSONField(blank=True)

    def __unicode__(self): return self.path


@receiver(pre_delete, sender=Content, dispatch_uid="delete_content")
def on_content_delete(sender, instance, **kwargs):
    """Delete the file represented by a Content object which was deleted."""
    # I had cosidered attempting to intelligently remove empty parent
    # directories created by the Publisher; however, that's ever so slightly
    # risky in exchange for nearly 0 gain.  Uncomment everything to use.
    #directory = os.path.dirname(instance.file)
    #base = os.path.join("/results/uploads", instance.publisher.name)
    logger.info("Deleting Content from %s, %s" % (instance.publisher.name, instance.file))
    try:
        os.remove(instance.file)
        ## If the content is stored somewhere other than where we expect
        ## do nothing beyond removing it
        #if directory.startswith(base):
        #    # This is an emulation of rmdir --parents
        #    # It removes each empty directory starting at directory and then
        #    # removing each, then empty, parent until something isn't empty,
        #    # raising an OSError, or until we're at base and we stop.
        #    while not os.path.samefile(directory != base):
        #        try:
        #            os.rmdir(directory)
        #        except OSError:
        #            break
    except OSError:
        logger.error("Deleting Content from %s, %s failed." %
                     (instance.publisher.name, instance.file))


class UserEventLog(models.Model):
    text = models.TextField(blank=True)
    timeStamp = models.DateTimeField(auto_now_add=True)
    # note, this isn't exactly how I think it should go.
    # Really, we want to see log association with a diversity
    # of different user facing entities and in each of their pages, you could
    # just read the logs variable and get a list of log objects associated with
    # it.
    upload = models.ForeignKey(ContentUpload, related_name="logs")

    def __unicode__(self):
        if len(self.text) > 23:
            return u'%s...' % self.text[:20]
        else:
            return u'%s' % self.text


class UserProfile(models.Model):
    # This field is required.
    user = models.ForeignKey(User, unique=True)

    # Optional fields here
    name = models.CharField(max_length=93)
    phone_number = models.CharField(max_length=256, default="", blank=True)
    # title will not necessarily even be exposed to the end user; however,
    # we can use it to re-use this system to store important service contacts
    # such as a "Lab Manager" and an "IT Manager" which have a special
    # representation in the UI.
    title = models.CharField(max_length=256, default="user")
    # This is a simple, plain-text dumping ground for whatever the user might
    # want to document about themselves that isn't captured in the above.
    note = models.TextField(default="", blank=True)

    def __unicode__(self):
        return u'profile: %s' % self.user.username


@receiver(post_save, sender=User, dispatch_uid="create_profile")
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

#201203 - SequencingKit is now obsolete
class SequencingKit(models.Model):
    name = models.CharField(max_length=512, blank=True)
    description = models.CharField(max_length=3024, blank=True)
    sap = models.CharField(max_length=7, blank=True)

    def __unicode__(self):
        return u'%s' % self.name

#201203 - LibraryKit is now obsolete
class LibraryKit(models.Model):
    name = models.CharField(max_length=512, blank=True)
    description = models.CharField(max_length=3024, blank=True)
    sap = models.CharField(max_length=7, blank=True)

    def __unicode__(self):
        return u'%s' % self.name

class VariantFrequencies(models.Model):
    name = models.CharField(max_length=512, blank=True)
    description = models.CharField(max_length=3024, blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Variant Frequencies"


class LibraryKey(models.Model):
    ALLOWED_DIRECTIONS = (
        ('Forward', 'Forward'),
        ('Reverse', 'Reverse')
    )
    
    direction = models.CharField(max_length=20, choices=ALLOWED_DIRECTIONS, default='Forward')
    
    ALLOWED_RUN_MODES = (
        ('', 'Undefined'),                         
        ('single', 'SingleRead'),
        ('pe', 'PairedEnd')
    )

    #run mode
    runMode = models.CharField(max_length=64, choices=ALLOWED_RUN_MODES, default='single', blank=True)

    name = models.CharField(max_length=256, blank=False, unique=True)
    sequence = models.CharField(max_length=64, blank=False)
    description = models.CharField(max_length=1024, blank=True)
    isDefault = models.BooleanField("use this by default", default=False)

    class Meta:
        verbose_name_plural = "Library keys"

    def __unicode__(self):
        return u'%s' % self.name


    def save(self):
        if (self.isDefault == False and LibraryKey.objects.filter(direction=self.direction, isDefault=True).count() == 1): 
            currentDefaults = LibraryKey.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id == currentDefault.id):          
                    raise ValidationError("Error: Please set another library key for %s direction to be the default before changing this key not to be the default." % self.direction)
                    
        if (self.isDefault == True and LibraryKey.objects.filter(direction=self.direction, isDefault=True).count() > 0):
            currentDefaults = LibraryKey.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id <> currentDefault.id):                    
                    currentDefault.isDefault = False
                    super(LibraryKey, currentDefault).save()

        ###print 'Going to call super.save() for LibraryKey'
        super(LibraryKey, self).save()

        
      
    def delete(self):
        if (self.isDefault == False and LibraryKey.objects.filter(direction=self.direction, isDefault=True).count() == 1): 
            currentDefaults = LibraryKey.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id == currentDefault.id):          
                    raise ValidationError("Error: Deleting the default library key is not allowed. Please set another library key for %s direction to be the default before deleting this key." % self.direction)
                    
        if (self.isDefault == True and LibraryKey.objects.filter(direction=self.direction, isDefault=True).count() > 0):
            currentDefaults = LibraryKey.objects.filter(direction=self.direction, isDefault=True)
            #there should only be 1 default for a given direction at any time
            for currentDefault in currentDefaults:
                if (self.id == currentDefault.id):
                    raise ValidationError("Error: Deleting the default library key is not allowed. Please set another library key for %s direction to be the default before deleting this key." % self.direction)

        super(LibraryKey, self).delete()


class MessageManager(models.Manager):

    def bound(self, *bindings):
        query = models.Q()
        for route_binding in bindings:
            query |= models.Q(route__startswith=route_binding)
        return self.get_query_set().filter(query)


class Message(models.Model):
    """This is a semi persistent, user oriented message intended to be
    displayed in the UI.
    """

    objects = MessageManager()

    body = models.TextField(blank=True, default="")
    level = models.IntegerField(default=20)
    route = models.TextField(blank=True, default="")
    expires = models.TextField(blank=True, default="read")
    tags = models.TextField(blank=True, default="")
    status = models.TextField(blank=True, default="unread")
    time = models.DateTimeField(auto_now_add=True)

    # Message alert levels
    DEBUG    = 10
    INFO     = 20
    SUCCESS  = 25
    WARNING  = 30
    ERROR    = 40
    CRITICAL = 50

    def __unicode__(self):
        if len(self.body) > 80:
            return u'%s...' % self.body[:77]
        else:
            return u'%s' % self.body[:80]

    @classmethod
    def log_new_message(cls, level, body, route, **kwargs):
        """A Message factory method which logs and creates a message with the
         given log level
         """
        logger.log(level, 'User Message route:\t"%s" body:\t"%s"' %
                          (route, body))
        msg = cls(body=body, route=route, level=level, **kwargs)
        msg.save()
        return msg

    @classmethod
    def debug(cls, body, route="", **kwargs):
        return cls.log_new_message(cls.DEBUG, body, route, **kwargs)

    @classmethod
    def info(cls, body, route="", **kwargs):
        return cls.log_new_message(cls.INFO, body, route, **kwargs)

    @classmethod
    def success(cls, body, route="", **kwargs):
        return cls.log_new_message(cls.SUCCESS, body, route, **kwargs)

    @classmethod
    def warn(cls, body, route="", **kwargs):
        return cls.log_new_message(cls.WARNING, body, route, **kwargs)

    @classmethod
    def error(cls, body, route="", **kwargs):
        return cls.log_new_message(cls.ERROR, body, route, **kwargs)

    @classmethod
    def critical(cls, body, route="", **kwargs):
        return cls.log_new_message(cls.CRITICAL, body, route, **kwargs)

# JUST DON'T THINK THIS IS BAKED (THOUGHT OUT) ENOUGH 
#class ProjectUserVisibility(models.Model):
#    """By default, a given project for a given user has no ProjectUserVisibility
#    and the project is 'show' visibility for that user.
#    """
#    VISIBILITY_CHOICES = (
#        ('star', 'Star'), #Is this useful or a even a good idea?
#        ('show', 'Normal'),
#        ('hide', 'Hide')
#        )
#    user = models.ForeignKey(User)
#    project = models.ForeignKey(Project)
#    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES)


class EventLogManager(models.Manager):
    def for_model(self, model):
        """
        QuerySet for all comments for a particular model (either an instance or
        a class).
        """
        ct = ContentType.objects.get_for_model(model)
        qs = self.get_query_set().filter(content_type=ct)
        if isinstance(model, models.Model):
            qs = qs.filter(object_pk=force_unicode(model._get_pk_val()))
        return qs
    def add_entry(self, instance, message, username="ION"):
        ct = ContentType.objects.get_for_model(instance)
        ev = EventLog(object_pk=instance.pk, content_type=ct, username=username, text=message)
        ev.save()
        
    
class EventLog (models.Model):
    # Content-object field
    content_type   = models.ForeignKey(ContentType,
            verbose_name='content type',
            related_name="content_type_set_for_%(class)s")
    object_pk      = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey(ct_field="content_type", fk_field="object_pk")

    text = models.TextField('comment', max_length=3000)
    username = models.CharField(max_length=32, default="ION", blank=True)

    def get_content_object_url(self):
        """
        Get a URL suitable for redirecting to the content object.
        """
        return urlresolvers.reverse(
            "eventlog-url-redirect",
            args=(self.content_type_id, self.object_pk)
        )
    objects = EventLogManager()
    created = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return self.text

class PEMetrics(models.Model):

    pereport = models.ForeignKey(Results, db_index=True, related_name='pemetrics_set')
    pefwdreport = models.ForeignKey(Results, db_index=True, related_name='pefwdreport_set')
    perevreport = models.ForeignKey(Results, db_index=True, related_name='perevreport_set')
    pairingrate = models.FloatField(blank=True, null=True)
    fwdandrevcorrected = models.FloatField(blank=True, null=True)
    fwdandrevuncorrected = models.FloatField(blank=True, null=True)
    fwdnotrev = models.FloatField(blank=True, null=True)
    totalbasesunion = models.FloatField(blank=True, null=True)
    totalbasescorrected = models.FloatField(blank=True, null=True)
    totalbasesunpairedfwd = models.FloatField(blank=True, null=True)
    totalbasesunpairedrev = models.FloatField(blank=True, null=True)
    totalq17basesunpairedrev = models.FloatField(blank=True, null=True)
    totalq17basesunpairedfwd = models.FloatField(blank=True, null=True)
    totalq17basescorrected = models.FloatField(blank=True, null=True)
    totalq17basesunion = models.FloatField(blank=True, null=True)
    totalq20basesunion = models.FloatField(blank=True, null=True)
    totalq20basescorrected = models.FloatField(blank=True, null=True)
    totalq20basesunpairedfwd = models.FloatField(blank=True, null=True)
    totalq20basesunpairedrev = models.FloatField(blank=True, null=True)
    totalreadsbasesunpairedrev = models.FloatField(blank=True, null=True)
    totalreadsbasesunpairedfwd = models.FloatField(blank=True, null=True)
    totalreadsbasescorrected = models.FloatField(blank=True, null=True)
    totalreadsbasesunion = models.FloatField(blank=True, null=True)
    meanlengthunion = models.FloatField(blank=True, null=True)
    meanlengthcorrected = models.FloatField(blank=True, null=True)
    meanlengthunpairedfwd = models.FloatField(blank=True, null=True)
    meanlengthunpairedrev = models.FloatField(blank=True, null=True)

    def __unicode__(self):
        return self.pereport.resultsName

    class Meta:
        verbose_name_plural = "PE metrics"


