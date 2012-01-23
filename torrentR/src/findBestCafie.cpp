/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#include <Rcpp.h>
#include "RawWells.h"
#include "CafieSolver.h"

RcppExport SEXP findBestCafie(
  SEXP measured_in,
  SEXP flowOrder_in,
  SEXP keyFlow_in,
  SEXP trueSeq_in,
  SEXP known_cf_in,
  SEXP known_ie_in,
  SEXP known_dr_in,
  SEXP analysisMode_in,
  SEXP nKeyFlow_in,
  SEXP doKeyNorm_in,
  SEXP doScale_in,
  SEXP hpSignal_in,
  SEXP sigMult_in
) {

    SEXP rl = R_NilValue; 		// Use this when there is nothing to be returned.
    char *exceptionMesg = NULL;
	char *flowOrder = NULL;
	char *trueSeq = NULL;
	int *keyFlow = NULL;
	double *hpSignal = NULL;

    try {

	RcppMatrix<double> measured_temp(measured_in);
	const char *       flowOrder_c    = Rcpp::as<const char *>(flowOrder_in);
	RcppVector<int>    keyFlow_temp(keyFlow_in);
	const char *       trueSeq_c      = Rcpp::as<const char *>(trueSeq_in);
	double             known_cf       = Rcpp::as<double>(known_cf_in);
	double             known_ie       = Rcpp::as<double>(known_ie_in);
	double             known_dr       = Rcpp::as<double>(known_dr_in);
	const char *       analysisMode   = Rcpp::as<const char *>(analysisMode_in);
	int                nKeyFlow       = Rcpp::as<int>(nKeyFlow_in);
	int                doKeyNorm      = Rcpp::as<int>(doKeyNorm_in);
	int                doScale        = Rcpp::as<int>(doScale_in);
	RcppVector<double> hpSignal_temp(hpSignal_in);
	double             sigMult        = Rcpp::as<double>(sigMult_in);

	int nWell = measured_temp.rows();
	int nFlow = measured_temp.cols();
	int flowOrderLen = strlen(flowOrder_c);
	int trueSeqLen = strlen(trueSeq_c);

	flowOrder = new char[flowOrderLen];
	strcpy(flowOrder,flowOrder_c);
	trueSeq = new char[trueSeqLen];
	strcpy(trueSeq,trueSeq_c);
	keyFlow = new int[keyFlow_temp.size()];
	for(int i=0; i<keyFlow_temp.size(); i++) {
	    keyFlow[i] = keyFlow_temp(i);
	}
	int nHpSignal = hpSignal_temp.size();
	hpSignal = new double[nHpSignal];
	for(int i=0; i<nHpSignal; i++)
	    hpSignal[i] = hpSignal_temp(i);

	if(flowOrderLen < nFlow) {
	    exceptionMesg = copyMessageToR("Flow order should be at least the same length as nFlow");
	} else if(nHpSignal < MAX_MER) {
	    exceptionMesg = copyMessageToR("hpSignal is too short");
	} else if((trueSeqLen <= 0) & (!strcmp(analysisMode,"knownSeq"))) {
	    // Maybe we should we be testing something more stringent than simply trueSeqLen > 0?
	    exceptionMesg = copyMessageToR("True sequence must have length > 0");
	} else {
	    // Initialize the sovler object
	    CafieSolver solver;
	    solver.SetFlowOrder(flowOrder);
	    double *measured = new double[nFlow];
	    RcppVector<double> caf(nWell);
	    RcppVector<double> ie(nWell);
	    RcppVector<double> dr(nWell);
	    RcppVector<double> err(nWell);
	    RcppMatrix<int>    call(nWell,nFlow);
	    RcppMatrix<double> predicted(nWell,nFlow);
	    RcppVector<double> multiplier(nWell);
	    for(int well=0; well<nWell; well++) {
	    	solver.SetCAFIE(0.0, 0.0);
		for(int flow=0; flow<nFlow; flow++)
	  	    measured[flow] = measured_temp(well,flow);
		solver.SetMeasured(nFlow, measured);
		if(doKeyNorm)
		    solver.Normalize(keyFlow, nKeyFlow, 0, false);
		double *normalized = (double *)solver.GetMeasured();

		// Prepare for a call to Solve
		if(!strcmp(analysisMode,"knownSeq")) {
		    solver.SetTestSequence(trueSeq);
		    err(well) = solver.FindBestCAFIE(normalized, nFlow, false, 0.0, hpSignal, nHpSignal, sigMult);
		    caf(well) = solver.CAF();
		    ie(well)  = solver.IE();
		    dr(well)  = solver.DR();
		} else if(!strcmp(analysisMode,"knownCAFIE")) {
		    solver.SetCAFIE(known_cf, known_ie);
		    solver.SetDroop(known_dr);
		} else {
		    exceptionMesg = copyMessageToR("analysisMode should be either knownSeq or knownCAFIE");
		}

		// Make the call to Solve
		bool doDotFixes = true;
		solver.Solve(3, hpSignal, nHpSignal, sigMult, doScale, doDotFixes);

		// Store quantities of interest after the call to Solve
		for(int flow=0; flow<nFlow; flow++) {
	          call(well,flow)      = solver.GetPredictedExtension(flow);
	          predicted(well,flow) = solver.GetPredictedResult(flow);
	          multiplier(well)     = solver.GetMultiplier();
		}
	    }
	    delete [] measured;

	    // Build result set to be returned as a list to R.
	    RcppResultSet rs;
	    rs.add("call",                call);
	    rs.add("predicted",           predicted);
	    rs.add("multiplier",          multiplier);
	    if(!strcmp(analysisMode,"knownSeq")) {
		rs.add("carryForward",        caf);
		rs.add("incompleteExtension", ie);
		rs.add("droop",               dr);
		rs.add("err",                 err);
	    }

	    // Get the list to be returned to R.
	    rl = rs.getReturnList();
	}
    delete [] flowOrder;
    delete [] trueSeq;
	delete [] keyFlow;
	delete [] hpSignal;

    } catch(std::exception& ex) {
	exceptionMesg = copyMessageToR(ex.what());
    } catch(...) {
	exceptionMesg = copyMessageToR("unknown reason");
    }
    
    if(exceptionMesg != NULL)
	Rf_error(exceptionMesg);

    return rl;
}
