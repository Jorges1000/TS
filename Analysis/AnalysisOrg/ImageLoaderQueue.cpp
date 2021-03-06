/* Copyright (C) 2012 Ion Torrent Systems, Inc. All Rights Reserved */
#include "ImageLoaderQueue.h"
#include "Utils.h"
#include "FlowBuffer.h"
#include "SynchDatSerialize.h"
#include "ComparatorNoiseCorrector.h"


// handle our fake mutex flags
void SetReadCompleted(ImageLoadWorkInfo *one_img_loader)
{
      // just a note: no guarantee that prior flows have finished yet
    ( ( int volatile * ) one_img_loader->CurRead ) [one_img_loader->cur_buffer] = 1;
}


void *FileLoadWorker ( void *arg )
{
  WorkerInfoQueue *q = static_cast<WorkerInfoQueue *> ( arg );
  assert ( q );

  bool done = false;

  while ( !done )
  {
    WorkerInfoQueueItem item = q->GetItem();

    if ( item.finished == true )
    {
      // we are no longer needed...go away!
      done = true;
      q->DecrementDone();
      continue;
    }
    ImageLoadWorkInfo *one_img_loader = ( ImageLoadWorkInfo * ) item.private_data;

    ClockTimer timer;

    // col noise correction
    if ( one_img_loader->inception_state->img_control.col_flicker_correct )
    {
        if(one_img_loader->inception_state->bfd_control.beadfindThumbnail)
        {
          //ComparatorNoiseCorrector
          ComparatorNoiseCorrector cnc;
          cnc.CorrectComparatorNoiseThumbnail(one_img_loader->img[one_img_loader->cur_buffer].raw, one_img_loader->mask, one_img_loader->inception_state->loc_context.regionXSize,one_img_loader->inception_state->loc_context.regionYSize, one_img_loader->inception_state->img_control.col_flicker_correct_verbose);
        } else {
            ComparatorNoiseCorrector cnc;
            cnc.CorrectComparatorNoise(one_img_loader->img[one_img_loader->cur_buffer].raw, one_img_loader->mask, one_img_loader->inception_state->img_control.col_flicker_correct_verbose);
        }
    }

    // dump dc offset one_img_loaderrmation before we do any normalization
    DumpDcOffset ( one_img_loader );
    int flow_buffer_for_flow = one_img_loader->cur_buffer;

    one_img_loader->img[flow_buffer_for_flow].SetMeanOfFramesToZero ( one_img_loader->normStart, one_img_loader->normEnd );

    // correct in-channel electrical cross-talk
    ImageTransformer::XTChannelCorrect ( one_img_loader->img[flow_buffer_for_flow].raw, one_img_loader->img[flow_buffer_for_flow].results_folder );

    // calculate the smooth pH step amplitude in empty wells across the whole image
    if ( one_img_loader->doEmptyWellNormalization )
    {
      // this is redundant with what's in the EmptyTrace class, but this method of spatial normalization
      // is going to go away soon, so not worth fixing
      MaskType referenceMask = MaskReference;

      if ( one_img_loader->inception_state->bkg_control.use_dud_and_empty_wells_as_reference )
        referenceMask = ( MaskType ) ( MaskReference | MaskDud );

      one_img_loader->img[flow_buffer_for_flow].CalculateEmptyWellLocalScaleForFlow ( * ( one_img_loader->pinnedInFlow ),one_img_loader->mask,one_img_loader->flow,referenceMask,one_img_loader->smooth_span );
#if 0
      char fname[512];
      sprintf ( fname,"ewampimg_%04d.txt",one_img_loader->flow );
      FILE *ewampfile = fopen ( fname,"w" );
      for ( int row=0;row < one_img_loader->img[flow_buffer_for_flow].GetRows();row++ )
      {
        int col;

        for ( col=0;col < ( one_img_loader->img[flow_buffer_for_flow].GetCols()-1 ); col++ )
          fprintf ( ewampfile,"%9.5f\t",one_img_loader->img[flow_buffer_for_flow].getEmptyWellAmplitude ( row,col ) );

        fprintf ( ewampfile,"%9.5f\n",one_img_loader->img[flow_buffer_for_flow].getEmptyWellAmplitude ( row,col ) );
      }
      fclose ( ewampfile );
#endif
    }

    // dump pH step debug one_img_loader to file (its really fast, don't worry)
    DumpStep ( one_img_loader );

    if ( one_img_loader->doRawBkgSubtract )
    {
      one_img_loader->img[flow_buffer_for_flow].SubtractLocalReferenceTrace ( one_img_loader->mask, MaskBead, MaskReference, one_img_loader->NNinnerx,
          one_img_loader->NNinnery,one_img_loader->NNouterx,one_img_loader->NNoutery, false, true, true );
      if ( one_img_loader->flow==0 ) // absolute first flow,not flow buffer
        printf ( "Notify user: NN empty subtraction in effect.  No further warnings will be given. %d \n",one_img_loader->flow );
    }

    printf ( "Allow model to go %d\n", one_img_loader->flow );

    SetReadCompleted(one_img_loader);

    size_t usec = timer.GetMicroSec();

    fprintf ( stdout, "FileLoadWorker: ImageProcessing time for flow %d: %0.5lf sec\n", one_img_loader->flow , usec / 1.0e6);

    q->DecrementDone();
  }

  return ( NULL );
}

