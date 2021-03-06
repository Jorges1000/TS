/* Copyright (C) 2012 Ion Torrent Systems, Inc. All Rights Reserved */

#include <string>
#include <algorithm>
#include <stdio.h>
#include <stdlib.h>

#include "Utils.h"
#include "ComparatorNoiseCorrector.h"


void ComparatorNoiseCorrector::CorrectComparatorNoise(RawImage *raw, Mask *mask, bool verbose)
{
  //if isThumbnail, assume 100x100 for
  time_t cnc_start;
  time ( &cnc_start );
  MemUsage ( "Starting Comparator Noise Correction" );
  float *comparator_sigs;
  float *comparator_noise;
  float comparator_rms[raw->cols*2];
  int comparator_mask[raw->cols*2];
  int c_avg_num[raw->cols*4];
  int x,y,frame,i;
  int phase;

  comparator_sigs = new float[raw->cols*4*raw->frames];
  comparator_noise = new float[raw->cols*2*raw->frames];
  memset(comparator_sigs,0,sizeof(float) * raw->cols*4*raw->frames);
  memset(comparator_noise,0,sizeof(float) * raw->cols*2*raw->frames);
  memset(c_avg_num,0,sizeof(c_avg_num));
  memset(comparator_mask,0,sizeof(comparator_mask));

  // first, create the average comparator signals
  // making sure to avoid pinned pixels
  i=0;
  for ( y=0;y<raw->rows;y++ ) {
    for ( x=0;x<raw->cols;x++ ) {
      int cndx;
      int frame;
      float *cptr;

      // if this pixel is pinned..skip it
      if ( (( *mask ) [i] & MaskPinned)==0 )
      {
        // figure out which comparator this pixel belongs to
        // since we don't know the phase just yet, we first split each column
        // up into 4 separate comparator signals, even though
        // there are really only 2 of them
        cndx = 4*x + (y&0x3);
        
        // get a pointer to where we will build the comparator signal average
        cptr = comparator_sigs + cndx*raw->frames;
  
        // add this pixels' data in
        for ( frame=0;frame<raw->frames;frame++ )
          cptr[frame] += raw->image[frame*raw->frameStride+i];
  
        // count how many we added
        c_avg_num[cndx]++;
      }

      i++;
    }
  }

  // divide by the number to make a proper average
  for ( int cndx=0;cndx < raw->cols*4;cndx++ )
  {
    float *cptr;

    if ( c_avg_num[cndx] == 0 )
      continue;

    // get a pointer to where we will build the comparator signal average
    cptr = comparator_sigs + cndx*raw->frames;

    // divide by corresponding count, extreme case: divide by zero if all pixels are pinned
    if(c_avg_num[cndx] != 0){
      for ( frame=0;frame<raw->frames;frame++ ){
        cptr[frame] /= c_avg_num[cndx];
      }
    }
  }

  // subtract DC offset from average comparator signals
  for ( int cndx=0;cndx < raw->cols*4;cndx++ )
  {
    float *cptr;
    float dc = 0.0f;

    // get a pointer to where we will build the comparator signal average
    cptr = comparator_sigs + cndx*raw->frames;

    for ( frame=0;frame<raw->frames;frame++ )
      dc += cptr[frame];

    dc /= raw->frames;

    // subtract dc offset
    for ( frame=0;frame<raw->frames;frame++ )
      cptr[frame] -= dc;
  }

  // now figure out which pair of signals go together
  // this function also combines pairs of signals accordingly
  // from this point forward, there are only raw->cols*2 signals to deal with
  phase = DiscoverComparatorPhase(comparator_sigs,c_avg_num,raw->cols*4,raw->frames);

  //special case of rms==0, assign phase to -1
  if(phase != -1){
      // mask comparators that don't contain any un-pinned pixels
      for ( int cndx=0;cndx < raw->cols*2;cndx++ )
      {
        if ( c_avg_num[cndx] == 0 )
        {
          comparator_mask[cndx] = 1;
          continue;
        }
      }

      // now neighbor-subtract the comparator signals
      NNSubtractComparatorSigs(comparator_noise,comparator_sigs,comparator_mask,1,raw->cols*2,raw->frames);

      // measure noise in the neighbor-subtracted signals
      CalcComparatorSigRMS(comparator_rms,comparator_noise,raw->cols*2,raw->frames);

      // find the noisiest 10%
      MaskIQR(comparator_mask,comparator_rms,raw->cols*2);

      // neighbor-subtract again...avoiding noisiest 10%
      NNSubtractComparatorSigs(comparator_noise,comparator_sigs,comparator_mask,1,raw->cols*2,raw->frames);

      // measure noise in the neighbor-subtracted signals
      CalcComparatorSigRMS(comparator_rms,comparator_noise,raw->cols*2,raw->frames);

      // reset comparator_mask
      memset(comparator_mask,0,sizeof(comparator_mask));
      for ( int cndx=0;cndx < raw->cols*2;cndx++ )
      {
        if ( c_avg_num[cndx] == 0 )
        {
          comparator_mask[cndx] = 1;
        }
      }
      MaskIQR(comparator_mask,comparator_rms,raw->cols*2, verbose);

      // neighbor-subtract again...avoiding noisiest 10%
      NNSubtractComparatorSigs(comparator_noise,comparator_sigs,comparator_mask,1,raw->cols*2,raw->frames);

      for ( int cndx=0;cndx < raw->cols*2;cndx++ )
      {
        float *cptr;

        if ( c_avg_num[cndx] == 0 ) {
          // get a pointer to where we will build the comparator signal average
          cptr = comparator_sigs + cndx*raw->frames;
          memset(cptr,0,sizeof(float[raw->frames]));
        }
      }

      // now subtract each neighbor-subtracted comparator signal from the
      // pixels that are connected to that comparator
      i=0;
      for ( y=0;y<raw->rows;y++ ) {
        for ( x=0;x<raw->cols;x++ ) {
          int cndx;
          int frame;
          float *cptr;

          // if this pixel is pinned..skip it
          if ( (( *mask ) [i] & MaskPinned)==0 )
          {
            // figure out which comparator this pixel belongs to
            cndx = 2*x;
            if (( (y&0x3) == (0+phase) ) || ( (y&0x3) == (1+phase) ))
                cndx++;

            //only perform correction on noisy comparators;
            if(comparator_mask[cndx]){
              // get a pointer to where we will build the comparator signal average
              cptr = comparator_noise + cndx*raw->frames;
              // subtract nn comparator signal from this pixel's data
              for ( frame=0;frame<raw->frames;frame++ )
                raw->image[frame*raw->frameStride+i] -= cptr[frame];
            }
          }

          i++;
        }
      }
  }

  delete [] comparator_noise;
  delete [] comparator_sigs;
  MemUsage ( "After Comparator Noise Correction" );
  time_t cnc_end;
  time ( &cnc_end );
  fprintf (stdout, "Comparator Noise Correction: %0.3lf sec.\n", difftime(cnc_end, cnc_start));
}

