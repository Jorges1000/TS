/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#ifndef RAWWELLS_H
#define RAWWELLS_H

#include <stdio.h>
#include <map>
#include <string>
#include <algorithm>
#include <vector>
#include <iostream>
#include "hdf5.h"
#include "Utils.h"

struct WellHeader {
  unsigned int numWells;
  unsigned short numFlows;
  char *flowOrder;
};

struct WellData {
  unsigned int rank;
  unsigned short x;
  unsigned short y;
  float *flowValues;
};

struct WellRank {
  int x;
  int y;
  double rqs;
};

/**
 * Utility class to wrap up some of the complications of an 
 * HDF5 Dataset. Ideally this will grow to part of a more general
 * utility framework for wrapping HDF5.
 */
class RWH5DataSet {

public:

  /** Constructor */
  RWH5DataSet();

  /** Destructor */
  ~RWH5DataSet();

  /** Close structures if open. */
  void Close();

  /** Initialize variables with empty state. */
  void Clear();

  static const int EMPTY = -1;
  std::string mGroup;  /**< Path to dataset in h5 file. */
  std::string mName;   /**< Name of dataset. */
  hid_t mDataset;      /**< H5 dataset handle */
  hid_t mDatatype;     /**< H5 data definition. */
  hid_t mDataspace;    /**< handles */
};


/** Utility class for specifying region of wells file to load. */
class WellChunk {
 public:
  WellChunk() {
    rowStart = rowHeight = colStart = colWidth = flowStart = flowDepth = 0;
  }

  size_t rowStart;
  size_t rowHeight;
  size_t colStart;
  size_t colWidth;
  size_t flowStart;
  size_t flowDepth;
};

/** 
 * Represents the cube of results 
 * Usages:
 * Writing wells flow by flow:
 * - Specify file name, rows, columns, etc.
 * - Open for write
 * - Fill in data for wells.
 * - Write out flows.
 * - close file
  // specify file name
  RawWells wells("1.wells")
  // Specify dimensions and flow order
  wells.SetCompression(3);
  wells.SetCols(numCols);
  wells.SetFlows(numFlows);
  wells.SetFlowOrder("TACG");

  // Set region we will be working with at first (keeps RAM usage to min)
  wells.SetChunk(0, rawWells.NumRows(), 0, rawWells.NumCols(), 0, N);
  wells.OpenForWrite() // open the file up for access
  for (chunks) {
     ...
     wells.Set(row,col,flow,value); // Many times set values of interest
     ...
     wells.WriteWells(); // incrementally writing current chunk
     // reset current region being worked on
     wells.SetChunk(0, rawWells.NumRows(), 0, rawWells.NumCols(), flowN, 60)
  }  
  // Write other portions of file of interest
  wells.WriteRanks();
  wells.WriteInfo();
  // Close the file and free hdf5 resources
  wells.Close();

 * Reading from wells one well at a time:
 * - Specify file name
 * - Open for read
 * - For each region, return next well or load next region
 * - close file
  RawWells wells("1.wells") // file to read from
  WellData data;
  wells.OpenForIncrementalRead(); // open file for reading a chunk at a time
  wells.ResetCurrentRegionWell(); // initialize iterator over wells
  while(!wells.ReadNextRegionData(&data)) {  
    ... // Something with data
  }
  wells.Close();

 * Reading from wells file chunk at a time:
 * - Specify file name
 * - Open for read
 * - Specify chunk
 * - Load chunk
 * - Access data as desired.
 * - close file.
  RawWells wells("1.wells") // file to read from
  wells.OpenForIncrementalRead(); // open file for reading a chunk at a time
  foreach (chunk) {
     wells.SetChunk(Y, N, X, N, 0, wells->NumFlows());
     wells.ReadWells();
     ...
     float f = wells.At(row, col, flow); // get flow value for row,column,flow tuple
     ...
  }
  wells.Close();

 */
class RawWells {

public:  

