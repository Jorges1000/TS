/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#ifndef BEADSCRATCH_H
#define BEADSCRATCH_H


#include "BkgMagicDefines.h"
#include <stdio.h>
#include <string.h>
#include <float.h>
#include <stdlib.h>
#include <math.h>
#include "FlowBuffer.h"
#include "BeadParams.h"
#include "DiffEqModel.h"
#include "TimeCompression.h"
#include "MathOptim.h"
#include "RegionTracker.h"
#include "BkgTrace.h"


// hold temporary values for a bead
class BeadScratchSpace{
  public:
    // active bead parameters parallelized by flow
    incorporation_params_block_flows cur_bead_block;
    buffer_params_block_flows cur_buffer_block;
    // temporary storage for fitting algorithm used to hold
    // functional evaluation and partial derivative terms
    float   *scratchSpace;
    // pointer into the scratch location where the function evaluation is held
    float   *fval;
    // separate cache for incorporation trace
    float   *ival;
    // xtalk is held in this separate cache
    float   *cur_xtflux_block;
    // emphasis vector for all flows for this bead
    float   *custom_emphasis;
    float   custom_emphasis_scale[NUMFB];
    int WhichEmphasis[NUMFB]; // current emphasis indexing used in creating custom_emphasis
    // hold current traces for bead with whatever correction has been done
    float *observed;
    float *shifted_bkg;
    float cur_shift; // cached tshift for checking if we're current


    // some buffer sizes for mnemonic purposes
    int   bead_flow_t;
    int   npts; // number of time points from time-compression
    
    BeadScratchSpace();
    ~BeadScratchSpace();
    void Allocate(int npts,int num_derivatives);
    void ResetXtalkToZero();
    void FillEmphasis(int *my_emphasis, float *source_emphasis[],float *source_emphasis_scale);
    void SetEmphasis(float *Ampl, int max_emphasis);
    void CreateEmphasis(float *source_emphasis[], float *source_emphasis_scale);
    void FillObserved(BkgTrace &my_trace,int ibd);
    void FillShiftedBkg(BkgTrace &my_trace, float tshift, bool force_fill);
    float CalculateFitError(float *per_flow_output, int numfb);
    void MultiFlowReturnResiduals(float *y_minus_f);
    void MultiFlowReturnFval(float *out, int numfb);
};



#endif // BEADSCRATCH_H
