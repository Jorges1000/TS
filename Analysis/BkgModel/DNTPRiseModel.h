/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#ifndef DNTPRISEMODEL_H
#define DNTPRISEMODEL_H

#include <string.h>
#include <stdlib.h>
#include <float.h>

#include "MathOptim.h"

#define MIN_PROC_THRESHOLD  (0.01)

// exportable math
int SigmaRiseFunction(float *output,int npts, float *frame_times, int sub_steps, float C, float t_mid_nuc,float sigma);
int SigmaXRiseFunction(float *output,int npts, float *frame_times, int sub_steps, float C, float t_mid_nuc,float sigma);
int SplineRiseFunction(float *output, int npts, float *frame_times, int sub_steps, float C, float t_mid_nuc, float sigma, float tangent_zero, float tangent_one);

class DntpRiseModel
{
public:
    // constructs an object that can compute the [DNTP] above the wells as a function of time
    // given:
    //  C: the [dNTP] in the reagent bottle
    //  _tvals: the time associated with each data point to compute
    //  _sub_steps: the number of steps to take between each time point
    //  _npts: the number of time points
    DntpRiseModel(int _npts,float _C, float *_tvals,int _sub_steps);

    // Computes [dNTP] as a function of time.  t_mid_nuc controls the starting point of the
    // [dNTP] change, and sigma indicates how blurred out in time the rise is
    // returns the first non-zero time point index
    int CalcCDntpTop(float *output,float t_mid_nuc,float sigma);
    int Geti_start(void) { return i_start; };

private:
    int npts;
    int sub_steps;
    float *tvals;
    float C;
    int i_start;
};


#endif // DNTPRISEMODEL_H