void *FileSDatLoadWorker ( void *arg )
{
  WorkerInfoQueue *q = static_cast<WorkerInfoQueue *> ( arg );
  assert ( q );

  bool done = false;

  while ( !done )
  {
    WorkerInfoQueueItem item = q->GetItem();

    if ( item.finished == true )
    {
      // we are no longer needed...go away!
      done = true;
      q->DecrementDone();
      continue;
    }

    ImageLoadWorkInfo *one_img_loader = ( ImageLoadWorkInfo * ) item.private_data;
    //    int flow_buffer_for_flow = one_img_loader->cur_buffer;

    // TraceChunkSerializer serializer;
    // serializer.Read ( one_img_loader->name, one_img_loader->sdat[flow_buffer_for_flow] );

    ClockTimer timer;
    SetReadCompleted(one_img_loader);
    size_t usec = timer.GetMicroSec();
    fprintf ( stdout, "FileLoadWorker: ImageProcessing time for flow %d: %0.5lf sec\n", one_img_loader->flow, usec / 1.0e6);

    q->DecrementDone();
  }

  return ( NULL );
}

void ConstructNameForCurrentInfo(ImageLoadWorkInfo *cur_image_loader, const char *post_fix)
{
  int cur_flow = cur_image_loader->flow;
    int filenum = cur_flow + ( cur_flow / cur_image_loader->numFlowsPerCycle ) * cur_image_loader->hasWashFlow;
    sprintf (cur_image_loader->name, "%s/%s%04d.%s", cur_image_loader->dat_source_directory,cur_image_loader->acqPrefix, filenum , post_fix);
}

void SetUpIndividualImageLoaders ( ImageLoadWorkInfo *my_img_loaders, ImageLoadWorkInfo *master_img_loader )
{
  for ( int  i_buffer = 0; i_buffer < master_img_loader->flow_buffer_size; i_buffer++ )
  {
    memcpy ( &my_img_loaders[i_buffer], master_img_loader, sizeof ( *master_img_loader ) );
    // names of files not set here yet
    my_img_loaders[i_buffer].flow = master_img_loader->startingFlow+i_buffer; //this buffer entry points to this absolute flow
    my_img_loaders[i_buffer].cur_buffer = i_buffer; // the actual buffer
    if (master_img_loader->doingSdat)
      ConstructNameForCurrentInfo(&my_img_loaders[i_buffer],master_img_loader->inception_state->img_control.sdatSuffix.c_str());
    else
      ConstructNameForCurrentInfo(&my_img_loaders[i_buffer],"dat");
  }
}


void KillQueue ( WorkerInfoQueue *loadWorkQ, int numWorkers )
{
  WorkerInfoQueueItem item;
  for ( int cworker = 0; cworker < numWorkers; cworker++ )
  {
    item.private_data = NULL;
    item.finished = true;
    loadWorkQ->PutItem ( item );
  }
  // wait for all workers to exit
  loadWorkQ->WaitTillDone();
}

// fake mutex using the >individual< image loaders
void DontReadAheadOfSignalProcessing (  ImageLoadWorkInfo *info, int lead)
{
  // don't read ahead too far of BkgModel regional fitter threads
  while ( info->cur_buffer > lead &&
          ! ( ( int volatile * ) info->CurProcessed ) [info->cur_buffer - lead] )
    sleep ( 1 );
}

