/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#ifndef LEVMARFITTER_H
#define LEVMARFITTER_H

#include <string.h>
#include <stdlib.h>
#include <float.h>

// some of the code uses <complex.h>, and in <complex.h> 'I' is defined and this 
// interferes w/ lapackpp.  I undef it here in case anyone above has included <complex.h>
#undef I

#include <lapackpp.h>

// base class for fitting algorithms
class LevMarFitter
{
protected:
	LevMarFitter(): len(0), x(NULL), residual(0.0), dp(NULL), residualWeight(NULL),
        nparams(0), param_max(NULL), param_min(NULL), lambda(0.0) {
    }

    ~LevMarFitter() {
        delete [] residualWeight;
		delete [] dp;
    }

    void Initialize(int _nparams,int _len,float *_x)
    {
        nparams = _nparams;
        len = _len;
        x = _x;

        // make all matricies the correct size
        jac.resize(len,nparams);
        jtj.resize(nparams,nparams);
        rhs.resize(nparams);
        delta.resize(nparams);

        dp = new float[_nparams];
        for(int i=0;i<_nparams;i++)
            dp[i] = 0.001;

        residualWeight = new float[len];
        for(int i=0;i<len;i++)
            residualWeight[i] = 1.0f;
    }

    // evaluate the fitted function w/ the specified parameters
    virtual void Evaluate(float *y,float *params) = 0;

    void SetParamMax(float *_param_max) {param_max = _param_max;}
    void SetParamMin(float *_param_min) {param_min = _param_min;}

    virtual float CalcResidual(float *refVals, float *testVals, int numVals, LaVectorDouble *err_vec = NULL) {
        double r = 0.0;

        if (err_vec)
            for (int i=0;i < numVals;i++)
                r += pow((*err_vec)(i) = residualWeight[i] * (refVals[i] - testVals[i]), 2);
        else
            for (int i=0;i < numVals;i++)
                r += pow(residualWeight[i] * (refVals[i] - testVals[i]),2);

        r /= numVals;
        return r;
    }

    // generic grid search
    void GridSearch(int steps,float *y,float *params)
    {
        // if we were never configured with min/max parameter values, just return
        // we only allow grid search if the region in which to search has been defined
        if ((param_min == NULL) || (param_max == NULL))
            return;

        float param_step[nparams];
        float p[nparams];

        // calculate step size for each parameter
        for (int pn=0;pn < nparams;pn++)
        {
            param_step[pn] = (param_max[pn] - param_min[pn])/(steps-1);
            p[pn] = param_min[pn];
        }

        int step_num[nparams];
        memset(step_num,0,sizeof(step_num));

        int inum;
        int total_steps;
        int digit;
        float *fval = new float[len];
        float min_err = FLT_MAX;
        float r1;

        total_steps = 1;
        for (int i=0;i < nparams;i++)
            total_steps *= steps;

        for (inum = 0;inum < total_steps;inum++)
        {
            // convert to baseN (where N==steps).  Each 'digit' of inum in baseN corresponds to the
            // step position of a parameter
            int inum_tmp = inum;
            int place_val = total_steps/steps;
            for (digit=nparams-1;digit >= 0;digit--)
            {
                int val = inum_tmp / place_val;
                inum_tmp -= val * place_val;
                p[digit] = param_min[digit]+param_step[digit]*val;
                place_val /= steps;
            }

            Evaluate(fval,p);
            r1 = CalcResidual(y, fval, len);

            if (r1 < min_err)
            {
                memcpy(params,p,sizeof(p));
                min_err = r1;
            }
        }

        delete [] fval;
    }

    // main fit entry-point
    int Fit(int max_iter, float *y, float *params, float *std_err = NULL)
    {
        int iter=0;

        if(y==NULL)
            return(iter);

        int done_cnt = 0;
        float lambda = 1.0;
        float *fval = new float[len];
        float *tmp = new float[len];
        float params_new[nparams];
        float r1 = FLT_MAX;
        float r2;
        LaVectorDouble  err_vect(len);

        while((iter < max_iter) && (done_cnt < 5))
        {
            // evaluate where we are
            Evaluate(fval,params);

            // calculate error bw function and data
            r1 = CalcResidual(y, fval, len, &err_vect);

            // evaluate the partial derivatives w.r.t. each parameter
            memcpy(params_new,params,sizeof(float[nparams]));
            for (int i=0;i < nparams;i++)
            {
                // adjust parameter
                params_new[i] += dp[i];

                // re-evaluate function
                Evaluate(tmp,params_new);

                // store in jacobian
                for (int j=0;j < len;j++)
                    jac(j,i) = residualWeight[j] * (tmp[j]-fval[j]) / dp[i];

                // put param back
                params_new[i] = params[i];
            }

            // calculate jtj matrix
            Blas_R1_Update(jtj,jac,1.0,0.0,false);

            // modify w/ lambda parameter
            for (int i=0;i < nparams;i++)
                jtj(i,i) *= (1.0 + lambda);

            // calculate rhs
            Blas_Mat_Trans_Vec_Mult(jac,err_vect,rhs,1.0,0.0);

            // solve for delta
            try {
                  LaLinearSolve(jtj,delta,rhs);
            }
            catch (LaException le) {
                delta.resize(nparams);
                delta = 0.0;
            }

            for (int i=0;i < nparams;i++)
            {
                // adjust parameter
                params_new[i] += delta(i);

                // apply limits if necessary
                if (param_max) params_new[i] = (params_new[i] > param_max[i] ? param_max[i] : params_new[i]);
                if (param_min) params_new[i] = (params_new[i] < param_min[i] ? param_min[i] : params_new[i]);

                // re-calculate error
                Evaluate(tmp,params_new);

                // calculate error bw function and data
                r2 = CalcResidual(y, tmp, len);

                if (r2 < r1)
                {
                    lambda /= 10.0;
                    memcpy(params,params_new,sizeof(float[nparams]));
                    done_cnt = 0;
                }
                else
                {
                    lambda *= 10.0;
                    done_cnt++;
                }
            }

            iter++;
        }

        delete [] fval;
        delete [] tmp;

        residual = r1;

        // compute parameter std errs
        if (std_err)
        {
            LaSymmMatDouble std_err_jtj(nparams, nparams);
            Blas_R1_Update(std_err_jtj, jac, 1.0, 0.0, false);

            LaVectorLongInt piv;
            piv.resize(nparams, nparams);

            LaGenMatDouble std_err_jtj_inv = std_err_jtj;
            LUFactorizeIP(std_err_jtj_inv, piv);
            LaLUInverseIP(std_err_jtj_inv, piv);

            double mrv = (residual * len) / (len - nparams); // mean residual variance
            std_err_jtj_inv *= mrv;

            for (int i=0;i < nparams;i++)
            	std_err[i] = sqrt(std_err_jtj_inv(i, i));
        }

        return(iter);
    }

protected:
    int len;
    float *x;
    float residual;
    float *dp;
    float *residualWeight;
    int nparams;
    float *param_max;
    float *param_min;

public:

private:
    float lambda;
    LaGenMatDouble  jac;
    LaSymmMatDouble jtj;
    LaVectorDouble  rhs;
    LaVectorDouble  delta;
};





#endif // LEVMARFITTER_H