void ComparatorNoiseCorrector::CorrectComparatorNoiseThumbnail(RawImage *raw, Mask *mask, int regionXSize, int regionYSize, bool verbose)
{
  time_t cnc_start;
  time ( &cnc_start );
  MemUsage ( "Starting Comparator Noise Correction" );
  if( raw->cols%regionXSize != 0 || raw->rows%regionYSize != 0){
    //skip correction
    fprintf (stdout, "Region sizes are not compatible with image(%d x %d): %d x %d", raw->rows, raw->cols, regionYSize, regionXSize);
  }
  int nXPatches = raw->cols / regionXSize;
  int nYPatches = raw->rows / regionYSize;

  float *comparator_sigs;
  float *comparator_noise;
  float comparator_rms[regionXSize*2];
  int comparator_mask[regionXSize*2];
  int c_avg_num[regionXSize*4];
  int phase;

  comparator_sigs = new float[raw->cols*4*raw->frames];
  comparator_noise = new float[raw->cols*2*raw->frames];
  for(int pRow = 0; pRow < nYPatches; pRow++){
    for(int pCol = 0; pCol < nXPatches; pCol++){
        if(verbose)
          fprintf (stdout, "Patch y: %d, Patch x: %d\n", pRow, pCol);
        memset(comparator_sigs,0,sizeof(float) * regionXSize*4*raw->frames);
        memset(comparator_noise,0,sizeof(float) * regionXSize*2*raw->frames);
        memset(c_avg_num,0,sizeof(c_avg_num));
        memset(comparator_mask,0,sizeof(comparator_mask));

        // first, create the average comparator signals
        // making sure to avoid pinned pixels

        for ( int y=0;y<regionYSize;y++ ) {
          for(int x=0;x<regionXSize;x++ ) {
            // if this pixel is pinned..skip it
            int imgInd = raw->cols * (y+pRow*regionYSize) + x + pCol*regionXSize;
            if ( (( *mask ) [imgInd] & MaskPinned)==0 )
            {
              // figure out which comparator this pixel belongs to
              // since we don't know the phase just yet, we first split each column
              // up into 4 separate comparator signals, even though
              // there are really only 2 of them
              int cndx = 4*x + (y&0x3);

              // get a pointer to where we will build the comparator signal average
              float *cptr = comparator_sigs + cndx*raw->frames;

              // add this pixels' data in
              for (int frame=0;frame<raw->frames;frame++ )
                cptr[frame] += raw->image[frame*raw->frameStride+imgInd];

              // count how many we added
              c_avg_num[cndx]++;
            }
          }
        }

        // divide by the number to make a proper average
        for ( int cndx=0;cndx < regionXSize*4;cndx++ )
        {
          if ( c_avg_num[cndx] == 0 )
            continue;

          // get a pointer to where we will build the comparator signal average
          float *cptr = comparator_sigs + cndx*raw->frames;

          // divide by corresponding count, extreme case: divide by zero if all pixels are pinned
          if(c_avg_num[cndx] != 0){
            for (int frame=0;frame<raw->frames;frame++ ){
              cptr[frame] /= c_avg_num[cndx];
            }
          }
        }

        // subtract DC offset from average comparator signals
        for ( int cndx=0;cndx < regionXSize*4;cndx++ )
        {
          float *cptr;
          float dc = 0.0f;

          // get a pointer to where we will build the comparator signal average
          cptr = comparator_sigs + cndx*raw->frames;

          for (int frame=0;frame<raw->frames;frame++ )
            dc += cptr[frame];

          dc /= raw->frames;

          // subtract dc offset
          for (int frame=0;frame<raw->frames;frame++ )
            cptr[frame] -= dc;
        }

        // now figure out which pair of signals go together
        // this function also combines pairs of signals accordingly
        // from this point forward, there are only raw->cols*2 signals to deal with
        phase = DiscoverComparatorPhase(comparator_sigs,c_avg_num,regionXSize*4,raw->frames);

        if(phase == -1){
//          fprintf (stdout, "Comparator Noise Correction skipped\n");
          continue;
        }

        // mask comparators that don't contain any un-pinned pixels
        for ( int cndx=0;cndx < regionXSize*2;cndx++ )
        {
          if ( c_avg_num[cndx] == 0 )
          {
            comparator_mask[cndx] = 1;
            continue;
          }
        }

        // now neighbor-subtract the comparator signals
        NNSubtractComparatorSigs(comparator_noise,comparator_sigs,comparator_mask, 1, regionXSize*2,raw->frames);

        // measure noise in the neighbor-subtracted signals
        CalcComparatorSigRMS(comparator_rms,comparator_noise,regionXSize*2,raw->frames);

        // find the noisiest 10%
        MaskIQR(comparator_mask,comparator_rms,regionXSize*2);

        // neighbor-subtract again...avoiding noisiest 10%
        NNSubtractComparatorSigs(comparator_noise,comparator_sigs,comparator_mask,1,regionXSize*2,raw->frames);

        // measure noise in the neighbor-subtracted signals
        CalcComparatorSigRMS(comparator_rms,comparator_noise,regionXSize*2,raw->frames);

        // reset comparator_mask
        memset(comparator_mask,0,sizeof(comparator_mask));
        for ( int cndx=0;cndx < regionXSize*2;cndx++ )
        {
          if ( c_avg_num[cndx] == 0 )
          {
            comparator_mask[cndx] = 1;
          }
        }
        MaskIQR(comparator_mask,comparator_rms,regionXSize*2, verbose);

        // neighbor-subtract again...avoiding noisiest 10%
        NNSubtractComparatorSigs(comparator_noise,comparator_sigs,comparator_mask,1,regionXSize*2,raw->frames);

        for ( int cndx=0;cndx < regionXSize*2;cndx++ )
        {
          float *cptr;

          if ( c_avg_num[cndx] == 0 ) {
            // get a pointer to where we will build the comparator signal average
            cptr = comparator_sigs + cndx*raw->frames;
            memset(cptr,0,sizeof(float[raw->frames]));
          }
        }

        // now subtract each neighbor-subtracted comparator signal from the
        // pixels that are connected to that comparator
        for ( int y=0;y<regionYSize;y++ ) {
          for(int x=0;x<regionXSize;x++ ) {
            int imgInd = raw->cols * (y+pRow*regionYSize) + x + pCol*regionXSize;

            // if this pixel is pinned..skip it
            if ( (( *mask ) [imgInd] & MaskPinned)==0 )
            {
              // figure out which comparator this pixel belongs to
              int cndx = 2*x;
              if (( (y&0x3) == (0+phase) ) || ( (y&0x3) == (1+phase) ))
                  cndx++;

              //only perform correction on noisy comparators;
              if(comparator_mask[cndx]){
                // get a pointer to where we will build the comparator signal average
                float *cptr = comparator_noise + cndx*raw->frames;
                // subtract nn comparator signal from this pixel's data
                for ( int frame=0;frame<raw->frames;frame++ )
                  raw->image[frame*raw->frameStride+imgInd] -= cptr[frame];
              }
            }
          }
        }
    }
  }



  delete [] comparator_noise;
  delete [] comparator_sigs;
  MemUsage ( "After Comparator Noise Correction" );
  time_t cnc_end;
  time ( &cnc_end );

  fprintf (stdout, "Comparator Noise Correction: %0.3lf sec.\n", difftime(cnc_end, cnc_start));
}