// don't step on the compute intensity that happens every chunk of flows
void PauseForLongCompute ( int cur_flow,  ImageLoadWorkInfo *info )
{
  // wait for the the BkgModel regional fitter threads to finish this block
  while ( ( CheckFlowForWrite ( cur_flow,false ) && ! ( (( int volatile * ) info->CurProcessed)[info->cur_buffer] ) ) )
    sleep ( 1 );
}



void JustLoadOneImageWithPinnedUpdate(ImageLoadWorkInfo *cur_image_loader)
{

    if ( !cur_image_loader->img[cur_image_loader->cur_buffer].LoadRaw ( cur_image_loader->name) )
    {
      exit ( EXIT_FAILURE );
    }
      //tikSMoother is a no-op if there was no tikSmoothFile entered on command line
      // cur_image_loader->img[cur_image_loader->cur_buffer].SmoothMeTikhonov ( NULL,false,cur_image_loader->name);

  // if gain correction has been calculated, apply it
  // @TODO: is this correctly done before pinning status is calculated, or after like XTCorrect?
    if ( ImageTransformer::gain_correction != NULL )
      ImageTransformer::GainCorrectImage ( cur_image_loader->img[cur_image_loader->cur_buffer].raw );
  
    // pinning updates only need to be complete to remove indeterminacy
    // in values dumped in DumpStep in FileLoadWorker
    cur_image_loader->pinnedInFlow->Update ( cur_image_loader->flow, &cur_image_loader->img[cur_image_loader->cur_buffer] );

}

void *FileLoader ( void *arg )
{
  ImageLoadWorkInfo *master_img_loader = ( ImageLoadWorkInfo * ) arg;


  WorkerInfoQueue *loadWorkQ = new WorkerInfoQueue ( master_img_loader->flow_buffer_size );


  ImageLoadWorkInfo *n_image_loaders = new ImageLoadWorkInfo[master_img_loader->flow_buffer_size];
  SetUpIndividualImageLoaders ( n_image_loaders,master_img_loader );

  int numWorkers = numCores() /2; // @TODO - this should be subject to inception_state options
  // int numWorkers = 1;
  numWorkers = ( numWorkers < 1 ? 1:numWorkers );
  fprintf ( stdout, "FileLoader: numWorkers threads = %d\n", numWorkers );
  {
    int cworker;
    pthread_t work_thread;
    // spawn threads for doing background correction/fitting work
    for ( cworker = 0; cworker < numWorkers; cworker++ )
    {
      int t = pthread_create ( &work_thread, NULL, FileLoadWorker,
                               loadWorkQ );
      pthread_detach(work_thread);
      if ( t )
        fprintf ( stderr, "Error starting thread\n" );
    }
  }

  WorkerInfoQueueItem item;

  //time_t start, end;
  int flow_buffer_size = master_img_loader->flow_buffer_size;

  Timer timer_file_access;
  double file_access_time = 0;
  // this loop goes over the individual image loaders
  for ( int i_buffer = 0; i_buffer < flow_buffer_size; i_buffer++ )
  {
    ImageLoadWorkInfo *cur_image_loader = &n_image_loaders[i_buffer];

    int cur_flow = cur_image_loader->flow;  // each job is an n_image_loaders item

    DontReadAheadOfSignalProcessing (cur_image_loader, master_img_loader->lead);
    //***We are doing this on this thread so we >load< in sequential order that pinned in Flow updates in sequential order
    timer_file_access.restart();
    JustLoadOneImageWithPinnedUpdate(cur_image_loader);
    file_access_time += timer_file_access.elapsed();
    //*** now we can do the rest of the computation for an image, including dumping in a multiply threaded fashion

    item.finished = false;
    item.private_data = cur_image_loader;
    loadWorkQ->PutItem ( item );

    if (ChipIdDecoder::GetGlobalChipId() != ChipId900)
      PauseForLongCompute ( cur_flow,cur_image_loader );

    if ( CheckFlowForWrite ( cur_flow,false ) )
    {
      fprintf (stdout, "File access Time for flow %d to %d: %.1f sec\n", ( ( cur_flow+1 ) - NUMFB ), cur_flow, file_access_time);
      file_access_time = 0;
    }
  }

  // wait for all of the images to be processed
  loadWorkQ->WaitTillDone();
  KillQueue ( loadWorkQ,numWorkers );

  delete loadWorkQ;
  delete[] n_image_loaders;

  master_img_loader->finished = true;

  return NULL;
}