  /* Constructors. */
  RawWells(const char *experimentPath, const char *rawWellsName, int rows, int cols);
  RawWells(const char *experimentPath, const char *rawWellsName);
  RawWells(const char *wellsFilePath, int rows, int cols);

  /* Destructor. */ 
  ~RawWells();

  /* Initialization and setup. */
  void Init(const char *experimentPath, const char *rawWellsName, int rows, int col,  int flows);
  void CreateEmpty(int numFlows, const char *flowOrder, int rows, int cols);
  void CreateEmpty(int numFlows, const char *flowOrder);
  void SetRegion(int rowStart, int height, int colStart, int width);
  void GetRegion(int &rowStart, int &height, int &colStart, int &width);
  /** Set the current gzip chunk compression level (0-9 valid only. */
  void SetCompression(int level) { mCompression = level; }
  int GetCompression() { return mCompression; }

  /* Opening and closing file and subsets of file. */
  bool OpenMetaData();
  void SetSubsetToLoad(const std::vector<int32_t> &xSubset, const std::vector<int32_t> &ySubset);
  void SetSubsetToWrite(const std::vector<int32_t> &subset);
  void SetSubsetToLoad(int32_t *xSubset, int32_t *ySubset, int count);
  bool OpenForRead(bool dummyMemMap = false);
  void OpenForWrite();
  bool OpenForReadWrite();
  void WriteLegacyWells();
  void WriteToHdf5(const std::string &file);
  void WriteToHdf5() { WriteToHdf5(mFilePath); }
  void Close();

  /* Accessors */
  size_t NumRows() const { return mRows; }
  void SetRows(size_t rows) { mRows = rows; mChunk.rowStart = 0; mChunk.rowHeight = rows; }

  size_t NumCols() const { return mCols; }
  void SetCols(int cols) { mCols = cols; mChunk.colStart = 0; mChunk.colWidth = cols;}

  size_t NumWells() const { return NumRows() * NumCols(); }

  size_t NumFlows() const { return mFlows; }
  void SetFlows(size_t flows) { mFlows = flows; mChunk.flowStart = 0; mChunk.flowDepth = flows; }

  const char * FlowOrder() const { return mFlowOrder.c_str(); }
  void SetFlowOrder(const std::string &flowOrder);
    
  bool HaveWell(size_t row, size_t col) const { return mIndexes[ToIndex(col,row)] >= 0; }
  bool HaveWell(size_t well) const { return mIndexes[well] >= 0; }
  float At(size_t row, size_t col, size_t flow) const;
  /** well idx is based on row major order like c */
  float At(size_t well, size_t flow) const;
  /** Warning - Subsequent calls to this function will overwrite returned data pointed too */
  const WellData *ReadXY(int x, int y); 
  void Set(size_t row, size_t col, size_t flow, float val) { Set(ToIndex(col, row), flow, val); }
  void Set(size_t idx, size_t flow, float val);
  void WriteFlowgram(size_t flow, size_t x, size_t y, float val);

  void ResetCurrentWell() { mCurrentWell = 0; }
  void ResetCurrentRegionWell() { mCurrentRow = 0, mCurrentCol = -1, mCurrentRegionRow = 0, mCurrentRegionCol = 0; }

  /* Metadata accessors. */
  /** Get the value associated with a particular key, return false if key not present. */
  bool GetValue(const std::string &key, std::string &value)  const { return mInfo.GetValue(key, value); }
  
  /** 
   * Set the value associated with a particular key. Newer values for
   * same key overwrite previos values. */
  bool SetValue(const std::string &key, const std::string &value) { return mInfo.SetValue(key, value); }

  /** Get the key and the value associated at index. */
  bool GetEntry(int index, std::string &key, std::string &value) const { return mInfo.GetEntry(index, key, value); }

  /** Get the total count of key value pairs valid for GetEntry() */
  int GetCount() const { return mInfo.GetCount(); }

  /** Entry exists. */
  bool KeyExists(const std::string &key) const { return mInfo.KeyExists(key); }