int ComparatorNoiseCorrector::DiscoverComparatorPhase(float *psigs,int *c_avg_num,int n_comparators,int nframes)
{
  float phase_rms[2];
  int phase;

  for ( phase = 0;phase < 2;phase++ )
  {
    phase_rms[phase] = 0.0f;
    int rms_num = 0;

    for ( int i=0;i < n_comparators;i+=4 )
    {
      float *cptr_1a;
      float *cptr_1b;
      float *cptr_2a;
      float *cptr_2b;
      float rms_sum = 0.0f;

      // have to skip any columns that have all pinned pixels in any subset-average
//      if (( c_avg_num[i] == 0 ) && ( c_avg_num[i] == 1 ) && ( c_avg_num[i] == 2 ) && ( c_avg_num[i] == 3 ))
      if (( c_avg_num[i] == 0 ) && ( c_avg_num[i + 1] == 0 ) && ( c_avg_num[i + 2] == 0 ) && ( c_avg_num[i + 3] == 0 )){
//        fprintf (stdout, "Noisy column: %d; Comparator: %d.\n", i/4, i&0x3);
        continue;
      }

      // get a pointers to the comparator signals
      if ( phase==0 ) {
        cptr_1a = psigs + (i+2)*nframes;
        cptr_1b = psigs + (i+3)*nframes;
        cptr_2a = psigs + (i+0)*nframes;
        cptr_2b = psigs + (i+1)*nframes;
      }
      else
      {
        cptr_1a = psigs + (i+0)*nframes;
        cptr_1b = psigs + (i+3)*nframes;
        cptr_2a = psigs + (i+1)*nframes;
        cptr_2b = psigs + (i+2)*nframes;
      }

      for ( int frame=0;frame < nframes;frame++ )
      {
        rms_sum += (cptr_1a[frame]-cptr_1b[frame])*(cptr_1a[frame]-cptr_1b[frame]);
        rms_sum += (cptr_2a[frame]-cptr_2b[frame])*(cptr_2a[frame]-cptr_2b[frame]);
      }
      phase_rms[phase] += rms_sum;
      rms_num++;
    }

    //make them comparable between different runs
    if(rms_num != 0){
        phase_rms[phase] /= (2*rms_num);
    }
  }
  
  if (phase_rms[0] == 0 || phase_rms[1] == 0){
    return -1; //special tag to indicate case of 0 rms
  }

  if ( phase_rms[0] < phase_rms[1] )
    phase = 0;
  else
    phase = 1;

  //get phase_rms values to check how reliable it is
//  fprintf (stdout, "Phase: %d; RMS Phase Calcs = %f vs %f\n", phase, phase_rms[0], phase_rms[1]);

  // now combine signals according to the detected phase
  int cndx=0;
  for ( int i=0;i < n_comparators;i+=4 )
  {
    int ndx[4];
    float *cptr_1a;
    float *cptr_1b;
    float *cptr_2a;
    float *cptr_2b;
    int num_1a,num_1b,num_2a,num_2b;
    float *cptr_1;
    float *cptr_2;
    int num1;
    int num2;
    float scale1;
    float scale2;

    // get a pointers to the comparator signals
    if ( phase==0 ) {
      ndx[0] = i+2;
      ndx[1] = i+3;
      ndx[2] = i+0;
      ndx[3] = i+1;
    }
    else
    {
      ndx[0] = i+0;
      ndx[1] = i+3;
      ndx[2] = i+1;
      ndx[3] = i+2;
    }
    cptr_1a = psigs + ndx[0]*nframes;
    cptr_1b = psigs + ndx[1]*nframes;
    cptr_2a = psigs + ndx[2]*nframes;
    cptr_2b = psigs + ndx[3]*nframes;
    num_1a = c_avg_num[ndx[0]];
    num_1b = c_avg_num[ndx[1]];
    num_2a = c_avg_num[ndx[2]];
    num_2b = c_avg_num[ndx[3]];

    num1 = num_1a+num_1b;
    num2 = num_2a+num_2b;

    cptr_1 = psigs + (cndx+0)*nframes;
    cptr_2 = psigs + (cndx+1)*nframes;

    if ( num1 > 0 )
      scale1 = 1.0f/((float)num1);
    else
      scale1 = 0.0f;

    if ( num2 > 0 )
      scale2 = 1.0f/((float)num2);
    else
      scale2 = 0.0f;

    for ( int frame=0;frame < nframes;frame++ )
    {
      // beware...we are doing this in place...need to be careful
      float sum1 = scale1*(cptr_1a[frame]*num_1a+cptr_1b[frame]*num_1b);
      float sum2 = scale2*(cptr_2a[frame]*num_2a+cptr_2b[frame]*num_2b);

      cptr_1[frame] = sum1;
      cptr_2[frame] = sum2;
    }

    c_avg_num[cndx+0] = num1;
    c_avg_num[cndx+1] = num2;
    cndx+=2;
  }

  return phase;
}