void *FileSDatLoader ( void *arg )
{
  ImageLoadWorkInfo *master_img_loader = ( ImageLoadWorkInfo * ) arg;


  WorkerInfoQueue *loadWorkQ = new WorkerInfoQueue ( master_img_loader->flow_buffer_size );
  ImageLoadWorkInfo *n_image_loaders = new ImageLoadWorkInfo[master_img_loader->flow_buffer_size];
  SetUpIndividualImageLoaders ( n_image_loaders,master_img_loader );

  //int numWorkers = numCores() /2; // @TODO - this should be subject to inception_state options
  int numWorkers = 1;
  numWorkers = ( numWorkers < 1 ? 1:numWorkers );
  fprintf ( stdout, "FileLoader: numWorkers threads = %d\n", numWorkers );
  {
    int cworker;
    pthread_t work_thread;
    // spawn threads for doing background correction/fitting work
    for ( cworker = 0; cworker < numWorkers; cworker++ )
    {
      int t = pthread_create ( &work_thread, NULL, FileSDatLoadWorker,
                               loadWorkQ );
      pthread_detach(work_thread);
      if ( t )
        fprintf ( stderr, "Error starting thread\n" );
    }
  }

  WorkerInfoQueueItem item;
  Timer timer_file_access;
  double file_access_time = 0;
  int flow_buffer_size = master_img_loader->flow_buffer_size;
  for ( int i_buffer = 0; i_buffer < flow_buffer_size;i_buffer++ )
  {
    ImageLoadWorkInfo *cur_image_loader = &n_image_loaders[i_buffer];

    int cur_flow = cur_image_loader->flow; // each job is an n_image_loaders item

    DontReadAheadOfSignalProcessing (cur_image_loader, master_img_loader->lead);
    TraceChunkSerializer serializer;
    timer_file_access.restart();
    bool ok = serializer.Read ( cur_image_loader->name, cur_image_loader->sdat[cur_image_loader->cur_buffer] );
    if (!ok) {
      ION_ABORT("Couldn't load file: " + ToStr(cur_image_loader->name));
    }
    file_access_time += timer_file_access.elapsed();
    cur_image_loader->pinnedInFlow->Update ( cur_image_loader->flow, &cur_image_loader->sdat[cur_image_loader->cur_buffer] );
    cur_image_loader->sdat[cur_image_loader->cur_buffer].AdjustForDrift();
    cur_image_loader->sdat[cur_image_loader->cur_buffer].SubDcOffset();
    item.finished = false;
    item.private_data = cur_image_loader;
    loadWorkQ->PutItem ( item );
    
    if (ChipIdDecoder::GetGlobalChipId() != ChipId900)
      PauseForLongCompute ( cur_flow,cur_image_loader );

    if ( CheckFlowForWrite ( cur_flow,false ) )
    {
      fprintf (stdout, "File access Time for flow %d to %d: %.1f sec\n", ( ( cur_flow+1 ) - NUMFB ), cur_flow, file_access_time);
      file_access_time = 0;
    }
  }

  // wait for all of the images to be processed
  loadWorkQ->WaitTillDone();

  KillQueue ( loadWorkQ,numWorkers );

  delete loadWorkQ;

  delete[] n_image_loaders;

  master_img_loader->finished = true;

  return NULL;
}

