/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#ifndef WORKERINFOQUEUE_H
#define WORKERINFOQUEUE_H

#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <time.h>
#include <stdlib.h>
#include <math.h>
#include <libgen.h>
#include <limits.h>
#include <signal.h>
#include <vector>
#include <algorithm>
#include <limits>
#include <numeric>
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <armadillo>


struct WorkerInfoQueueItem
{
    bool finished;
    void *private_data;
};

// helper class to distribute work items to a set of threads for processing
// add class access is thread safe
class WorkerInfoQueue
{
public:
    // create a queue w/ that can hold the specified number of items
    WorkerInfoQueue(int _depth)
    {
        depth = _depth;
        rdndx = 0;
        wrndx = 0;
        num = 0;
        not_done_cnt = 0;
        qlist = new WorkerInfoQueueItem[depth];

        pthread_mutex_init(&lock, NULL);
        pthread_cond_init(&rdcond,NULL);
        pthread_cond_init(&wrcond,NULL);
        pthread_cond_init(&donecond,NULL);
    }

    // put a new item on the queue.  this will block if the queue is full
    void PutItem(WorkerInfoQueueItem &new_item)
    {
        // obtain the lock
        pthread_mutex_lock(&lock);

        // wait for someone to signal new free space
        while (num >= depth)
            pthread_cond_wait(&wrcond,&lock);

        qlist[wrndx] = new_item;
        if (++wrndx >= depth) wrndx = 0;
        num++;
        not_done_cnt++;

        // signal readers to check for the new item
        pthread_cond_signal(&rdcond);

        // give up the lock
        pthread_mutex_unlock(&lock);
    }

    // remove and item from the queue.  this will block if the queue is empty
    WorkerInfoQueueItem GetItem(void)
    {
        WorkerInfoQueueItem item;

        // obtain the lock
        pthread_mutex_lock(&lock);

        // wait for someone to signal a new item
        while (num == 0)
            pthread_cond_wait(&rdcond,&lock);

        item = qlist[rdndx];
        if (++rdndx >= depth) rdndx = 0;
        num--;

        // signal writers that more free space is available
        pthread_cond_signal(&wrcond);

        // give up the lock
        pthread_mutex_unlock(&lock);

        return(item);
    }

    // NOTE: just because the q is empty...doesn't mean the workers are done with the
    // last item they pulled off.  Worker's decrement the 'not done' count whenever they
    // finish a work item.  This waits till all the work items have been completed
    void WaitTillDone(void)
    {
        // obtain the lock
        pthread_mutex_lock(&lock);

        // wait for someone to signal new free space
        while (not_done_cnt > 0)
            pthread_cond_wait(&donecond,&lock);

        // give up the lock
        pthread_mutex_unlock(&lock);
    }

    // Allows workers to indicate that they have completed a task
    void DecrementDone(void)
    {
        // obtain the lock
        pthread_mutex_lock(&lock);

        // decrement done count
        not_done_cnt--;

        // if everything is done, signal the condition change
        if (not_done_cnt == 0)
            pthread_cond_signal(&donecond);

        // give up the lock
        pthread_mutex_unlock(&lock);
    }

    ~WorkerInfoQueue()
    {
        pthread_cond_destroy(&donecond);
        pthread_cond_destroy(&wrcond);
        pthread_cond_destroy(&rdcond);
        pthread_mutex_destroy(&lock);
        delete [] qlist;
    }

private:
    int rdndx;
    int wrndx;
    int num;
    int depth;
    int not_done_cnt;
    WorkerInfoQueueItem *qlist;

    // synchronization objects
    pthread_mutex_t lock;
    pthread_cond_t wrcond;
    pthread_cond_t rdcond;
    pthread_cond_t donecond;
};

class DynamicWorkQueueGpuCpu {

public:

    // create a queue w/ that can hold the specified number of items
    DynamicWorkQueueGpuCpu(int _depth)
    {
        start = false;
        depth = _depth;
        gpuRdIdx = 0;
        cpuRdIdx = depth - 1;
        wrIdx = 0;
        not_done_cnt = 0;
        qlist = new WorkerInfoQueueItem[depth];

        pthread_mutex_init(&lock, NULL);
        pthread_cond_init(&startcond,NULL);
        pthread_cond_init(&donecond,NULL);
    }


    WorkerInfoQueueItem GetGpuItem() {

        WorkerInfoQueueItem item;

        pthread_mutex_lock(&lock);
        //printf("Acquiring lock gpu\n");    


        while (!start)
            pthread_cond_wait(&startcond, &lock);
    
        if (gpuRdIdx == cpuRdIdx)
            start = false;

        //printf("Getting Gpu Item, GpuIdx: %d CpuIdx: %d, start: %d\n", gpuRdIdx, cpuRdIdx, start); 
        item = qlist[gpuRdIdx++];
            
        //printf("Releasing lock gpu\n");    
        pthread_mutex_unlock(&lock);         

        return item;
    }