// now neighbor-subtract the comparator signals
void ComparatorNoiseCorrector::NNSubtractComparatorSigs(float *pnn,float *psigs,int *mask,int span,int n_comparators,int nframes)
{
  float nn_avg[nframes];

  for ( int i=0;i < n_comparators;i++ )
  {
    int nn_cnt=0;
    float *cptr;
    float *nncptr;
    float centroid = 0.0f;
    int i_c0 = i & ~0x1;
    memset(nn_avg,0,sizeof(nn_avg));
    
    // rounding down the starting point and adding one to the rhs properly centers
    // the neighbor average about the central column...except in cases where columns are
    // masked within the neighborhood.

    //same column but the other comparator
    int offset[2] = {1, 0};
    int theOtherCompInd = i_c0 + offset[i-i_c0];
    if(!mask[theOtherCompInd]){
        // get a pointer to the comparator signal
        cptr = psigs + theOtherCompInd *nframes;

        // add it to the average
        for ( int frame=0;frame < nframes;frame++ )
          nn_avg[frame] += cptr[frame];

        nn_cnt++;
        centroid += theOtherCompInd;
    }

    for(int s = 1, cndx = 0; s <= span; s++){
      //i_c0 is even number
      //odd
      if(!(i_c0 - 2*s + 1 < 0  || i_c0 + 2*s + 1 >= n_comparators || mask[i_c0 - 2*s + 1] || mask[i_c0 + 2*s + 1])) {
          // get a pointer to the comparator signal
          cndx = i_c0 - 2*s + 1;
          cptr = psigs + cndx*nframes;
          // add it to the average
          for ( int frame=0;frame < nframes;frame++ )
            nn_avg[frame] += cptr[frame];
          nn_cnt++;
          centroid += cndx;
          cndx = i_c0 + 2*s + 1;
          cptr = psigs + cndx*nframes;
          // add it to the average
          for ( int frame=0;frame < nframes;frame++ )
            nn_avg[frame] += cptr[frame];
          nn_cnt++;
          centroid += cndx;
      }

      //even, symmetric
      if(!(i_c0 - 2*s < 0  || i_c0 + 2*s >= n_comparators || mask[i_c0 - 2*s] || mask[i_c0 + 2*s])) {
          cndx = i_c0 - 2*s;
          cptr = psigs + cndx*nframes;
          // add it to the average
          for ( int frame=0;frame < nframes;frame++ )
            nn_avg[frame] += cptr[frame];
          nn_cnt++;
          centroid += cndx;
          cndx = i_c0 + 2*s;
          cptr = psigs + cndx*nframes;
          // add it to the average
          for ( int frame=0;frame < nframes;frame++ )
            nn_avg[frame] += cptr[frame];
          nn_cnt++;
          centroid += cndx;
      }
    }

    if (( nn_cnt > 0 ) )
    {
      for ( int frame=0;frame < nframes;frame++ )
        nn_avg[frame] /= nn_cnt;

      // now subtract the neighbor average
      cptr = psigs + i*nframes;
      nncptr = pnn + i*nframes;
      for ( int frame=0;frame < nframes;frame++ )
        nncptr[frame] = cptr[frame] - nn_avg[frame];
    }
    else
    {
//      fprintf (stdout, "Default noise of 0 is set: %d\n", i);
      // not a good set of neighbors to use...just blank the correction
      // signal and do nothing.
      nncptr = pnn + i*nframes;
      for ( int frame=0;frame < nframes;frame++ )
        nncptr[frame] = 0.0f;
    }
  }
}