  /** Empty out the keys, value pairs. */
  void Clear() { mInfo.Clear(); };

  void SetChunk(size_t rowStart, size_t rowHeight, 
                size_t colStart, size_t colWidth,
                size_t flowStart, size_t flowDepth);

  const WellChunk &GetChunk() const { return mChunk; }

  const WellData *ReadNextRegionData();
  bool ReadNextRegionData(WellData *_data);
  size_t GetNextRegionData();

  void WriteWells();
  void ReadWells();
  void OpenForIncrementalRead();
  void WriteRanks();
  void WriteInfo();

 private:
  bool InChunk(size_t row, size_t col);

  /* Conversion to and from row/col to index. */
  void ReadWell(int well, WellData *_data);
  uint64_t ToIndex(size_t x, size_t y) const { return y * NumCols() + x; }
  void IndexToXY(size_t index, unsigned short &x, unsigned short &y) const;
  void IndexToXY(size_t index, size_t &x, size_t &y) const;

  void InitIndexes();
  void CreateBuffers();
  bool WellsInSubset(uint32_t rowStart, uint32_t rowEnd, uint32_t colStart, uint32_t colEnd);

  bool OpenForReadLegacy();
  void CleanupHdf5();

  void WriteSubsetWells();
  uint64_t CheckWells();

  void OpenWellsForWrite();
  void OpenWellsToRead();

  void ReadWellsRegion();
  void ReadWellsSubset();
  void ReadRanks();
  void ReadInfo();

  void WriteStringVector(hid_t h5File, const std::string &name, const char **values, int numValues);
  void ReadStringVector(hid_t h5File, const std::string &name, std::vector<std::string> &strings);

  WellData data; ///< For returning pointers to internal object, all memory owned internally

  std::string mDirectory; ///< Legacy API specify directory and file separately.
  std::string mFileLeaf;
  std::string mFilePath;
  std::string mFlowOrder;

  /* Global size of array. */
  size_t mRows;   ///< Total number of rows (values in y dimension)
  size_t mCols;   ///< Total number of columns (values in x dimension)
  size_t mFlows;  ///< Total number of nucleotide flows.
  size_t mCurrentWell; ///< Current well for use with ReadNext()

  int WELL_NOT_LOADED;   /* not currently in memory. */
  int WELL_NOT_SUBSET; /* non-live well, assumed all zero all the time. */
  /* For our window/region of interest. */
  WellChunk mChunk;

  /* Data structures containing actual data. */
  Info mInfo;         ///< Any key,value information associated with this hdf5 file.
  std::vector<uint32_t> mRankData;  ///< All zeros since we don't use it, when can we just drop?
  std::vector<int32_t> mIndexes; ///< Conversion of well index on chip to index in mFlowData below.
  std::vector<int32_t> mWriteSubset; ///< Subset of wells to read/write into or from RAM.
  std::vector<float> mFlowData; ///< Big chunk of data...
  std::vector<float> mZeros; ///< Small vector used for WellData->flowValues
  std::vector<float> mInputBuffer; // temporary for writes.
  size_t mStepSize;
  int mCompression;   ///< What level of compression is being used.
  hid_t mHFile;       ///< Id for hdf5 file operations.
  
  bool mWriteOnClose;  ///< To support legacy api have a flag for writing when closing

  RWH5DataSet mRanks;       ///< Ranks hdf5 dataset
  RWH5DataSet mWells;       ///< Wells hdf5 dataset
  RWH5DataSet mInfoKeys;    ///< Dataset for keys matching mInfoValues order
  RWH5DataSet mInfoValues;  ///< Dataset for values matching mInfoKeys order
  size_t mWellChunkSize;
  size_t mFlowChunkSize;

  /* For iterating the current region well. */
  size_t mCurrentRegionRow;
  size_t mCurrentRegionCol;
  size_t mCurrentRow;
  size_t mCurrentCol;
  bool mIsLegacy;
private:
  RawWells(); // not implemented, don't call!
};

#endif // RAWWELLS_H