//@TODO: why is this not a method of info?
void DumpStep ( ImageLoadWorkInfo *info )
{
//@TODO: if only there were some object, say a flow context, that had
// already converted the flowOrder into the string of nucleotides to
// the length of all the flows we wouldn't need to write code like
// this...but that would be crazy talk.
  char nucChar = info->inception_state->flow_context.ReturnNucForNthFlow ( info->flow );
  string nucStepDir = string ( info->inception_state->sys_context.GetResultsFolder() ) + string ( "/NucStep" );

  // Make output directory or quit
  if ( mkdir ( nucStepDir.c_str(), 0777 ) && ( errno != EEXIST ) )
  {
    perror ( nucStepDir.c_str() );
    return;
  }

  // Set region width & height
  int rWidth=50;
  int rHeight=50;

  // Lower left corner of the region should equal 0 modulus xModulus or yModulus
  int xModulus=50;
  int yModulus=50;

  vector<string> regionName;
  vector<int> regionStartCol;
  vector<int> regionStartRow;
  vector<int> regionWidth;
  vector<int> regionHeight;


  const RawImage *rawImg = info->img[info->cur_buffer].GetImage();

  ChipIdEnum chipId = ChipIdDecoder::GetGlobalChipId();
  if ( chipId == ChipId900 )
  {
    // Proton chips
    regionName.push_back ( "inlet" );
    regionStartCol.push_back ( xModulus * floor ( 0.1 * ( float ) rawImg->cols / ( float ) xModulus ) );
    regionStartRow.push_back ( yModulus * floor ( 0.5 * ( float ) rawImg->rows / ( float ) yModulus ) );
    regionWidth.push_back ( rWidth );
    regionHeight.push_back ( rHeight );

    regionName.push_back ( "middle" );
    regionStartCol.push_back ( xModulus * floor ( 0.5 * ( float ) rawImg->cols / ( float ) xModulus ) );
    regionStartRow.push_back ( yModulus * floor ( 0.5 * ( float ) rawImg->rows / ( float ) yModulus ) );
    regionWidth.push_back ( rWidth );
    regionHeight.push_back ( rHeight );

    regionName.push_back ( "outlet" );
    regionStartCol.push_back ( xModulus * floor ( 0.9 * ( float ) rawImg->cols / ( float ) xModulus ) );
    regionStartRow.push_back ( yModulus * floor ( 0.5 * ( float ) rawImg->rows / ( float ) yModulus ) );
    regionWidth.push_back ( rWidth );
    regionHeight.push_back ( rHeight );
  }
  else
  {
    // PGM chips
    regionName.push_back ( "inlet" );
    regionStartCol.push_back ( xModulus * floor ( 0.9 * ( float ) rawImg->cols / ( float ) xModulus ) );
    regionStartRow.push_back ( yModulus * floor ( 0.9 * ( float ) rawImg->rows / ( float ) yModulus ) );
    regionWidth.push_back ( rWidth );
    regionHeight.push_back ( rHeight );

    regionName.push_back ( "middle" );
    regionStartCol.push_back ( xModulus * floor ( 0.5 * ( float ) rawImg->cols / ( float ) xModulus ) );
    regionStartRow.push_back ( yModulus * floor ( 0.5 * ( float ) rawImg->rows / ( float ) yModulus ) );
    regionWidth.push_back ( rWidth );
    regionHeight.push_back ( rHeight );

    regionName.push_back ( "outlet" );
    regionStartCol.push_back ( xModulus * floor ( 0.1 * ( float ) rawImg->cols / ( float ) xModulus ) );
    regionStartRow.push_back ( yModulus * floor ( 0.1 * ( float ) rawImg->rows / ( float ) yModulus ) );
    regionWidth.push_back ( rWidth );
    regionHeight.push_back ( rHeight );
  }

  for ( unsigned int iRegion=0; iRegion<regionStartRow.size(); iRegion++ )
  {
    info->img[info->cur_buffer].DumpStep (
      regionStartCol[iRegion],
      regionStartRow[iRegion],
      regionWidth[iRegion],
      regionHeight[iRegion],
      regionName[iRegion],
      nucChar,
      nucStepDir,
      info->mask,
      info->pinnedInFlow,
      info->flow
    );
  }
}

void DumpDcOffset ( ImageLoadWorkInfo *info )
{
  char nucChar = info->inception_state->flow_context.ReturnNucForNthFlow ( info->flow );
  string dcOffsetDir = string ( info->inception_state->sys_context.GetResultsFolder() ) + string ( "/dcOffset" );

  // Make output directory or quit
  if ( mkdir ( dcOffsetDir.c_str(), 0777 ) && ( errno != EEXIST ) )
  {
    perror ( dcOffsetDir.c_str() );
    return;
  }

  int nSample=100000;

  info->img[info->cur_buffer].DumpDcOffset (
    nSample,
    dcOffsetDir,
    nucChar,
    info->flow
  );
}