// measure noise in the neighbor-subtracted signals
void ComparatorNoiseCorrector::CalcComparatorSigRMS(float *prms,float *pnn,int n_comparators,int nframes)
{
  for ( int i=0;i < n_comparators;i++ )
  {
    float *cptr;
    float rms_sum = 0.0f;

    // get a pointer to the comparator signal
    cptr = pnn + i*nframes;

    // add it to the average
    for ( int frame=0;frame < nframes;frame++ )
      rms_sum += cptr[frame]*cptr[frame];

    prms[i] = sqrt(rms_sum/nframes);
//    fprintf (stdout, "RMS of Comparator %d: %f\n", i, prms[i]);
  }
}

// find the noisiest 10%
void ComparatorNoiseCorrector::MaskAbove90thPercentile(int *mask,float *prms,int n_comparators)
{
  float rms_sort[n_comparators];
  int i;

  memcpy(rms_sort,prms,sizeof(rms_sort));

  // sort the top 10%
  for ( i=0;i < (n_comparators/10);i++ )
  {
    for ( int j=i;j < n_comparators;j++ )
    {
      if ( rms_sort[j] > rms_sort[i] )
      {
        float tmp = rms_sort[j];
        rms_sort[j] = rms_sort[i];
        rms_sort[i] = tmp;
      }
    }
  }

  float rms_thresh = rms_sort[i-1];

//  printf("**************************** comparator noise threshold = %f\n",rms_thresh);

  for ( i=0;i < n_comparators;i++ )
  {
    if ( prms[i] >= rms_thresh )
      mask[i] = 1;
  }
}

// find the noisiest 10%
void ComparatorNoiseCorrector::MaskIQR(int *mask,float *prms,int n_comparators, bool verbose)
{
  float rms_sort[n_comparators];
  int i;

  memcpy(rms_sort,prms,sizeof(rms_sort));

  std::sort(rms_sort, rms_sort+n_comparators);

  float rms_thresh = rms_sort[n_comparators * 3 / 4 - 1] + 2.5 * (rms_sort[n_comparators * 3/4 - 1] - rms_sort[n_comparators * 1/4 - 1]) ;

  int noisyCount = 0;
  if(verbose)
    fprintf (stdout, "Noisy comparators:");
  for ( i=0;i < n_comparators;i++ )
  {
    if ( prms[i] >= rms_thresh ){
      mask[i] = 1;
      noisyCount ++;
      if(verbose)
        fprintf (stdout, " %d", i);
    }
  }
  if(verbose)
    fprintf (stdout, "\n");
//  fprintf (stdout, "\n%d noisy comparators; threshold: %f\n", noisyCount, rms_thresh);
}