    WorkerInfoQueueItem GetCpuItem() {

        WorkerInfoQueueItem item;

        pthread_mutex_lock(&lock);
        
        //printf("Acquiring lock cpu\n");    


        while (!start)
            pthread_cond_wait(&startcond, &lock);
       
        if (cpuRdIdx == gpuRdIdx)
            start = false;
    
        //printf("Getting Cpu Item, GpuIdx: %d CpuIdx: %d, start: %d\n", gpuRdIdx, cpuRdIdx, start); 
        item = qlist[cpuRdIdx--];
        
        //printf("Releasing lock cpu\n");    
        pthread_mutex_unlock(&lock);         

        return item;
    }

    void PutItem(WorkerInfoQueueItem &new_item) {
	
       
        qlist[wrIdx++] = new_item;
        not_done_cnt++;
    
        //printf("Putting Item\n"); 
        if (wrIdx == depth) {
            pthread_mutex_lock(&lock);
            //printf("Signalling to start\n");
            start = true;
            pthread_cond_broadcast(&startcond); 
            pthread_mutex_unlock(&lock);
        }
           
    }


    // NOTE: just because the q is empty...doesn't mean the workers are done with the
    // last item they pulled off.  Worker's decrement the 'not done' count whenever they
    // finish a work item.  This waits till all the work items have been completed
    void WaitTillDone(void)
    {
        // obtain the lock
        pthread_mutex_lock(&lock);

        // wait for someone to signal new free space
        while (not_done_cnt > 0)
            pthread_cond_wait(&donecond,&lock);

        // give up the lock
        pthread_mutex_unlock(&lock);
    }

    // Allows workers to indicate that they have completed a task
    void DecrementDone(void)
    {
        // obtain the lock
        pthread_mutex_lock(&lock);

        // decrement done count
        not_done_cnt--;

        // if everything is done, signal the condition change
        if (not_done_cnt == 0) {
            start = false;
            pthread_cond_signal(&donecond);
        }

        // give up the lock
        pthread_mutex_unlock(&lock);
    }

    void ResetIndices() {
        pthread_mutex_lock(&lock);
        wrIdx = 0;
        gpuRdIdx = 0;
        cpuRdIdx = depth - 1;
        pthread_mutex_unlock(&lock);
    }

    int getGpuReadIndex() {
        return gpuRdIdx;
    }

    ~DynamicWorkQueueGpuCpu()
    {
        pthread_cond_destroy(&donecond);
        pthread_cond_destroy(&startcond);
        pthread_mutex_destroy(&lock);
        delete [] qlist;
    }


private:
    int gpuRdIdx;
    int cpuRdIdx;
    int wrIdx;
    int depth;
    int not_done_cnt;
    bool start;
    WorkerInfoQueueItem *qlist;
    
    // synchronization objects
    pthread_mutex_t lock;
    pthread_cond_t donecond;
    pthread_cond_t startcond;
};


/*
#ifndef __FRAME_OUTPUT_QUEUE_H
#define __FRAME_OUTPUT_QUEUE_H

#include <pthread.h>

struct frame_info
{
    int frameNumber;
    UINT8 *ptr;
    struct timeval timestamp;
    UINT32 frame_duration;
};

struct FrameOutputQueue
{
    struct frame_info *frames;
    int rd_ndx;
    int wr_ndx;
    int num;
    int nFrames;
    int acqFinished;

    pthread_mutex_t lock;
    pthread_cond_t wrcond;
    pthread_cond_t rdcond;
};

// Creates a new output queue large enough to hold numFrames
struct FrameOutputQueue *foq_Create(int numFrames);

// Destroys a FrameOutputQueue and free's the resources used by the control structures
void foq_Destroy(struct FrameOutputQueue *q);

// Puts a new frame into the queue.  Blocks if there isn't space for the new frame
void foq_PutFrame(struct FrameOutputQueue *q,int frameNum,struct timeval timestamp,UINT32 frame_duration,UINT8 *ptr);

// Gets the next frame from the queue.  Blocks if there aren't any new frames available
int foq_GetFrame(struct FrameOutputQueue *q,struct frame_info *pframe);

// indicate to readers that the acquisition is complete and no more frames should be
// expected
void foq_FinishAcquisition(struct FrameOutputQueue *q);

// Empty's the queue
void foq_Reset(struct FrameOutputQueue *q);

// Queries number of frames in the queue
int foq_GetNum(struct FrameOutputQueue *q);

#endif
 
 
 #include "datacollect_global.h"
#include "FrameOutputQueue.h"

#include "dbgmem.h"

// Creates a new output queue large enough to hold numFrames
struct FrameOutputQueue *foq_Create(int numFrames)
{
    struct frame_info *frames;
    struct FrameOutputQueue *q;

    q = (struct FrameOutputQueue *)malloc(sizeof(struct FrameOutputQueue));

    if (q == NULL)
        goto err0;

    frames = (struct frame_info *)malloc(sizeof(struct frame_info)*numFrames);

    if (frames == NULL)
        goto err1;

    q->frames = frames;

    if (pthread_mutex_init(&q->lock, NULL) != 0)
        goto err2;

    if (pthread_cond_init(&q->rdcond,NULL) != 0)
        goto err3;

    if (pthread_cond_init(&q->wrcond,NULL) != 0)
        goto err4;

    q->nFrames = numFrames;
    foq_Reset(q);

    return(q);

err4:
    pthread_cond_destroy(&q->rdcond);
err3:
    pthread_mutex_destroy(&q->lock);
err2:
    free(frames);
err1:
    free(q);
err0:
    return NULL;
}

// Destroys a FrameOutputQueue and free's the resources used by the control structures
void foq_Destroy(struct FrameOutputQueue *q)
{
    // technically...I should check here to see if anyone is blocked on these
    // things before destroying them...will fix this at some point
    pthread_cond_destroy(&q->wrcond);
    pthread_cond_destroy(&q->rdcond);
    pthread_mutex_destroy(&q->lock);
    free(q->frames);
    free(q);
}

// Puts a new frame into the queue.  Blocks if there isn't space for the new frame
void foq_PutFrame(struct FrameOutputQueue *q,int frameNum,struct timeval timestamp,UINT32 frame_duration,UINT8 *ptr)
{
    pthread_mutex_lock(&q->lock);

    while (q->num >= q->nFrames)
    {
        // wait for someone to signal new free space
        pthread_cond_wait(&q->wrcond,&q->lock);
    }

    q->frames[q->wr_ndx].frameNumber = frameNum;
    q->frames[q->wr_ndx].timestamp = timestamp;
    q->frames[q->wr_ndx].frame_duration = frame_duration;
    q->frames[q->wr_ndx].ptr = ptr;

    if (++(q->wr_ndx) >= q->nFrames) q->wr_ndx = 0;
    q->num++;

    // signal readers to check for the new frame
    pthread_cond_signal(&q->rdcond);

    pthread_mutex_unlock(&q->lock);
}

// Gets the next frame from the queue.  Blocks if there aren't any new frames available
int foq_GetFrame(struct FrameOutputQueue *q,struct frame_info *pframe)
{
    int nrcv = 0;

    pthread_mutex_lock(&q->lock);

    while ((q->num <= 0) && (q->acqFinished == 0))
    {
        // wait for someone to signal new frame
        pthread_cond_wait(&q->rdcond,&q->lock);
    }

    // if there was a new frame available, get the info
    if (q->num > 0)
    {
        pframe->frameNumber = q->frames[q->rd_ndx].frameNumber;
        pframe->timestamp = q->frames[q->rd_ndx].timestamp;
        pframe->ptr = q->frames[q->rd_ndx].ptr;
        pframe->frame_duration = q->frames[q->rd_ndx].frame_duration;

        if (++(q->rd_ndx) >= q->nFrames) q->rd_ndx = 0;
        q->num--;

        // signal new free space to writers
        pthread_cond_signal(&q->wrcond);

        nrcv = 1;
    }

    pthread_mutex_unlock(&q->lock);

    // if we return 0, it means there aren't any more frames available
    // and the acqusition has finished...so don't expect any more
    return nrcv;
}

// indicate to readers that the acquisition is complete and no more frames should be
// expected
void foq_FinishAcquisition(struct FrameOutputQueue *q)
{
    pthread_mutex_lock(&q->lock);

    q->acqFinished = 1;
    pthread_cond_signal(&q->rdcond);

    pthread_mutex_unlock(&q->lock);
}

// Empty's the queue
void foq_Reset(struct FrameOutputQueue *q)
{
    pthread_mutex_lock(&q->lock);

    q->acqFinished = q->rd_ndx = q->wr_ndx = q->num = 0;

    pthread_mutex_unlock(&q->lock);
}

// Queries number of frames in the queue
int foq_GetNum(struct FrameOutputQueue *q)
{
    int ret;

    pthread_mutex_lock(&q->lock);

    ret = q->num;

    pthread_mutex_unlock(&q->lock);

    return(ret);
}


*/

#endif // WORKERINFOQUEUE_H
